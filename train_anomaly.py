# train_anomaly.py
"""
Trains an Isolation Forest on benign-only traffic from CICIDS2017.

Environment variables (all optional — safe defaults shown):
    ARGUS_MODEL_DIR   Directory to read scaler.pkl from and write iso_forest.pkl to.
                      Default: backend/model
    ARGUS_DATA_FILE   Path to the CICIDS2017 CSV.
                      Default: Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv
    ARGUS_CONTAMINATION  Expected proportion of outliers in the dataset (float).
                         Default: 0.05
"""

import os
os.environ.setdefault("OMP_NUM_THREADS", "2")  # Limit OpenMP threads to prevent resource contention

import logging
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

# Column name for labels in the dataset; used for filtering benign rows.
_LABEL_COL: str = "Label"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config from environment ───────────────────────────────────────────────────
MODEL_DIR: str = os.environ.get("ARGUS_MODEL_DIR", "backend/model")
DATA_FILE: str = os.environ.get(
    "ARGUS_DATA_FILE",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
)

DATA_DIR: str | None = os.environ.get("ARGUS_DATA_DIR", None)

CONTAMINATION: float = float(os.environ.get("ARGUS_CONTAMINATION", "0.05"))

SCALER_PATH: str = os.path.join(MODEL_DIR, "scaler.pkl")
ISO_FOREST_PATH: str = os.path.join(MODEL_DIR, "iso_forest.pkl")
FEATURES_PATH: str = os.path.join(MODEL_DIR, "rf_features.pkl")

COLS_TO_DROP: list[str] = ["Flow ID", "Source IP", "Destination IP", "Timestamp"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_and_filter_benign(data_file: str, feature_names: list[str]) -> pd.DataFrame:
    """
    Load the dataset, apply §5.2 preprocessing steps 1-3, then return
    only the benign rows restricted to the trained feature columns.

    Preprocessing order mirrors train_model.py exactly:
        1. Drop non-informative columns
        2. Handle inf / NaN
        3. Label encode (filter step — keep BENIGN rows only)
    Min-max normalisation (step 4) is applied separately using the
    already-fitted scaler so the Isolation Forest sees the same
    feature space as the ensemble at inference time.
    """
    log.info("Loading dataset from: %s", data_file)

    if not os.path.exists(data_file):
        log.error("Dataset not found: %s", data_file)
        sys.exit(1)

    df = pd.read_csv(data_file)
    df.columns = df.columns.str.strip()

    # Step 1 — drop non-informative columns
    for col in COLS_TO_DROP:
        if col in df.columns:
            df.drop(col, axis=1, inplace=True)

    # Step 2 — replace inf with NaN, then drop
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)

    # Step 3 — keep benign rows only (label encode not needed; filtering by string)
    if "Label" not in df.columns:
        log.error("'Label' column not found in dataset.")
        sys.exit(1)

    benign_df = df[df["Label"].str.strip().str.upper() == "BENIGN"].copy()
    log.info("Benign rows after filtering: %d (of %d total)", len(benign_df), len(df))

    if len(benign_df) == 0:
        log.error("No benign rows found — check Label column values.")
        sys.exit(1)

    # Restrict to the exact feature set the ensemble was trained on
    missing = [f for f in feature_names if f not in benign_df.columns]
    if missing:
        log.error("Features missing from dataset: %s", missing)
        sys.exit(1)

    return benign_df[feature_names]

def filter_benign_from_df(
    df: pd.DataFrame,
    feature_names: list[str],
) -> pd.DataFrame:
    """
    Filter benign rows from an already-loaded and cleaned DataFrame.
    Used by the multi-file path where load_multi_csv() has already
    handled cleaning and concatenation.

    Args:
        df: Cleaned concatenated DataFrame with 'Label' column present.
        feature_names: Feature columns to restrict output to.

    Returns:
        DataFrame of benign rows restricted to feature_names columns.
    """
    if _LABEL_COL not in df.columns:
        log.error("'Label' column not found in provided DataFrame.")
        sys.exit(1)

    benign_df = df[df[_LABEL_COL].str.strip().str.upper() == "BENIGN"].copy()
    log.info("Benign rows after filtering: %d (of %d total)", len(benign_df), len(df))

    if len(benign_df) == 0:
        log.error("No benign rows found — check Label column values.")
        sys.exit(1)

    missing = [f for f in feature_names if f not in benign_df.columns]
    if missing:
        log.error("Features missing from DataFrame: %s", missing)
        sys.exit(1)

    return benign_df[feature_names]


