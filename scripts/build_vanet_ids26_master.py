from pathlib import Path
import csv
import gzip
import argparse
import sys
import time

ROOT = Path("/mnt/c/VANET_Dataset/fl-bert-vanet-dataset")
DATASET_NAME = "VANET-IDS26"

RUNS = [f"run_{i:06d}" for i in range(1001, 1021)]

FIELDNAMES = [
    "dataset_name",
    "record_id",
    "source_type",
    "source_file",
    "base_run_id",
    "density",
    "attack_ratio",

    "message_id",
    "base_message_id",
    "overlay_message_id",
    "original_message_id",
    "attack_dataset_id",

    "time",
    "claimed_time",
    "physical_sender_id",
    "claimed_sender_id",
    "sequence_number",

    "true_x",
    "true_y",
    "true_speed",
    "true_acceleration",
    "true_heading",
    "true_lane",

    "claimed_x",
    "claimed_y",
    "claimed_speed",
    "claimed_acceleration",
    "claimed_heading",
    "claimed_lane",

    "malicious_delay_ms",
    "sybil_group_id",
    "event_type",
    "false_object_id",
    "object_type",
    "object_x",
    "object_y",
    "attack_start_time",
    "attack_notes",

    "is_attacker",
    "is_synthetic_message",

    "attack_type",
    "attack_label",
    "message_label",
    "binary_label",
    "multiclass_label",

    "text_input",
]

TEXT_FIELDS = [
    "time",
    "claimed_time",
    "physical_sender_id",
    "claimed_sender_id",
    "sequence_number",

    "true_x",
    "true_y",
    "true_speed",
    "true_acceleration",
    "true_heading",
    "true_lane",

    "claimed_x",
    "claimed_y",
    "claimed_speed",
    "claimed_acceleration",
    "claimed_heading",
    "claimed_lane",

    "malicious_delay_ms",
    "sybil_group_id",
    "event_type",
    "false_object_id",
    "object_type",
    "object_x",
    "object_y",
]

def density_from_run(run_id: str) -> str:
    try:
        n = int(run_id.split("_")[1])
    except Exception:
        return ""

    if 1001 <= n <= 1005:
        return "low"
    if 1006 <= n <= 1010:
        return "medium"
    if 1011 <= n <= 1015:
        return "high"
    if 1016 <= n <= 1020:
        return "very_high"
    return ""

def to_int_label(value, default=0) -> int:
    try:
        s = str(value).strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default

def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()

def make_text_input(row: dict) -> str:
    """
    BERT-ready text version of the VANET message.

    Important:
    This text intentionally excludes attack_type, attack_label,
    binary_label, multiclass_label, message_label, source_type,
    and record_id to avoid direct label leakage.
    """
    parts = []
    for key in TEXT_FIELDS:
        value = str(row.get(key, "")).strip()
        if value != "":
            parts.append(f"{key}={value}")
    return " ; ".join(parts)

def standard_base_row(row: dict, path: Path) -> dict:
    run_id = row.get("run_id", "")
    attack_label = to_int_label(row.get("attack_label", "0"), 0)

    out = {k: "" for k in FIELDNAMES}

    message_id = row.get("message_id", "")

    out.update({
        "dataset_name": DATASET_NAME,
        "record_id": f"base::{message_id}",
        "source_type": "benign_base",
        "source_file": rel(path),
        "base_run_id": run_id,
        "density": density_from_run(run_id),
        "attack_ratio": "0",

        "message_id": message_id,
        "base_message_id": message_id,
        "overlay_message_id": "",
        "original_message_id": "",
        "attack_dataset_id": "",

        "time": row.get("time", ""),
        "claimed_time": row.get("time", ""),
        "physical_sender_id": row.get("physical_sender_id", ""),
        "claimed_sender_id": row.get("claimed_sender_id", ""),
        "sequence_number": row.get("sequence_number", ""),

        "true_x": row.get("true_x", ""),
        "true_y": row.get("true_y", ""),
        "true_speed": row.get("true_speed", ""),
        "true_acceleration": row.get("true_acceleration", ""),
        "true_heading": row.get("true_heading", ""),
        "true_lane": row.get("true_lane", ""),

        "claimed_x": row.get("claimed_x", ""),
        "claimed_y": row.get("claimed_y", ""),
        "claimed_speed": row.get("claimed_speed", ""),
        "claimed_acceleration": row.get("claimed_acceleration", ""),
        "claimed_heading": row.get("claimed_heading", ""),
        "claimed_lane": row.get("claimed_lane", row.get("true_lane", "")),

        "is_attacker": row.get("is_attacker", "0"),
        "is_synthetic_message": "0",

        "attack_type": row.get("attack_type", "benign"),
        "attack_label": str(attack_label),
        "message_label": row.get("message_label", str(attack_label)),
        "binary_label": "0",
        "multiclass_label": str(attack_label),
    })

    out["text_input"] = make_text_input(out)
    return out

def parse_overlay_ratio(path: Path) -> str:
    folder = path.parent.name
    try:
        return folder.rsplit("_", 1)[1]
    except Exception:
        return ""

