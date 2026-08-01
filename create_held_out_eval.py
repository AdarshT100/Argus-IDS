from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

RANDOM_STATE: Final[int] = 42
CHUNKSIZE: Final[int] = 50_000
LABEL_COL: Final[str] = "Label"
DROP_COLS: Final[set[str]] = {"Flow ID", "Source IP", "Destination IP", "Timestamp"}

SOURCE_FILES: Final[dict[str, list[str]]] = {
    "BENIGN": [
        "Tuesday-WorkingHours.pcap_ISCX.csv",
        "Wednesday-workingHours.pcap_ISCX.csv",
        "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
        "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv",
        "Friday-WorkingHours-Morning.pcap_ISCX.csv",
        "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
        "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv",
    ],
    "DoS": [
        "Wednesday-workingHours.pcap_ISCX.csv",
        "Friday-WorkingHours-Morning.pcap_ISCX.csv",
    ],
    "DDoS": ["Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv"],
    "PortScan": ["Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv"],
    "BruteForce": ["Tuesday-WorkingHours.pcap_ISCX.csv"],
    "WebAttack": ["Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv"],
    "Infiltration": ["Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv"],
}

LABEL_TO_CLASS: Final[dict[str, str]] = {
    "benign": "BENIGN",
    "dos hulk": "DoS",
    "dos goldeneye": "DoS",
    "dos slowloris": "DoS",
    "dos slowhttptest": "DoS",
    "ddos": "DDoS",
    "portscan": "PortScan",
    "ftp-patator": "BruteForce",
    "ssh-patator": "BruteForce",
    "web attack - brute force": "BruteForce",
    "web attack - xss": "WebAttack",
    "web attack - sql injection": "WebAttack",
    "infiltration": "Infiltration",
    "bot": "Infiltration",
    "heartbleed": "Infiltration",
}

CLASS_ORDER: Final[list[str]] = [
    "BENIGN",
    "DoS",
    "DDoS",
    "PortScan",
    "BruteForce",
    "WebAttack",
    "Infiltration",
]

ATTACK_CLASSES: Final[list[str]] = [
    "DoS",
    "DDoS",
    "PortScan",
    "BruteForce",
    "WebAttack",
    "Infiltration",
]


