#!/usr/bin/env python3
"""
HTTP inference service for closed-loop OMNeT++/Veins SDN-VANET integration.

The service loads the final Flower global model checkpoint and exposes:
  GET  /health
  POST /predict

POST /predict accepts either:
  {"text_input": "..."}
or:
  {"features": {"run": "veins", "density": 1, "time_cs": 1200, ...}}
"""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import torch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from flower_vanet_pipeline import ATTACK_CLASS_NAMES, build_model, encode_text, get_device


DEFAULT_CHECKPOINT = Path(__file__).resolve().parents[1] / "models" / "final_global_model.pt"


def features_to_text(features: dict[str, Any]) -> str:
    ordered_keys = [
        "run",
        "density",
        "ratio",
        "time_cs",
        "sender",
        "seq",
        "x_cm",
        "y_cm",
        "speed_cms",
        "accel_cms2",
        "heading_cdeg",
        "lane",
        "event",
    ]
    tokens: list[str] = []
    for key in ordered_keys:
        if key in features and features[key] is not None:
            tokens.extend([key, str(features[key])])
    for key in sorted(features):
        if key not in ordered_keys and features[key] is not None:
            tokens.extend([key, str(features[key])])
    return " ".join(tokens)


def mitigation_action(label: int, confidence: float, threshold: float) -> str:
    if label == 0:
        return "allow"
    if confidence < threshold:
        return "monitor"
    high_impact = {17, 18, 20, 21, 24}
    if label in high_impact:
        return "isolate_sender"
    if label in {13, 14, 15, 16}:
        return "drop_stale_or_replayed_message"
    return "drop_message"


class IdsModel:
    def __init__(self, checkpoint_path: Path, cpu: bool):
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        self.vocab = json.loads(Path(checkpoint["vocab_path"]).read_text())
        self.config = checkpoint["model_config"]
        self.label_names = checkpoint.get("label_names") or ATTACK_CLASS_NAMES[: int(self.config["num_labels"])]
        self.device = get_device(prefer_cuda=not cpu)
        self.model = build_model(
            vocab_size=len(self.vocab),
            num_labels=int(self.config["num_labels"]),
            max_len=int(self.config["max_len"]),
            d_model=int(self.config["d_model"]),
            nhead=int(self.config["nhead"]),
            num_layers=int(self.config["num_layers"]),
            dropout=float(self.config["dropout"]),
        ).to(self.device)
        self.model.load_state_dict(checkpoint["state_dict"], strict=True)
        self.model.eval()

    def predict(self, text_input: str, top_k: int, threshold: float) -> dict[str, Any]:
        ids, mask = encode_text(text_input, self.vocab, int(self.config["max_len"]))
        input_ids = torch.tensor([ids], dtype=torch.long, device=self.device)
        attention_mask = torch.tensor([mask], dtype=torch.long, device=self.device)
        with torch.no_grad():
            logits = self.model(input_ids, attention_mask)
            probabilities = torch.softmax(logits, dim=1)[0].detach().cpu()
        confidence, label_tensor = torch.max(probabilities, dim=0)
        label = int(label_tensor.item())
        top_values, top_indices = torch.topk(probabilities, k=min(top_k, len(probabilities)))
        return {
            "predicted_label": label,
            "attack_name": self.label_names[label] if label < len(self.label_names) else f"Class {label}",
            "confidence": float(confidence.item()),
            "action": mitigation_action(label, float(confidence.item()), threshold),
            "top_k": [
                {
                    "label": int(idx.item()),
                    "attack_name": self.label_names[int(idx.item())]
                    if int(idx.item()) < len(self.label_names)
                    else f"Class {int(idx.item())}",
                    "probability": float(value.item()),
                }
                for value, idx in zip(top_values, top_indices)
            ],
        }


def make_handler(model: IdsModel, top_k: int, threshold: float):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VANETIDSClosedLoop/1.0"

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args) -> None:
            print(f"[ids-server] {self.address_string()} - {fmt % args}")

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "num_labels": int(model.config["num_labels"]),
                    "device": str(model.device),
                },
            )

        def do_POST(self) -> None:
            if self.path != "/predict":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                text_input = body.get("text_input")
                if not text_input:
                    features = body.get("features")
                    if not isinstance(features, dict):
                        raise ValueError("request must include text_input or features object")
                    text_input = features_to_text(features)
                result = model.predict(str(text_input), top_k=top_k, threshold=threshold)
                result.update(
                    {
                        "vehicle_id": body.get("vehicle_id"),
                        "sim_time": body.get("sim_time"),
                    }
                )
                self._send_json(HTTPStatus.OK, result)
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Closed-loop VANET IDS inference server")
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--mitigation-threshold", type=float, default=0.60)
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checkpoint_path = Path(args.checkpoint).expanduser().resolve()
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"model checkpoint missing: {checkpoint_path}")
    model = IdsModel(checkpoint_path, cpu=args.cpu)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(model, args.top_k, args.mitigation_threshold))
    print(f"[ids-server] listening on http://{args.host}:{args.port}")
    print(f"[ids-server] checkpoint: {checkpoint_path}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