def standard_overlay_row(row: dict, path: Path) -> dict:
    run_id = row.get("base_run_id", "")
    attack_label = to_int_label(row.get("attack_label", row.get("message_label", "0")), 0)

    out = {k: "" for k in FIELDNAMES}

    overlay_message_id = row.get("overlay_message_id", "")
    base_message_id = row.get("base_message_id", "")
    message_id = overlay_message_id if overlay_message_id else base_message_id

    out.update({
        "dataset_name": DATASET_NAME,
        "record_id": f"overlay::{row.get('attack_dataset_id', '')}::{message_id}",
        "source_type": "attack_overlay",
        "source_file": rel(path),
        "base_run_id": run_id,
        "density": density_from_run(run_id),
        "attack_ratio": parse_overlay_ratio(path),

        "message_id": message_id,
        "base_message_id": base_message_id,
        "overlay_message_id": overlay_message_id,
        "original_message_id": row.get("original_message_id", ""),
        "attack_dataset_id": row.get("attack_dataset_id", ""),

        "time": row.get("time", ""),
        "claimed_time": row.get("claimed_time", ""),
        "physical_sender_id": row.get("physical_sender_id", ""),
        "claimed_sender_id": row.get("claimed_sender_id", ""),
        "sequence_number": row.get("sequence_number", ""),

        "true_x": row.get("true_x", ""),
        "true_y": row.get("true_y", ""),
        "true_speed": row.get("true_speed", ""),
        "true_acceleration": row.get("true_acceleration", ""),
        "true_heading": row.get("true_heading", ""),
        "true_lane": row.get("true_lane", ""),

        "claimed_x": row.get("claimed_x", ""),
        "claimed_y": row.get("claimed_y", ""),
        "claimed_speed": row.get("claimed_speed", ""),
        "claimed_acceleration": row.get("claimed_acceleration", ""),
        "claimed_heading": row.get("claimed_heading", ""),
        "claimed_lane": row.get("claimed_lane", ""),

        "malicious_delay_ms": row.get("malicious_delay_ms", ""),
        "sybil_group_id": row.get("sybil_group_id", ""),
        "event_type": row.get("event_type", ""),
        "false_object_id": row.get("false_object_id", ""),
        "object_type": row.get("object_type", ""),
        "object_x": row.get("object_x", ""),
        "object_y": row.get("object_y", ""),
        "attack_start_time": row.get("attack_start_time", ""),
        "attack_notes": row.get("attack_notes", ""),

        "is_attacker": row.get("is_attacker", ""),
        "is_synthetic_message": row.get("is_synthetic_message", ""),

        "attack_type": row.get("attack_type", ""),
        "attack_label": str(attack_label),
        "message_label": row.get("message_label", str(attack_label)),
        "binary_label": "0" if attack_label == 0 else "1",
        "multiclass_label": str(attack_label),
    })

    out["text_input"] = make_text_input(out)
    return out

def iter_csv_rows(path: Path):
    with path.open("r", newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row

def build(args):
    start = time.time()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    temp_output = output.with_suffix(output.suffix + ".tmp")
    if temp_output.exists():
        temp_output.unlink()

    base_files = [ROOT / "dataset" / "processed" / run / "messages.csv" for run in RUNS]
    overlay_files = sorted((ROOT / "dataset" / "overlays").glob("run_001*/**/attack_overlay.csv"))

    if args.max_overlay_files is not None:
        overlay_files = overlay_files[:args.max_overlay_files]

    print(f"Dataset root: {ROOT}")
    print(f"Output: {output}")
    print(f"Base files: {len(base_files)}")
    print(f"Overlay files: {len(overlay_files)}")
    print(f"Compression level: {args.compresslevel}")
    print()

    total_rows = 0
    base_rows = 0
    overlay_rows = 0

    with gzip.open(temp_output, "wt", newline="", compresslevel=args.compresslevel, encoding="utf-8") as gz:
        writer = csv.DictWriter(gz, fieldnames=FIELDNAMES)
        writer.writeheader()

        for path in base_files:
            if not path.exists():
                print(f"WARNING missing base file: {path}")
                continue

            local_count = 0
            print(f"Reading base: {rel(path)}", flush=True)

            for row in iter_csv_rows(path):
                writer.writerow(standard_base_row(row, path))
                total_rows += 1
                base_rows += 1
                local_count += 1

                if args.max_base_rows is not None and base_rows >= args.max_base_rows:
                    break

                if total_rows % 1000000 == 0:
                    print(f"Rows written: {total_rows:,}", flush=True)

            print(f"  base rows written from file: {local_count:,}", flush=True)

            if args.max_base_rows is not None and base_rows >= args.max_base_rows:
                print("Reached max base rows for test run.")
                break

        for file_index, path in enumerate(overlay_files, start=1):
            local_count = 0
            print(f"Reading overlay {file_index}/{len(overlay_files)}: {rel(path)}", flush=True)

            for row in iter_csv_rows(path):
                writer.writerow(standard_overlay_row(row, path))
                total_rows += 1
                overlay_rows += 1
                local_count += 1

                if args.max_rows_per_overlay is not None and local_count >= args.max_rows_per_overlay:
                    break

                if total_rows % 1000000 == 0:
                    print(f"Rows written: {total_rows:,}", flush=True)

            print(f"  overlay rows written from file: {local_count:,}", flush=True)

    temp_output.rename(output)

    elapsed = time.time() - start
    print()
    print("DONE")
    print(f"Output file: {output}")
    print(f"Total rows written excluding header: {total_rows:,}")
    print(f"Base rows: {base_rows:,}")
    print(f"Overlay rows: {overlay_rows:,}")
    print(f"Elapsed seconds: {elapsed:.1f}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--compresslevel", type=int, default=1)

    # Test-run controls
    parser.add_argument("--max-base-rows", type=int, default=None)
    parser.add_argument("--max-overlay-files", type=int, default=None)
    parser.add_argument("--max-rows-per-overlay", type=int, default=None)

    args = parser.parse_args()
    build(args)

if __name__ == "__main__":
    main()
