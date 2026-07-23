from pathlib import Path
import csv
import gzip
from collections import Counter
import sys

ROOT = Path("/mnt/c/VANET_Dataset/fl-bert-vanet-dataset")
sys.path.insert(0, str(ROOT / "scripts"))

from build_vanet_ids26_master import (
    FIELDNAMES,
    standard_base_row,
    standard_overlay_row,
)

OUT = ROOT / "release" / "github" / "VANET-IDS26" / "samples" / "vanet_ids26_sample.csv.gz"

BENIGN_LIMIT = 1000
PER_ATTACK_LIMIT = 1000

ATTACK_TYPES = {
    1: "constant_position",
    2: "position_offset",
    3: "random_position",
    4: "speed_manipulation",
    5: "acceleration_manipulation",
    6: "heading_manipulation",
    7: "lane_spoofing",
    8: "impossible_kinematics",
    9: "eventual_stop",
    10: "false_brake_event",
    11: "false_emergency_vehicle",
    12: "false_hazard_event",
    13: "replay",
    14: "delayed_message",
    15: "timestamp_shift",
    16: "stale_message_replay",
    17: "sybil",
    18: "impersonation",
    19: "pseudonym_abuse",
    20: "flooding_ddos",
    21: "beacon_rate_abuse",
    22: "gnss_spoofing",
    23: "map_location_spoofing",
    24: "ghost_vehicle",
    25: "false_object_injection",
    26: "object_position_shift",
}

def read_csv(path):
    with path.open("r", newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    counts = Counter()

    with gzip.open(OUT, "wt", newline="", compresslevel=1, encoding="utf-8") as gz:
        writer = csv.DictWriter(gz, fieldnames=FIELDNAMES)
        writer.writeheader()

        base_path = ROOT / "dataset" / "processed" / "run_001001" / "messages.csv"
        print(f"Sampling benign rows from {base_path.relative_to(ROOT)}")

        for row in read_csv(base_path):
            writer.writerow(standard_base_row(row, base_path))
            counts[0] += 1
            if counts[0] >= BENIGN_LIMIT:
                break

        for label, attack in ATTACK_TYPES.items():
            path = ROOT / f"dataset/overlays/run_001001/{attack}_10/attack_overlay.csv"

            if not path.exists():
                matches = sorted((ROOT / "dataset" / "overlays").glob(f"run_001*/{attack}_*/attack_overlay.csv"))
                if not matches:
                    print(f"WARNING: no overlay found for attack {label}: {attack}")
                    continue
                path = matches[0]

            print(f"Sampling attack {label:02d} {attack} from {path.relative_to(ROOT)}")

            for row in read_csv(path):
                writer.writerow(standard_overlay_row(row, path))
                counts[label] += 1
                if counts[label] >= PER_ATTACK_LIMIT:
                    break

    print()
    print("DONE")
    print(f"Output: {OUT}")
    print("Counts by multiclass label:")
    for label in range(27):
        print(f"{label}: {counts[label]}")
    print(f"Total rows excluding header: {sum(counts.values())}")

if __name__ == "__main__":
    main()
