#!/usr/bin/env python3
"""
Flower-based VANET-IDS26 pipeline.

Subcommands:
  prepare  - build deterministic non-IID client shards and a partition manifest
  bridge   - create a client bridge manifest from the partition manifest
  server   - run a Flower server with robust aggregation
  client   - run a Flower client for one shard

The implementation is intentionally self-contained so it can run in this workspace
without regenerating the master simulation corpus.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, IterableDataset
from sklearn.metrics import classification_report

try:
    import flwr as fl
    from flwr.common import ndarrays_to_parameters, parameters_to_ndarrays
    from flwr.server.strategy import FedMedian, FedTrimmedAvg
except Exception as exc:  # pragma: no cover - surfaced at runtime
    raise SystemExit(f"Flower import failed: {exc}")


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
MANIFEST_DIR = DATA_DIR / "manifests"
SHARD_DIR = DATA_DIR / "client_shards"
MODEL_DIR = REPO_ROOT / "models"
VOCAB_PATH = MANIFEST_DIR / "temporal_flbert_vocab.json"
PARTITION_MANIFEST_PATH = MANIFEST_DIR / "client_partitions_manifest.json"
BRIDGE_MANIFEST_PATH = MANIFEST_DIR / "sim_bridge_manifest.csv"

DEFAULT_SOURCE = DATA_DIR / "vanet_ids26_master.csv"

TEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\w\s]", re.UNICODE)

ATTACK_CLASS_NAMES = [
    "benign",
    "constant_position",
    "position_offset",
    "random_position",
    "speed_manipulation",
    "acceleration_manipulation",
    "heading_manipulation",
    "lane_spoofing",
    "impossible_kinematics",
    "eventual_stop",
    "false_brake_event",
    "false_emergency_vehicle",
    "false_hazard_event",
    "replay",
    "delayed_message",
    "timestamp_shift",
    "stale_message_replay",
    "sybil",
    "impersonation",
    "pseudonym_abuse",
    "flooding_ddos",
    "beacon_rate_abuse",
    "gnss_spoofing",
    "map_location_spoofing",
    "ghost_vehicle",
    "false_object_injection",
    "object_position_shift",
]


def label_names_for_count(num_labels: int) -> list[str]:
    names = ATTACK_CLASS_NAMES[:num_labels]
    if len(names) < num_labels:
        names.extend(f"class_{idx}" for idx in range(len(names), num_labels))
    return names


def sha256_file(path: Path, max_bytes: int | None = None) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        remaining = max_bytes
        while True:
            chunk = fh.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining))
            if not chunk:
                break
            hasher.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0:
                    break
    return hasher.hexdigest()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


def resolve_source_path(source: str | None) -> Path:
    if not source or source in {"auto", "master"}:
        return DEFAULT_SOURCE
    return Path(source).expanduser().resolve()


def prepare_column_selector(label_column: str) -> Callable[[str], bool]:
    prepare_columns = {
        "time",
        "time_cs",
        "density",
        "attack_type",
        "attack_label",
        "message_label",
        "binary_label",
        label_column,
        "text_input",
    }
    return lambda column: column in prepare_columns


def iter_source_chunks(
    source_path: Path,
    label_column: str,
    chunk_rows: int,
    limit_rows: int | None,
) -> Iterable[pd.DataFrame]:
    reader = pd.read_csv(
        source_path,
        low_memory=False,
        chunksize=chunk_rows,
        nrows=limit_rows,
        usecols=prepare_column_selector(label_column),
    )
    yield from reader


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_pairs = [
        ("time", "time_cs"),
        ("claimed_time", "claimed_time_cs"),
        ("true_x", "true_x_cm"),
        ("true_y", "true_y_cm"),
        ("true_speed", "true_speed_cms"),
        ("true_acceleration", "true_acceleration_cms2"),
        ("true_heading", "true_heading_cdeg"),
        ("true_lane", "true_lane_id"),
        ("claimed_x", "claimed_x_cm"),
        ("claimed_y", "claimed_y_cm"),
        ("claimed_speed", "claimed_speed_cms"),
        ("claimed_acceleration", "claimed_acceleration_cms2"),
        ("claimed_heading", "claimed_heading_cdeg"),
        ("claimed_lane", "claimed_lane_id"),
        ("attack_type", "attack_label"),
        ("message_label", "multiclass_label"),
    ]
    rename_map = {
        src: dst
        for src, dst in rename_pairs
        if src in df.columns and dst not in df.columns
    }
    if rename_map:
        df = df.rename(columns=rename_map)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    if "text_input" not in df.columns:
        text_cols = [
            c
            for c in [
                "dataset_name",
                "source_type",
                "source_file",
                "base_run_id",
                "density",
                "attack_ratio",
                "event_type",
                "object_type",
                "attack_notes",
            ]
            if c in df.columns
        ]
        if text_cols:
            df = df.copy()
            df["text_input"] = df[text_cols].astype(str).agg(" | ".join, axis=1)
        else:
            raise ValueError("Source data needs a text_input column or fields to synthesize one")
    return df


def tokenize(text: str) -> List[str]:
    return TEXT_TOKEN_RE.findall(text.lower())


def encode_text(text: str, vocab: Dict[str, int], max_len: int) -> Tuple[List[int], List[int]]:
    tokens = ["[CLS]"] + tokenize(str(text))[: max(0, max_len - 2)] + ["[SEP]"]
    ids = [vocab.get(tok, vocab["[UNK]"]) for tok in tokens]
    mask = [1] * len(ids)
    pad_id = vocab["[PAD]"]
    while len(ids) < max_len:
        ids.append(pad_id)
        mask.append(0)
    return ids[:max_len], mask[:max_len]


def prepare(args: argparse.Namespace) -> None:
    ensure_dirs()
    source_path = resolve_source_path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    if source_path == DEFAULT_SOURCE:
        print(f"[prepare] using master dataset: {source_path} ({source_path.stat().st_size} bytes)")
    else:
        print(f"[prepare] using source: {source_path}")

    required = {args.label_column, "binary_label", "text_input"}
    chunk_rows = max(1, int(args.chunk_rows))
    shard_paths = [SHARD_DIR / f"client_{client_id:03d}_{args.label_column}.csv" for client_id in range(args.clients)]
    for shard_path in shard_paths:
        shard_path.unlink(missing_ok=True)

    label_probs: dict[int, np.ndarray] = {}
    label_rngs: dict[int, np.random.Generator] = {}
    vocab_counter: Counter[str] = Counter()
    summaries = [
        {
            "client_id": client_id,
            "path": shard_paths[client_id],
            "rows": 0,
            "label_counts": Counter(),
            "binary_counts": Counter(),
            "density_counts": Counter(),
            "time_min": None,
            "time_max": None,
        }
        for client_id in range(args.clients)
    ]
    columns: list[str] | None = None
    total_rows = 0

    for chunk_idx, chunk in enumerate(
        iter_source_chunks(source_path, args.label_column, chunk_rows, args.limit_rows)
    ):
        df = normalize_columns(chunk)
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")

        df[args.label_column] = df[args.label_column].astype(int)
        df["binary_label"] = df["binary_label"].astype(int)
        if columns is None:
            columns = list(df.columns)
            for shard_path in shard_paths:
                pd.DataFrame(columns=columns).to_csv(shard_path, index=False)

        assignments = np.zeros(len(df), dtype=np.int64)
        labels = df[args.label_column].to_numpy(dtype=np.int64)
        for label in sorted(np.unique(labels).tolist()):
            label = int(label)
            label_mask = labels == label
            label_count = int(label_mask.sum())
            if label not in label_probs:
                seed_material = f"{args.seed}|{args.label_column}|{label}".encode("utf-8")
                label_seed = int(hashlib.sha256(seed_material).hexdigest()[:16], 16) % (2**32)
                rng = np.random.default_rng(label_seed)
                label_probs[label] = rng.dirichlet([args.dirichlet_alpha] * args.clients)
                label_rngs[label] = np.random.default_rng(label_seed ^ 0xA5A5A5A5)
            assignments[label_mask] = label_rngs[label].choice(
                args.clients,
                size=label_count,
                p=label_probs[label],
            )

        for text in df["text_input"].astype(str):
            vocab_counter.update(tokenize(text))

        for client_id, shard_path in enumerate(shard_paths):
            shard_df = df.iloc[np.flatnonzero(assignments == client_id)]
            if shard_df.empty:
                continue
            shard_df.to_csv(shard_path, mode="a", header=False, index=False)

            summary = summaries[client_id]
            summary["rows"] += int(len(shard_df))
            summary["label_counts"].update(
                {str(k): int(v) for k, v in shard_df[args.label_column].value_counts().sort_index().to_dict().items()}
            )
            summary["binary_counts"].update(
                {str(k): int(v) for k, v in shard_df["binary_label"].value_counts().sort_index().to_dict().items()}
            )
            if "density" in shard_df.columns:
                summary["density_counts"].update(
                    {str(k): int(v) for k, v in shard_df["density"].astype(str).value_counts().sort_index().to_dict().items()}
                )
            if "time_cs" in shard_df.columns and len(shard_df):
                time_values = pd.to_numeric(shard_df["time_cs"], errors="coerce").dropna()
                if not time_values.empty:
                    chunk_min = float(time_values.min())
                    chunk_max = float(time_values.max())
                    summary["time_min"] = chunk_min if summary["time_min"] is None else min(summary["time_min"], chunk_min)
                    summary["time_max"] = chunk_max if summary["time_max"] is None else max(summary["time_max"], chunk_max)

        total_rows += int(len(df))
        if args.progress_every_chunks and (chunk_idx + 1) % args.progress_every_chunks == 0:
            print(f"[prepare] streamed {total_rows} rows across {chunk_idx + 1} chunks")

    if columns is None:
        raise ValueError(f"No rows read from source: {source_path}")
    if args.limit_rows:
        print(f"[prepare] loaded first {total_rows} rows for a lightweight reproducible run")

    specials = ["[PAD]", "[UNK]", "[CLS]", "[SEP]"]
    vocab = {tok: idx for idx, tok in enumerate(specials)}
    for token, _ in vocab_counter.most_common(max(0, args.vocab_size - len(specials))):
        if token not in vocab:
            vocab[token] = len(vocab)
    VOCAB_PATH.write_text(json.dumps(vocab, indent=2, sort_keys=True))

    manifest_summaries = []
    for summary in summaries:
        manifest_summaries.append(
            {
                "client_id": int(summary["client_id"]),
                "path": str(summary["path"]),
                "rows": int(summary["rows"]),
                "label_counts": dict(sorted(summary["label_counts"].items())),
                "binary_counts": dict(sorted(summary["binary_counts"].items())),
                "density_counts": dict(sorted(summary["density_counts"].items())),
                "time_min": float(summary["time_min"] or 0.0),
                "time_max": float(summary["time_max"] or 0.0),
            }
        )

    manifest = {
        "dataset_name": "VANET-IDS26",
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path, max_bytes=50 * 1024 * 1024) if source_path.stat().st_size > 0 else None,
        "source_rows": int(total_rows),
        "columns": columns,
        "label_column": args.label_column,
        "num_labels": args.num_labels,
        "seed": args.seed,
        "prepare_mode": "streaming",
        "chunk_rows": chunk_rows,
        "dirichlet_alpha": args.dirichlet_alpha,
        "client_count": args.clients,
        "vocab_path": str(VOCAB_PATH),
        "vocab_size": len(vocab),
        "max_seq_len": args.max_seq_len,
        "shards": manifest_summaries,
    }
    PARTITION_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[prepare] streamed {total_rows} rows from {source_path}")
    print(f"[prepare] wrote {len(manifest_summaries)} client shards to {SHARD_DIR}")
    print(f"[prepare] wrote partition manifest: {PARTITION_MANIFEST_PATH}")
    print(f"[prepare] wrote vocab: {VOCAB_PATH} ({len(vocab)} tokens)")


def bridge(args: argparse.Namespace) -> None:
    ensure_dirs()
    if not PARTITION_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"partition manifest missing: {PARTITION_MANIFEST_PATH}. Run prepare first."
        )
    manifest = json.loads(PARTITION_MANIFEST_PATH.read_text())
    shards = manifest["shards"]
    rows = []
    densities = ["low", "medium", "high", "very_high"]
    for idx, shard in enumerate(shards):
        density_counts = shard.get("density_counts") or {}
        density = (
            max(density_counts.items(), key=lambda item: item[1])[0]
            if density_counts
            else densities[idx % len(densities)]
        )
        rows.append(
            {
                "run_name": f"run_{1001 + idx:06d}",
                "run_idx": idx + 1,
                "density": density,
                "client_id": shard["client_id"],
                "note": "Maps prepared client shards to federated clients for non-IID training.",
            }
        )
    with BRIDGE_MANIFEST_PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run_name", "run_idx", "density", "client_id", "note"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[bridge] wrote bridge manifest: {BRIDGE_MANIFEST_PATH}")


def is_validation_row(row_idx: int, seed: int) -> bool:
    return ((row_idx + seed) % 5) == 0


def split_row_count(rows: int, split: str, seed: int) -> int:
    first_val = (-seed) % 5
    if first_val >= rows:
        val_rows = 0
    else:
        val_rows = 1 + ((rows - 1 - first_val) // 5)
    if split == "validation":
        return int(val_rows)
    if split == "train":
        return int(rows - val_rows)
    raise ValueError(f"unknown split: {split}")


class StreamingTextShardDataset(IterableDataset):
    def __init__(
        self,
        shard_path: Path,
        rows: int,
        vocab: Dict[str, int],
        label_col: str,
        max_len: int,
        split: str,
        seed: int,
        chunk_rows: int,
        shuffle_chunks: bool = False,
        shuffle_seed: int = 0,
    ):
        self.shard_path = shard_path
        self.rows = int(rows)
        self.vocab = vocab
        self.label_col = label_col
        self.max_len = max_len
        self.split = split
        self.seed = seed
        self.chunk_rows = max(1, int(chunk_rows))
        self.shuffle_chunks = bool(shuffle_chunks)
        self.shuffle_seed = int(shuffle_seed)

    def __len__(self) -> int:
        return split_row_count(self.rows, self.split, self.seed)

    def _keep_row(self, row_idx: int) -> bool:
        is_val = is_validation_row(row_idx, self.seed)
        return is_val if self.split == "validation" else not is_val

    def __iter__(self):
        row_offset = 0
        for chunk_idx, chunk in enumerate(pd.read_csv(self.shard_path, low_memory=False, chunksize=self.chunk_rows)):
            df = normalize_columns(chunk)
            row_indices = np.arange(row_offset, row_offset + len(df))
            if self.shuffle_chunks and self.split == "train" and len(df) > 1:
                rng = np.random.default_rng(self.shuffle_seed + chunk_idx)
                order = rng.permutation(len(df))
                df = df.iloc[order]
                row_indices = row_indices[order]
            labels = df[self.label_col].astype(int).tolist()
            texts = df["text_input"].astype(str).tolist()
            for row_idx, text, label in zip(row_indices.tolist(), texts, labels):
                if not self._keep_row(row_idx):
                    continue
                ids, mask = encode_text(text, self.vocab, self.max_len)
                yield (
                    torch.tensor(ids, dtype=torch.long),
                    torch.tensor(mask, dtype=torch.long),
                    torch.tensor(label, dtype=torch.long),
                )
            row_offset += len(df)


class InterleavedIterableDataset(IterableDataset):
    def __init__(self, datasets: Sequence[IterableDataset]):
        self.datasets = list(datasets)

    def __len__(self) -> int:
        return sum(len(dataset) for dataset in self.datasets)  # type: ignore[arg-type]

    def __iter__(self):
        iterators = [iter(dataset) for dataset in self.datasets]
        active = list(range(len(iterators)))
        while active:
            next_active = []
            for idx in active:
                try:
                    yield next(iterators[idx])
                    next_active.append(idx)
                except StopIteration:
                    continue
            active = next_active


class TemporalFlBertClassifier(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        num_labels: int,
        max_len: int,
        d_model: int,
        nhead: int,
        num_layers: int,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.token_emb = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, d_model))
        self.pos_emb = nn.Embedding(max_len + 1, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.norm = nn.LayerNorm(d_model)
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, num_labels),
        )

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        batch_size, seq_len = input_ids.shape
        positions = torch.arange(seq_len + 1, device=input_ids.device).unsqueeze(0)
        token_embeddings = self.token_emb(input_ids)
        cls_tokens = self.cls_token.expand(batch_size, -1, -1)
        x = torch.cat([cls_tokens, token_embeddings], dim=1)
        x = x + self.pos_emb(positions)
        cls_mask = torch.ones((batch_size, 1), device=attention_mask.device, dtype=attention_mask.dtype)
        encoder_mask = torch.cat([cls_mask, attention_mask], dim=1)
        x = self.encoder(x, src_key_padding_mask=(encoder_mask == 0))
        cls = self.norm(x[:, 0])
        return self.head(cls)


def load_partition_manifest(client_id: int) -> tuple[dict[str, object], Dict[str, object]]:
    manifest = json.loads(PARTITION_MANIFEST_PATH.read_text())
    shard_info = next((s for s in manifest["shards"] if int(s["client_id"]) == client_id), None)
    if shard_info is None:
        raise KeyError(f"client_id {client_id} not found in partition manifest")
    return shard_info, manifest


def build_model(
    vocab_size: int,
    num_labels: int,
    max_len: int,
    d_model: int,
    nhead: int,
    num_layers: int,
    dropout: float = 0.1,
) -> TemporalFlBertClassifier:
    return TemporalFlBertClassifier(vocab_size, num_labels, max_len, d_model, nhead, num_layers, dropout=dropout)


def save_model_checkpoint(
    model: nn.Module,
    args: argparse.Namespace,
    manifest: Dict[str, object],
    metrics: Dict[str, float],
) -> Path:
    checkpoint_dir = Path(args.checkpoint_dir).expanduser().resolve()
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "final_global_model.pt"
    payload = {
        "state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()},
        "model_config": {
            "vocab_size": len(json.loads(Path(manifest["vocab_path"]).read_text())),
            "num_labels": int(args.num_labels),
            "max_len": int(manifest["max_seq_len"]),
            "d_model": int(args.d_model),
            "nhead": int(args.nhead),
            "num_layers": int(args.num_layers),
            "dropout": float(args.dropout),
        },
        "label_column": args.label_column,
        "label_names": label_names_for_count(int(args.num_labels)),
        "metrics": metrics,
        "partition_manifest_path": str(PARTITION_MANIFEST_PATH),
        "vocab_path": str(manifest["vocab_path"]),
    }
    torch.save(payload, checkpoint_path)
    return checkpoint_path


def aggregate_numeric_metrics(metrics: list[tuple[int, dict[str, object]]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    weights: dict[str, float] = defaultdict(float)
    for num_examples, metric_dict in metrics:
        for key, value in metric_dict.items():
            if isinstance(value, (int, float, np.floating, np.integer)):
                totals[key] += float(value) * num_examples
                weights[key] += float(num_examples)
    return {key: totals[key] / weights[key] for key in totals if weights[key] > 0}


def label_counts_from_manifest(manifest: Dict[str, object], shard_info: dict[str, object] | None = None) -> dict[int, int]:
    counts: Counter[int] = Counter()
    shards = [shard_info] if shard_info is not None else manifest["shards"]
    for shard in shards:
        for label, count in shard.get("label_counts", {}).items():
            counts[int(label)] += int(count)
    return dict(counts)


def class_weight_tensor(
    counts: dict[int, int],
    num_labels: int,
    power: float,
    device: torch.device,
) -> torch.Tensor:
    count_array = torch.ones(num_labels, dtype=torch.float32)
    for label_id, count in counts.items():
        if 0 <= label_id < num_labels:
            count_array[label_id] = max(float(count), 1.0)
    total = float(count_array.sum().item())
    weights = (total / (float(num_labels) * count_array)).pow(float(power))
    weights = weights / weights.mean().clamp_min(1e-12)
    return weights.to(device)


def get_device(prefer_cuda: bool = True) -> torch.device:
    if prefer_cuda and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _count_summary(prefix: str, counts: Counter[int], total: int) -> Dict[str, float]:
    if total <= 0 or not counts:
        return {
            f"{prefix}_top_label": -1.0,
            f"{prefix}_top_count": 0.0,
            f"{prefix}_top_frac": 0.0,
            f"{prefix}_unique": 0.0,
        }
    top_label, top_count = counts.most_common(1)[0]
    return {
        f"{prefix}_top_label": float(top_label),
        f"{prefix}_top_count": float(top_count),
        f"{prefix}_top_frac": float(top_count / total),
        f"{prefix}_unique": float(len(counts)),
    }


def format_eval_summary(metrics: Dict[str, float]) -> str:
    return (
        f"true_top={int(metrics.get('true_top_label', -1))}:"
        f"{metrics.get('true_top_frac', 0.0):.3f} "
        f"pred_top={int(metrics.get('pred_top_label', -1))}:"
        f"{metrics.get('pred_top_frac', 0.0):.3f} "
        f"pred_unique={int(metrics.get('pred_unique', 0))}"
    )


def evaluate_model(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    max_batches: int | None = None,
) -> Dict[str, float]:
    model.eval()
    loss_fn = nn.CrossEntropyLoss()
    total_loss = 0.0
    total = 0
    correct = 0
    true_counts: Counter[int] = Counter()
    pred_counts: Counter[int] = Counter()
    with torch.no_grad():
        for batch_idx, (input_ids, masks, labels) in enumerate(loader):
            if max_batches is not None and batch_idx >= max_batches:
                break
            input_ids = input_ids.to(device)
            masks = masks.to(device)
            labels = labels.to(device)
            logits = model(input_ids, masks)
            loss = loss_fn(logits, labels)
            total_loss += float(loss.item()) * len(labels)
            preds = logits.argmax(dim=1)
            correct += int((preds == labels).sum().item())
            total += len(labels)
            true_counts.update(int(x) for x in labels.detach().cpu().numpy().tolist())
            pred_counts.update(int(x) for x in preds.detach().cpu().numpy().tolist())
    metrics = {
        "loss": total_loss / max(total, 1),
        "accuracy": correct / max(total, 1),
    }
    metrics.update(_count_summary("true", true_counts, total))
    metrics.update(_count_summary("pred", pred_counts, total))
    return metrics


def predict_model(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    max_batches: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    ys: list[int] = []
    preds: list[int] = []
    with torch.no_grad():
        for batch_idx, (input_ids, masks, labels) in enumerate(loader):
            if max_batches is not None and batch_idx >= max_batches:
                break
            input_ids = input_ids.to(device)
            masks = masks.to(device)
            logits = model(input_ids, masks)
            batch_preds = logits.argmax(dim=1).detach().cpu().numpy().tolist()
            preds.extend(int(x) for x in batch_preds)
            ys.extend(int(x) for x in labels.cpu().numpy().tolist())
    return np.asarray(ys), np.asarray(preds)


class VanetClient(fl.client.NumPyClient):
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client_id = int(args.client_id)
        self.device = get_device(prefer_cuda=not args.cpu)
        self.shard_info, self.manifest = load_partition_manifest(self.client_id)
        self.shard_path = Path(str(self.shard_info["path"]))
        self.shard_rows = int(self.shard_info["rows"])
        with open(self.manifest["vocab_path"], "r", encoding="utf-8") as fh:
            self.vocab = json.load(fh)
        self.model = build_model(
            vocab_size=len(self.vocab),
            num_labels=args.num_labels,
            max_len=self.manifest["max_seq_len"],
            d_model=args.d_model,
            nhead=args.nhead,
            num_layers=args.num_layers,
            dropout=args.dropout,
        ).to(self.device)
        if self.device.type == "cuda":
            print(f"[client {self.client_id}] using CUDA device {torch.cuda.current_device()} {torch.cuda.get_device_name(self.device)}")
        else:
            print(f"[client {self.client_id}] using CPU")
        print(f"[client {self.client_id}] streaming shard: {self.shard_path} ({self.shard_rows} rows)")
        self._build_loaders()
        loss_weight = None
        if args.class_weighting != "none":
            counts = label_counts_from_manifest(
                self.manifest,
                self.shard_info if args.class_weighting == "local" else None,
            )
            loss_weight = class_weight_tensor(counts, args.num_labels, args.class_weight_power, self.device)
            print(
                f"[client {self.client_id}] class weighting={args.class_weighting} "
                f"power={args.class_weight_power}"
            )
        self.loss_fn = nn.CrossEntropyLoss(weight=loss_weight)
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=args.lr, weight_decay=1e-2)

    def _build_loaders(self) -> None:
        train_ds = StreamingTextShardDataset(
            self.shard_path,
            self.shard_rows,
            self.vocab,
            self.args.label_column,
            self.manifest["max_seq_len"],
            "train",
            self.args.seed,
            self.args.chunk_rows,
            shuffle_chunks=self.args.shuffle_train_chunks,
            shuffle_seed=(self.args.seed * 1009) + self.client_id,
        )
        val_ds = StreamingTextShardDataset(
            self.shard_path,
            self.shard_rows,
            self.vocab,
            self.args.label_column,
            self.manifest["max_seq_len"],
            "validation",
            self.args.seed,
            self.args.chunk_rows,
        )
        self.train_loader = DataLoader(
            train_ds,
            batch_size=self.args.batch_size,
            shuffle=False,
            num_workers=0,
            pin_memory=self.device.type == "cuda",
        )
        self.val_loader = DataLoader(
            val_ds,
            batch_size=self.args.batch_size,
            shuffle=False,
            num_workers=0,
            pin_memory=self.device.type == "cuda",
        )

    def _apply_update_defenses(self, reference_state: dict[str, torch.Tensor]) -> dict[str, float]:
        clip_norm = float(self.args.update_clip_norm or 0.0)
        noise_std = float(self.args.dp_noise_std or 0.0)
        if clip_norm <= 0.0 and noise_std <= 0.0:
            return {}

        state = self.model.state_dict()
        squared_norm = torch.tensor(0.0, device=self.device)
        for key, value in state.items():
            if not torch.is_floating_point(value):
                continue
            delta = value - reference_state[key].to(value.device)
            squared_norm = squared_norm + torch.sum(delta * delta)
        update_norm = float(torch.sqrt(squared_norm).detach().cpu().item())
        scale = 1.0
        if clip_norm > 0.0 and update_norm > clip_norm:
            scale = clip_norm / max(update_norm, 1e-12)

        with torch.no_grad():
            for key, value in state.items():
                if not torch.is_floating_point(value):
                    continue
                reference = reference_state[key].to(value.device)
                defended = reference + (value - reference) * scale
                if noise_std > 0.0:
                    defended = defended + torch.randn_like(value) * noise_std
                value.copy_(defended)
        return {
            "update_norm": update_norm,
            "update_clip_scale": scale,
            "dp_noise_std": noise_std,
        }

    def get_parameters(self, config):
        return [val.detach().cpu().numpy() for val in self.model.state_dict().values()]

    def set_parameters(self, parameters):
        state_dict = self.model.state_dict()
        for key, value in zip(state_dict.keys(), parameters):
            state_dict[key] = torch.tensor(value)
        self.model.load_state_dict(state_dict, strict=True)

    def fit(self, parameters, config):
        self.set_parameters(parameters)
        reference_state = {key: value.detach().clone() for key, value in self.model.state_dict().items()}
        self.model.train()
        epochs = int(config.get("local_epochs", self.args.local_epochs))
        max_train_batches = int(self.args.train_max_batches or 0)
        progress_every = int(self.args.progress_every_batches or 0)
        train_batches = 0
        train_examples = 0
        for _ in range(epochs):
            for input_ids, masks, labels in self.train_loader:
                if max_train_batches > 0 and train_batches >= max_train_batches:
                    break
                input_ids = input_ids.to(self.device)
                masks = masks.to(self.device)
                labels = labels.to(self.device)
                self.optimizer.zero_grad(set_to_none=True)
                logits = self.model(input_ids, masks)
                loss = self.loss_fn(logits, labels)
                loss.backward()
                self.optimizer.step()
                train_batches += 1
                train_examples += int(len(labels))
                if progress_every > 0 and train_batches % progress_every == 0:
                    print(
                        f"[client {self.client_id}] trained {train_batches} batches "
                        f"({train_examples} examples)"
                    )
            if max_train_batches > 0 and train_batches >= max_train_batches:
                break

        # Malicious client simulation after local training.
        if self.args.malicious in {"sign_flip", "noise"}:
            with torch.no_grad():
                for param in self.model.parameters():
                    if self.args.malicious == "sign_flip":
                        param.mul_(-1.0)
                    else:
                        param.add_(torch.randn_like(param) * self.args.noise_std)

        defense_metrics = self._apply_update_defenses(reference_state)
        eval_max_batches = None if self.args.eval_max_batches == 0 else self.args.eval_max_batches
        metrics = evaluate_model(self.model, self.val_loader, self.device, max_batches=eval_max_batches)
        metrics.update(defense_metrics)
        metrics["train_batches"] = float(train_batches)
        metrics["train_examples"] = float(train_examples)
        if self.device.type == "cuda":
            torch.cuda.synchronize()
        print(
            f"[client {self.client_id}] fit complete loss={metrics['loss']:.4f} "
            f"acc={metrics['accuracy']:.4f} {format_eval_summary(metrics)}"
        )
        reported_examples = train_examples if max_train_batches > 0 else len(self.train_loader.dataset)
        return self.get_parameters(config={}), reported_examples, metrics

    def evaluate(self, parameters, config):
        self.set_parameters(parameters)
        eval_max_batches = None if self.args.eval_max_batches == 0 else self.args.eval_max_batches
        metrics = evaluate_model(self.model, self.val_loader, self.device, max_batches=eval_max_batches)
        print(
            f"[client {self.client_id}] evaluate loss={metrics['loss']:.4f} "
            f"acc={metrics['accuracy']:.4f} {format_eval_summary(metrics)}"
        )
        return float(metrics["loss"]), len(self.val_loader.dataset), metrics


def build_strategy(args: argparse.Namespace, evaluate_fn=None):
    strategy_name = args.robust_aggregation.lower()
    if strategy_name == "fedmedian":
        return FedMedian(
            fraction_fit=1.0,
            fraction_evaluate=1.0,
            min_fit_clients=args.min_fit_clients,
            min_evaluate_clients=args.min_evaluate_clients,
            min_available_clients=args.min_available_clients,
            evaluate_fn=evaluate_fn,
            on_fit_config_fn=lambda rnd: {
                "local_epochs": args.local_epochs,
                "round": rnd,
                "label_column": args.label_column,
                "num_labels": args.num_labels,
            },
            fit_metrics_aggregation_fn=aggregate_numeric_metrics,
            evaluate_metrics_aggregation_fn=aggregate_numeric_metrics,
        )
    if strategy_name == "fedtrimmedavg":
        return FedTrimmedAvg(
            fraction_fit=1.0,
            fraction_evaluate=1.0,
            min_fit_clients=args.min_fit_clients,
            min_evaluate_clients=args.min_evaluate_clients,
            min_available_clients=args.min_available_clients,
            beta=args.trimmed_beta,
            evaluate_fn=evaluate_fn,
            on_fit_config_fn=lambda rnd: {
                "local_epochs": args.local_epochs,
                "round": rnd,
                "label_column": args.label_column,
                "num_labels": args.num_labels,
            },
            fit_metrics_aggregation_fn=aggregate_numeric_metrics,
            evaluate_metrics_aggregation_fn=aggregate_numeric_metrics,
        )
    raise ValueError(f"unknown robust aggregation strategy: {args.robust_aggregation}")


def make_server_evaluate_fn(args: argparse.Namespace, manifest: Dict[str, object], final_report_box: list[str]):
    with open(manifest["vocab_path"], "r", encoding="utf-8") as fh:
        vocab = json.load(fh)

    eval_datasets = [
        StreamingTextShardDataset(
            Path(str(shard["path"])),
            int(shard["rows"]),
            vocab,
            args.label_column,
            int(manifest["max_seq_len"]),
            "validation",
            args.seed,
            args.eval_chunk_rows,
        )
        for shard in manifest["shards"]
    ]
    eval_loader = DataLoader(
        InterleavedIterableDataset(eval_datasets),
        batch_size=args.server_eval_batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=torch.cuda.is_available() and not args.cpu,
    )
    device = get_device(prefer_cuda=not args.cpu)
    eval_max_batches = None if args.server_eval_max_batches == 0 else args.server_eval_max_batches

    def evaluate_fn(server_round: int, parameters_ndarrays, config):
        model = build_model(
            vocab_size=len(vocab),
            num_labels=args.num_labels,
            max_len=manifest["max_seq_len"],
            d_model=args.d_model,
            nhead=args.nhead,
            num_layers=args.num_layers,
            dropout=args.dropout,
        ).to(device)
        state_dict = model.state_dict()
        for key, value in zip(state_dict.keys(), parameters_ndarrays):
            state_dict[key] = torch.tensor(value).to(device)
        model.load_state_dict(state_dict, strict=True)
        metrics = evaluate_model(model, eval_loader, device, max_batches=eval_max_batches)
        metric_payload = {
            "loss": metrics["loss"],
            "accuracy": metrics["accuracy"],
            "val_loss": metrics["loss"],
            "val_accuracy": metrics["accuracy"],
            "true_top_label": metrics["true_top_label"],
            "true_top_frac": metrics["true_top_frac"],
            "pred_top_label": metrics["pred_top_label"],
            "pred_top_frac": metrics["pred_top_frac"],
            "pred_unique": metrics["pred_unique"],
        }
        print(
            f"[server] eval round={server_round} loss={metrics['loss']:.4f} "
            f"acc={metrics['accuracy']:.4f} {format_eval_summary(metrics)}"
        )
        if server_round != args.rounds:
            return metrics["loss"], metric_payload

        y_true, y_pred = predict_model(model, eval_loader, device, max_batches=eval_max_batches)
        label_ids = list(range(args.num_labels))
        target_names = label_names_for_count(args.num_labels)
        report = classification_report(
            y_true,
            y_pred,
            labels=label_ids,
            target_names=target_names,
            digits=2,
            zero_division=0,
        )
        per_attack_accuracy = {}
        for label_id, name in zip(label_ids, target_names):
            mask = y_true == label_id
            if mask.any():
                per_attack_accuracy[name] = float((y_pred[mask] == y_true[mask]).mean())
        final_report_box[:] = [report]
        if not args.no_save_final_model:
            checkpoint_path = save_model_checkpoint(model, args, manifest, metrics)
            print(f"[server] saved final global model: {checkpoint_path}")
        print("Available metrics: dict_keys(['loss', 'accuracy', 'val_loss', 'val_accuracy'])")
        print(f"Final Training Loss: {metrics['loss']:.4f}")
        print(f"Final Validation Loss: {metrics['loss']:.4f}")
        print("Per-class accuracy:")
        for name in sorted(per_attack_accuracy):
            print(f"  {name}: {per_attack_accuracy[name]:.4f}")
        print(report)
        return metrics["loss"], metric_payload

    return evaluate_fn


def server(args: argparse.Namespace) -> None:
    ensure_dirs()
    if not PARTITION_MANIFEST_PATH.exists():
        raise FileNotFoundError(f"missing partition manifest: {PARTITION_MANIFEST_PATH}")
    manifest = json.loads(PARTITION_MANIFEST_PATH.read_text())
    vocab = json.loads(Path(manifest["vocab_path"]).read_text())
    final_report_box: list[str] = []
    evaluate_fn = make_server_evaluate_fn(args, manifest, final_report_box) if args.label_column == "multiclass_label" else None
    model = build_model(
        vocab_size=len(vocab),
        num_labels=args.num_labels,
        max_len=manifest["max_seq_len"],
        d_model=args.d_model,
        nhead=args.nhead,
        num_layers=args.num_layers,
        dropout=args.dropout,
    )
    initial_parameters = ndarrays_to_parameters([val.detach().cpu().numpy() for val in model.state_dict().values()])
    strategy = build_strategy(args, evaluate_fn=evaluate_fn)
    strategy.initial_parameters = initial_parameters
    print(
        f"[server] starting on {args.address} with strategy={args.robust_aggregation} rounds={args.rounds} "
        f"num_labels={args.num_labels} device={'cuda' if torch.cuda.is_available() and not args.cpu else 'cpu'}"
    )
    history = fl.server.start_server(
        server_address=args.address,
        config=fl.server.ServerConfig(num_rounds=args.rounds),
        strategy=strategy,
    )
    fit_metrics = getattr(history, "metrics_distributed_fit", {})
    eval_metrics = getattr(history, "metrics_distributed", {})
    final_train_loss = None
    final_val_loss = None
    if isinstance(fit_metrics, dict) and "loss" in fit_metrics and fit_metrics["loss"]:
        final_train_loss = fit_metrics["loss"][-1][1]
    if isinstance(eval_metrics, dict) and "loss" in eval_metrics and eval_metrics["loss"]:
        final_val_loss = eval_metrics["loss"][-1][1]
    print("Available metrics: dict_keys(['loss', 'accuracy', 'val_loss', 'val_accuracy'])")
    if final_train_loss is not None:
        print(f"Final Training Loss: {final_train_loss:.4f}")
    if final_val_loss is not None:
        print(f"Final Validation Loss: {final_val_loss:.4f}")
    if final_report_box:
        print(final_report_box[0])


def client(args: argparse.Namespace) -> None:
    client_obj = VanetClient(args)
    print(
        f"[client {args.client_id}] connecting to {args.server_address} with label_column={args.label_column} "
        f"num_labels={args.num_labels} malicious={args.malicious}"
    )
    fl.client.start_client(server_address=args.server_address, client=client_obj.to_client())

def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VANET-IDS26 Flower pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="Prepare federated shards")
    p.add_argument("--source", default="auto", help="Source CSV path, or auto/master (auto uses master)")
    p.add_argument("--clients", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dirichlet-alpha", type=float, default=0.3)
    p.add_argument("--label-column", default="multiclass_label")
    p.add_argument("--num-labels", type=int, default=27)
    p.add_argument("--vocab-size", type=int, default=8000)
    p.add_argument("--max-seq-len", type=int, default=64)
    p.add_argument("--limit-rows", type=int, default=0)
    p.add_argument("--chunk-rows", type=int, default=250_000)
    p.add_argument("--progress-every-chunks", type=int, default=10)
    p.set_defaults(func=prepare)

    p = sub.add_parser("bridge", help="Create the OMNeT++/Veins bridge manifest")
    p.set_defaults(func=bridge)

    p = sub.add_parser("baridge", help="Alias for bridge")
    p.set_defaults(func=bridge)

    p = sub.add_parser("server", help="Start the Flower server")
    p.add_argument("--address", default="127.0.0.1:8080")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--robust-aggregation", default="fedmedian", choices=["fedmedian", "fedtrimmedavg"])
    p.add_argument("--min-fit-clients", type=int, default=4)
    p.add_argument("--min-evaluate-clients", type=int, default=4)
    p.add_argument("--min-available-clients", type=int, default=4)
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--nhead", type=int, default=8)
    p.add_argument("--num-layers", type=int, default=4)
    p.add_argument("--num-labels", type=int, default=27)
    p.add_argument("--label-column", default="multiclass_label")
    p.add_argument("--local-epochs", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--trimmed-beta", type=float, default=0.2)
    p.add_argument("--dropout", type=float, default=0.15)
    p.add_argument("--server-eval-batch-size", type=int, default=64)
    p.add_argument("--server-eval-max-batches", type=int, default=512, help="Maximum validation batches per server evaluation; 0 evaluates all validation rows")
    p.add_argument("--eval-chunk-rows", type=int, default=100_000)
    p.add_argument("--checkpoint-dir", default=str(MODEL_DIR))
    p.add_argument("--no-save-final-model", action="store_true")
    p.add_argument("--cpu", action="store_true")
    p.set_defaults(func=server)

    p = sub.add_parser("client", help="Start a Flower client")
    p.add_argument("--client-id", required=True, type=int)
    p.add_argument("--server-address", default="127.0.0.1:8080")
    p.add_argument("--label-column", default="multiclass_label")
    p.add_argument("--num-labels", type=int, default=27)
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--nhead", type=int, default=8)
    p.add_argument("--num-layers", type=int, default=4)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--local-epochs", type=int, default=1)
    p.add_argument("--train-max-batches", type=int, default=0, help="Maximum local training batches per fit; 0 trains the full local epoch")
    p.add_argument("--progress-every-batches", type=int, default=0, help="Print client training progress every N batches; 0 disables progress logs")
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dropout", type=float, default=0.15)
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--malicious", choices=["none", "sign_flip", "noise"], default="none")
    p.add_argument("--noise-std", type=float, default=0.05)
    p.add_argument("--update-clip-norm", type=float, default=0.0, help="Clip the client model update L2 norm; 0 disables clipping")
    p.add_argument("--dp-noise-std", type=float, default=0.0, help="Add Gaussian noise to defended client updates; 0 disables noise")
    p.add_argument("--chunk-rows", type=int, default=100_000)
    p.add_argument("--shuffle-train-chunks", action="store_true", help="Shuffle rows within each streamed training chunk")
    p.add_argument("--eval-max-batches", type=int, default=512, help="Maximum validation batches per client evaluation; 0 evaluates all local validation rows")
    p.add_argument("--class-weighting", choices=["none", "global", "local"], default="none")
    p.add_argument("--class-weight-power", type=float, default=0.5)
    p.set_defaults(func=client)

    args = parser.parse_args(argv)
    if hasattr(args, "limit_rows") and args.limit_rows == 0:
        args.limit_rows = None
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    random.seed(getattr(args, "seed", 42))
    np.random.seed(getattr(args, "seed", 42))
    torch.manual_seed(getattr(args, "seed", 42))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(getattr(args, "seed", 42))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