def normalise_benign(
    X_benign: pd.DataFrame,
    scaler_path: str,
    feature_names: list[str],
) -> pd.DataFrame:
    """
    Apply the already-fitted MinMaxScaler from train_model.py.
    Never refit the scaler here — Isolation Forest must see the same
    scale as the ensemble at inference time.
    """
    if not os.path.exists(scaler_path):
        log.error(
            "scaler.pkl not found at %s — run train_model.py first.", scaler_path
        )
        sys.exit(1)

    scaler = joblib.load(scaler_path)
    log.info("Loaded scaler from: %s", scaler_path)

    X_scaled = pd.DataFrame(
        scaler.transform(X_benign),
        columns=feature_names,
        index=X_benign.index,
    )
    log.info("Normalisation applied — shape: %s", X_scaled.shape)
    return X_scaled

# ── Main ──────────────────────────────────────────────────────────────────────

def train_isolation_forest(
    X_scaled: pd.DataFrame,
    contamination: float,
) -> IsolationForest:
    """
    Fit Isolation Forest on scaled benign-only data.

    n_estimators=100  — matches RF/XGBoost choice for consistency.
    random_state=42   — reproducibility.
    contamination     — configurable via ARGUS_CONTAMINATION env var.
    n_jobs=-1         — use all cores; mirrors train_model.py convention.
    """
    log.info(
        "Training Isolation Forest — n_estimators=100, contamination=%.3f",
        contamination,
    )
    iso_forest = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=42,
        n_jobs=2,
    )
    iso_forest.fit(X_scaled)
    log.info("Isolation Forest training complete.")
    return iso_forest


def save_model(model: IsolationForest, path: str) -> None:
    """Persist the fitted Isolation Forest to backend/model/ (§6.1)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(model, path)
    log.info("iso_forest.pkl saved to: %s", path)


def print_summary(
    iso_forest: IsolationForest,
    X_scaled: pd.DataFrame,
) -> None:
    """
    Score the training data and report the anomaly flag distribution.
    predict() returns +1 (normal) or -1 (anomaly).
    On a benign-only training set the vast majority should be +1;
    the -1 fraction should approximate the contamination parameter.
    """
    preds = iso_forest.predict(X_scaled)
    normal_count = int((preds == 1).sum())
    anomaly_count = int((preds == -1).sum())
    total = len(preds)

    log.info("─" * 60)
    log.info("Training-set self-evaluation (benign data only):")
    log.info("  Normal  (+1): %d  (%.1f%%)", normal_count, 100 * normal_count / total)
    log.info("  Anomaly (-1): %d  (%.1f%%)", anomaly_count, 100 * anomaly_count / total)
    log.info("  Expected anomaly %%: ~%.1f%% (contamination param)", 100 * CONTAMINATION)
    log.info("─" * 60)

    # Sanity check — warn if anomaly rate diverges significantly from contamination
    observed_rate = anomaly_count / total
    if abs(observed_rate - CONTAMINATION) > 0.05:
        log.warning(
            "Observed anomaly rate (%.3f) differs from contamination (%.3f) by > 5%%. "
            "Consider tuning ARGUS_CONTAMINATION.",
            observed_rate,
            CONTAMINATION,
        )


if __name__ == "__main__":
    log.info("═" * 60)
    log.info("Argus-IDS — Isolation Forest Training")
    log.info("═" * 60)

    # 1. Load feature list from ensemble training artefact
    if not os.path.exists(FEATURES_PATH):
        log.error(
            "rf_features.pkl not found at %s — run train_model.py first.",
            FEATURES_PATH,
        )
        sys.exit(1)
    feature_names: list[str] = joblib.load(FEATURES_PATH)
    log.info("Loaded %d features from: %s", len(feature_names), FEATURES_PATH)

    # 2. Load and filter to benign rows — multi-file or single-file
    if DATA_DIR:
        log.info("Multi-file mode — loading from directory: %s", DATA_DIR)
        from backend.core.data import load_multi_csv
        combined_df = load_multi_csv(DATA_DIR, feature_list_override=feature_names)
        X_benign = filter_benign_from_df(combined_df, feature_names)
    else:
        log.info("Single-file mode — loading: %s", DATA_FILE)
        X_benign = load_and_filter_benign(DATA_FILE, feature_names)

    # 3. Normalise using the ensemble's scaler — never refit
    X_scaled = normalise_benign(X_benign, SCALER_PATH, feature_names)

    # 4. Fit
    iso_forest = train_isolation_forest(X_scaled, CONTAMINATION)

    # 5. Save to backend/model/ (§6.1)
    save_model(iso_forest, ISO_FOREST_PATH)

    # 6. Self-evaluation summary
    print_summary(iso_forest, X_scaled)

    log.info("Done. iso_forest.pkl is ready for the decision engine.")
