# filename: backend/consumers/flow_generator.py
# purpose: Read CICIDS2017 CSVs row by row, publish raw feature vectors to
#          argus:flows Redis stream at a fixed rate.
# governs: §4.3, §5.2 — flow_generator.py spec

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from backend.services.stream_manager import STREAM_FLOWS, xadd

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
DATA_DIR: str = os.environ.get("ARGUS_DATA_DIR", "./Dataset")
STREAM_RATE: float = float(os.environ.get("ARGUS_STREAM_RATE", "50"))  # packets/sec
LOG_INTERVAL: int = int(os.environ.get("ARGUS_FLOW_LOG_INTERVAL", "1000"))  # rows

# Columns removed before training — same list as train_model.py / train_anomaly.py
_COLS_TO_DROP: list[str] = ["Flow ID", "Source IP", "Destination IP", "Timestamp"]

# held_out_eval.csv must never enter any training or streaming pipeline (§10, §14)
_EXCLUDED_FILENAMES: frozenset[str] = frozenset({"held_out_eval.csv"})

# Canonical CICIDS2017 day order — mirrors training file narrative 
_CANONICAL_ORDER: list[str] = [
    "Tuesday-WorkingHours.pcap_ISCX.csv",
    "Wednesday-workingHours.pcap_ISCX.csv",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
    "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv",
]

# ── Shutdown flag — set by SIGTERM or KeyboardInterrupt ──────────────────────
_shutdown: bool = False


def _handle_signal(signum: int, frame: object) -> None:
    global _shutdown
    log.info("Shutdown signal received (%s) — draining current batch then exiting.", signum)
    _shutdown = True


# ── CSV discovery ─────────────────────────────────────────────────────────────

def discover_csv_files(data_dir: str) -> list[Path]:
    """
    Return sorted list of CICIDS2017 CSV paths from data_dir,
    excluding held_out_eval.csv (hard constraint — §10, §14).
    Mirrors the exclusion pattern in train_anomaly.py.
    """
    data_path = Path(data_dir)
    if not data_path.is_dir():
                raise FileNotFoundError(
            f"ARGUS_DATA_DIR not found or is not a directory: {data_dir!r}"
        )
    available: set[str] = {
        p.name for p in data_path.glob("*.csv")
        if p.name.lower() not in _EXCLUDED_FILENAMES
    }

    if not available:
        raise FileNotFoundError(
            f"No eligible CSV files found in {data_dir!r} "
            f"(excluding {sorted(_EXCLUDED_FILENAMES)})."
        )

    # Files present in canonical order first, then any extras sorted alphabetically
    ordered = [data_path / f for f in _CANONICAL_ORDER if f in available]
    extras = sorted(data_path / f for f in available if f not in set(_CANONICAL_ORDER))
    csv_files = ordered + extras

    log.info("Discovered %d CSV file(s) for replay (day-ordered, held_out_eval.csv excluded):", len(csv_files))
    for csv_path in csv_files:
        log.info("  %s", csv_path.name)

    return csv_files

# ── Cleaning ──────────────────────────────────────────────────────────────────

def clean_chunk(chunk: pd.DataFrame, filename: str) -> pd.DataFrame:
    """
    Apply the same preprocessing as train_model.py steps 1–2:
      1. Strip column names
      2. Drop metadata columns (Flow ID, Source IP, Destination IP, Timestamp)
      3. Replace inf with NaN, drop NaN rows

    Label column is retained — published as the `label` field for downstream
    consumer observability. Rows are NOT scaled here; scaling happens in
    prediction_consumer.py (Phase 7).

    Args:
        chunk:    Raw DataFrame chunk from pd.read_csv.
        filename: Source filename — logged on cleaning errors only.

    Returns:
        Cleaned DataFrame with Label column intact.
    """
    chunk.columns = chunk.columns.str.strip()

    for col in _COLS_TO_DROP:
        if col in chunk.columns:
            chunk.drop(col, axis=1, inplace=True)

    chunk.replace([np.inf, -np.inf], np.nan, inplace=True)
    chunk.dropna(inplace=True)

    if chunk.empty:
        log.debug("Chunk from %s is empty after cleaning — skipping.", filename)

    return chunk


# ── Row iteration ─────────────────────────────────────────────────────────────