def configure_logging() -> None:
    """Configure process-wide logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Create the frozen mixed held-out CICIDS2017 evaluation CSV."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing held_out_eval.csv and held_out_manifest.json.",
    )
    return parser.parse_args()


def normalise_label(value: object) -> str:
    """Normalise CICIDS2017 label text for case-insensitive class matching."""
    label = str(value).strip()
    label = label.replace("\u2013", "-").replace("\u2014", "-").replace("\ufffd", "-")
    return " ".join(label.lower().split())


def map_labels(labels: pd.Series) -> pd.Series:
    """Map raw CICIDS2017 labels to held-out evaluation classes."""
    return labels.map(normalise_label).map(LABEL_TO_CLASS)


def clean_chunk(chunk: pd.DataFrame, filename: str) -> pd.DataFrame:
    """Apply the same raw cleaning steps used before training, preserving Label."""
    chunk.columns = chunk.columns.str.strip()

    if LABEL_COL not in chunk.columns:
        raise ValueError(f"'Label' column not found in {filename}.")

    chunk.drop(columns=[col for col in DROP_COLS if col in chunk.columns], inplace=True)
    chunk.replace([np.inf, -np.inf], np.nan, inplace=True)
    chunk.dropna(inplace=True)
    return chunk


def append_matching_rows(
    class_frames: dict[str, list[pd.DataFrame]],
    rows_available: dict[str, int],
    filename: str,
    chunk: pd.DataFrame,
) -> None:
    """Collect rows whose mapped label belongs to a class sourced from filename."""
    eval_labels = map_labels(chunk[LABEL_COL])

    for eval_class, source_files in SOURCE_FILES.items():
        if filename not in source_files:
            continue

        class_chunk = chunk.loc[eval_labels == eval_class].copy()
        row_count = len(class_chunk)
        rows_available[eval_class] += row_count

        if row_count:
            class_frames[eval_class].append(class_chunk)

        logging.info("%s: %s rows found for %s", filename, row_count, eval_class)


def load_class_pools(data_dir: Path) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """Load the configured CSV files in chunks and build per-class row pools."""
    class_frames: dict[str, list[pd.DataFrame]] = {name: [] for name in CLASS_ORDER}
    rows_available: dict[str, int] = {name: 0 for name in CLASS_ORDER}

    for filename in SOURCE_FILES["BENIGN"]:
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Required CICIDS2017 CSV not found: {path}")

        logging.info("Loading %s", path)
        for chunk in pd.read_csv(path, chunksize=CHUNKSIZE):
            cleaned = clean_chunk(chunk, filename)
            append_matching_rows(class_frames, rows_available, filename, cleaned)

    class_pools: dict[str, pd.DataFrame] = {}
    for eval_class in CLASS_ORDER:
        frames = class_frames[eval_class]
        class_pools[eval_class] = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return class_pools, rows_available


def sample_frame(df: pd.DataFrame, target: int) -> pd.DataFrame:
    """Sample up to target rows without oversampling."""
    if len(df) <= target:
        return df.copy()
    return df.sample(n=target, random_state=RANDOM_STATE)


def sample_classes(
    class_pools: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """Sample attack classes first, then BENIGN from all source files."""
    samples: dict[str, pd.DataFrame] = {}
    targets: dict[str, int] = {}

    for eval_class in ATTACK_CLASSES:
        target = 2_000 if eval_class in {"WebAttack", "Infiltration"} else 5_000
        targets[eval_class] = target
        samples[eval_class] = sample_frame(class_pools[eval_class], target)
        logging.info("%s rows sampled for %s", len(samples[eval_class]), eval_class)

    largest_attack_sample = max(len(samples[eval_class]) for eval_class in ATTACK_CLASSES)
    benign_target = min(10_000, 2 * largest_attack_sample)
    targets["BENIGN"] = benign_target
    samples["BENIGN"] = sample_frame(class_pools["BENIGN"], benign_target)
    logging.info("%s rows sampled for BENIGN", len(samples["BENIGN"]))

    return samples, targets


def build_manifest(
    samples: dict[str, pd.DataFrame],
    rows_available: dict[str, int],
    sampling_targets: dict[str, int],
) -> dict[str, object]:
    """Build the held-out manifest payload."""
    class_counts = {eval_class: int(len(samples[eval_class])) for eval_class in CLASS_ORDER}

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "random_state": RANDOM_STATE,
        "total_rows": int(sum(class_counts.values())),
        "class_counts": class_counts,
        "source_files": {eval_class: SOURCE_FILES[eval_class] for eval_class in CLASS_ORDER},
        "rows_available_before_sampling": {
            eval_class: int(rows_available[eval_class]) for eval_class in CLASS_ORDER
        },
        "sampling_targets": {
            eval_class: int(sampling_targets[eval_class]) for eval_class in CLASS_ORDER
        },
    }


def write_outputs(
    samples: dict[str, pd.DataFrame],
    manifest: dict[str, object],
    held_out_path: Path,
    manifest_path: Path,
) -> None:
    """Write the shuffled held-out CSV and JSON manifest."""
    held_out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    held_out = pd.concat([samples[eval_class] for eval_class in CLASS_ORDER], ignore_index=True)
    held_out = held_out.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)
    held_out.to_csv(held_out_path, index=False)

    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)
        file.write("\n")

    logging.info("Total rows in held_out_eval.csv: %s", len(held_out))
    logging.info("Held-out CSV saved to %s", held_out_path)
    logging.info("Manifest saved to %s", manifest_path)


def main() -> int:
    """Create the frozen mixed held-out evaluation CSV."""
    configure_logging()
    args = parse_args()

    data_dir = Path(os.environ.get("ARGUS_DATA_DIR", "./Dataset"))
    model_dir = Path(os.environ.get("ARGUS_MODEL_DIR", "backend/model"))
    held_out_path = data_dir / "held_out_eval.csv"
    manifest_path = model_dir / "held_out_manifest.json"

    if held_out_path.exists() and not args.force:
        logging.warning("%s already exists; exiting without overwriting.", held_out_path)
        return 0

    class_pools, rows_available = load_class_pools(data_dir)
    samples, sampling_targets = sample_classes(class_pools)
    manifest = build_manifest(samples, rows_available, sampling_targets)
    write_outputs(samples, manifest, held_out_path, manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