def iter_rows(
    csv_files: list[Path],
    chunksize: int = 10_000,
) -> Iterator[tuple[str, pd.Series]]:
    """
    Yield (source_filename, row_series) for every cleaned row across all CSVs,
    looping continuously. Restarts from the first file when all are exhausted.

    Args:
        csv_files: Sorted list of CSV Paths to replay.
        chunksize: Rows per read_csv chunk — controls memory footprint.

    Yields:
        Tuple of (filename, pd.Series) for each surviving row after cleaning.
    """
    while not _shutdown:
        for csv_path in csv_files:
            if _shutdown:
                return
            log.info("Starting replay of: %s", csv_path.name)
            try:
                for chunk in pd.read_csv(csv_path, chunksize=chunksize, low_memory=False):
                    if _shutdown:
                        return
                    cleaned = clean_chunk(chunk, csv_path.name)
                    for _, row in cleaned.iterrows():
                        if _shutdown:
                            return
                        yield csv_path.name, row
            except Exception as exc:
                log.error("Error reading %s: %s — skipping file.", csv_path.name, exc)
                continue

        if not _shutdown:
            log.info("All CSV files replayed — restarting from the first file.")


# ── Payload serialisation ─────────────────────────────────────────────────────

def row_to_payload(filename: str, row: pd.Series) -> dict[str, str]:
    """
    Convert a cleaned row Series to a flat string-valued dict for XADD.

    Redis stream fields must be strings. Numeric features are formatted with
    enough precision to round-trip through float parsing in prediction_consumer.
    The Label column is published as `label`; source CSV name as `source_file`.

    Args:
        filename: Source CSV filename — published as `source_file`.
        row:      Cleaned pd.Series with feature columns and a Label column.

    Returns:
        Flat dict[str, str] ready for stream_manager.xadd().
    """
    payload: dict[str, str] = {}

    for field, value in row.items():
        if field == "Label":
            payload["label"] = str(value).strip()
        else:
            # Format numeric values with enough precision to survive float parsing
            try:
                payload[str(field)] = f"{float(value):.6g}"
            except (ValueError, TypeError):
                payload[str(field)] = str(value)

    payload["source_file"] = filename
    return payload


# ── Main loop ─────────────────────────────────────────────────────────────────

def run() -> None:
    """
    Continuous flow replay loop. Publishes rows to argus:flows at STREAM_RATE
    packets per second. Logs progress every LOG_INTERVAL packets.
    Shuts down cleanly on KeyboardInterrupt or SIGTERM.
    """
    global _shutdown

    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("═" * 60)
    log.info("Argus-IDS — Flow Generator (Phase 6)")
    log.info("  Data dir    : %s", DATA_DIR)
    log.info("  Stream rate : %.1f packets/sec", STREAM_RATE)
    log.info("  Target stream: %s", STREAM_FLOWS)
    log.info("  Log interval : every %d packets", LOG_INTERVAL)
    log.info("═" * 60)

    csv_files = discover_csv_files(DATA_DIR)

    # Inter-packet sleep duration in seconds
    sleep_interval: float = 1.0 / STREAM_RATE if STREAM_RATE > 0 else 0.0

    packets_sent: int = 0
    packets_failed: int = 0
    loop_start: float = time.monotonic()

    try:
        for filename, row in iter_rows(csv_files):
            payload = row_to_payload(filename, row)
            message_id = xadd(STREAM_FLOWS, payload)

            if message_id is not None:
                packets_sent += 1
            else:
                packets_failed += 1

            if packets_sent % LOG_INTERVAL == 0 and packets_sent > 0:
                elapsed = time.monotonic() - loop_start
                effective_rate = packets_sent / elapsed if elapsed > 0 else 0.0
                log.info(
                    "Published %d packets  (failed=%d  effective_rate=%.1f pkt/s  "
                    "source=%s)",
                    packets_sent,
                    packets_failed,
                    effective_rate,
                    filename,
                )

            if sleep_interval > 0:
                time.sleep(sleep_interval)

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received — shutting down.")
        _shutdown = True

    elapsed_total = time.monotonic() - loop_start
    log.info("═" * 60)
    log.info("Flow generator stopped.")
    log.info("  Total published : %d", packets_sent)
    log.info("  Total failed    : %d", packets_failed)
    log.info("  Elapsed         : %.1f seconds", elapsed_total)
    log.info("═" * 60)


if __name__ == "__main__":
    run()