# train_multiclass.py
# Purpose : Train 6-class RF + XGBoost soft-voting ensemble, calibrate with
#           CalibratedClassifierCV (isotonic, cv=5), save multiclass_model.pkl
#           and multiclass_label_map.json to backend/model/.
#
# Label map:
#   0 → BENIGN
#   1 → DoS      (DoS Hulk, GoldenEye, slowloris, Slowhttptest, DDoS)
#   2 → PortScan
#   3 → BruteForce (FTP-Patator, SSH-Patator, Web Attack – Brute Force)
#   4 → WebAttack  (Web Attack – XSS, Web Attack – Sql Injection)
#   5 → Infiltration (Infiltration, Bot, Heartbleed)

import os
os.environ.setdefault("OMP_NUM_THREADS", "2")

import json
import sys
import tempfile
from datetime import datetime, timezone

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from imblearn.under_sampling import RandomUnderSampler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
)
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier

from backend.core.data import load_multi_csv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR: str = os.environ.get("ARGUS_DATA_DIR", "./Dataset")
MODEL_DIR: str = os.environ.get("ARGUS_MODEL_DIR", "backend/model")


HELD_OUT_FILENAME: str = "held_out_eval.csv"
TRAIN_FILES: list[str] = [
    f for f in sorted(os.listdir(DATA_DIR))
    if f.endswith(".csv") and f != HELD_OUT_FILENAME
]

# Output artefacts (§2.2, §5.3) — never overwrites binary artefacts
MULTICLASS_MODEL_FILE: str = os.path.join(MODEL_DIR, "multiclass_model.pkl")
LABEL_MAP_FILE: str = os.path.join(MODEL_DIR, "multiclass_label_map.json")

COLS_TO_DROP: list[str] = ["Flow ID", "Source IP", "Destination IP", "Timestamp"]

# Internal validation fraction — mirrors Phase 1b convention
INTERNAL_VALIDATION_FRACTION: float = float(
    os.environ.get("ARGUS_INTERNAL_VALIDATION_FRACTION", "0.2")
)

# Minimum macro-averaged accuracy gate for the calibrated multiclass model.
# Lower than binary because rare classes (Infiltration/Heartbleed) depress
# macro recall on the internal validation slice.
MIN_ACCURACY: float = float(os.environ.get("ARGUS_MC_MIN_ACCURACY", "0.75"))

DRY_RUN: bool = os.environ.get("ARGUS_DRY_RUN", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Label map (§2.3) — integer → display string
# Used at inference time by backend/core/model.py → load_label_map()
# ---------------------------------------------------------------------------
LABEL_MAP: dict[int, str] = {
    0: "BENIGN",
    1: "DoS",
    2: "PortScan",
    3: "BruteForce",
    4: "WebAttack",
    5: "Infiltration",
}

# Mapping from raw CICIDS2017 label strings → integer class ID (§2.3)
# All comparisons are performed after .strip().upper() normalisation.
_RAW_LABEL_TO_CLASS: dict[str, int] = {
    "BENIGN": 0,
    # DoS family — DDoS folded in (§2.3 rationale: mechanistically identical)
    "DOS HULK": 1,
    "DOS GOLDENEYE": 1,
    "DOS SLOWLORIS": 1,
    "DOS SLOWHTTPTEST": 1,
    "DDOS": 1,
    # PortScan
    "PORTSCAN": 2,
    # BruteForce family
    "FTP-PATATOR": 3,
    "SSH-PATATOR": 3,
# BruteForce family — dash is UTF-8 replacement char U+FFFD (\xef\xbf\xbd)
    "WEB ATTACK \ufffd BRUTE FORCE": 3,
    # WebAttack family
    "WEB ATTACK \ufffd XSS": 4,
    "WEB ATTACK \ufffd SQL INJECTION": 4,
    # Infiltration family — Heartbleed and Bot folded in (§2.3 rationale:
    # too sparse to train as standalone classes)
    "INFILTRATION": 5,
    "BOT": 5,
    "HEARTBLEED": 5,
}

CLASS_NAMES: list[str] = [LABEL_MAP[i] for i in range(len(LABEL_MAP))]
NUM_CLASSES: int = len(LABEL_MAP)


# ---------------------------------------------------------------------------
# Label encoding — raw CICIDS2017 string → 6-class integer
# ---------------------------------------------------------------------------
def encode_multiclass_label(raw_label: str) -> int | None:
    """
    Map a raw CICIDS2017 label string to a 6-class integer.
    Returns None for any label not covered by the label map — these rows
    are dropped with a warning so unknown variants never silently become
    the wrong class.
    """
    normalised = str(raw_label).strip().upper()
    return _RAW_LABEL_TO_CLASS.get(normalised, None)


def apply_label_encoding(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Apply multiclass label encoding to a dataframe with a 'Label' column.
    Drops rows whose label is not in the 6-class map and logs the count.
    Returns (X, y) with y as integer class IDs.
    """
    if "Label" not in df.columns:
        raise ValueError("Label column not found.")

    y_raw = df["Label"].apply(encode_multiclass_label)
    unknown_mask = y_raw.isna()
    unknown_count = unknown_mask.sum()
    if unknown_count > 0:
        unknown_labels = df.loc[unknown_mask, "Label"].unique().tolist()
        print(
            f"[label] WARNING — {unknown_count:,} rows dropped: "
            f"label(s) not in 6-class map: {unknown_labels}"
        )

    valid_mask = ~unknown_mask
    X = df.loc[valid_mask].drop("Label", axis=1)
    y = y_raw.loc[valid_mask].astype(int)

    print("[label] Class distribution after encoding:")
    for class_id, class_name in LABEL_MAP.items():
        count = (y == class_id).sum()
        print(f"         {class_id} ({class_name:<12}): {count:,}")

    return X, y


# ---------------------------------------------------------------------------
# Data loading — reuses load_multi_csv() via symlink temp dir
# Mirrors load_training_dataframe() from train_model.py exactly
# ---------------------------------------------------------------------------
def load_training_dataframe(
    filenames: list[str],
    data_dir: str,
) -> tuple[pd.DataFrame, list[dict[str, int | str]]]:
    """
    Load the Phase 1b / Phase 2 temporal training files via load_multi_csv().
    Uses a temporary symlink directory to pass a filename list to the
    directory-based load_multi_csv() without modifying data.py (§7).
    """
    for fname in filenames:
        fpath = os.path.join(data_dir, fname)
        if not os.path.exists(fpath):
            raise FileNotFoundError(
                f"[data] Expected training file not found: {fpath}"
            )

    with tempfile.TemporaryDirectory(prefix="argus_mc_train_files_") as temp_dir:
        symlink_names: dict[str, str] = {}
        for index, fname in enumerate(filenames):
            source = os.path.abspath(os.path.join(data_dir, fname))
            link_name = f"{index:02d}__{fname}"
            target = os.path.join(temp_dir, link_name)
            os.symlink(source, target)
            symlink_names[link_name] = fname

        combined_df, per_file_stats = load_multi_csv(temp_dir)

    for stat in per_file_stats:
        stat["filename"] = symlink_names.get(
            str(stat["filename"]), stat["filename"]
        )

    print(
        f"[data] Phase 2 loaded {len(filenames)} training files. "
        "Dataset/held_out_eval.csv is reserved for Phase 1c / evaluate_held_out.py."
    )
    return combined_df, per_file_stats


# ---------------------------------------------------------------------------
# Train / validation split — temporal within each file
# Mirrors split_training_dataframe_by_file() from train_model.py
# DIFFERENCE: y is 6-class integer, not binary
# ---------------------------------------------------------------------------
def split_by_file_temporal(
    combined_df: pd.DataFrame,
    per_file_stats: list[dict[str, int | str]],
    train_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Preserve temporal ordering within each file.
    Early rows → training; later rows → internal validation slice.
    Label encoding to 6-class integers is performed here.
    Rows with unmapped labels are dropped before splitting.
    """
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1.")

    # Apply multiclass label encoding to the full combined dataframe first
    X_all, y_all = apply_label_encoding(combined_df)

    X_train_parts: list[pd.DataFrame] = []
    X_test_parts: list[pd.DataFrame] = []
    y_train_parts: list[pd.Series] = []
    y_test_parts: list[pd.Series] = []

    # Rebuild per-file slices from the encoded (and potentially row-dropped)
    # dataframe. We track position using the original row counts from stats,
    # but must use the encoded index since some rows may have been dropped.
    # Strategy: re-split by iterating over the original file boundaries using
    # the original combined_df index, then intersecting with valid encoded rows.
    cursor = 0
    for stat in per_file_stats:
        fname = str(stat["filename"])
        row_count = int(stat["total_rows"])

        # Identify original indices for this file's slice in combined_df
        file_original_indices = combined_df.index[cursor: cursor + row_count]
        cursor += row_count

        # Intersect with rows that survived label encoding
        valid_indices = file_original_indices.intersection(X_all.index)

        if len(valid_indices) == 0:
            print(
                f"[split:file] WARNING — {fname}: no valid rows after label "
                "encoding. Skipping."
            )
            continue

        X_file = X_all.loc[valid_indices]
        y_file = y_all.loc[valid_indices]

        split_idx = int(len(X_file) * train_fraction)
        if split_idx <= 0 or split_idx >= len(X_file):
            raise ValueError(
                f"[split:file] Invalid internal validation split for {fname}: "
                f"{split_idx}/{len(X_file)}"
            )

        X_train_parts.append(X_file.iloc[:split_idx])
        X_test_parts.append(X_file.iloc[split_idx:])
        y_train_parts.append(y_file.iloc[:split_idx])
        y_test_parts.append(y_file.iloc[split_idx:])

        print(
            f"[split:file] {fname}  "
            f"valid={len(X_file):,}  "
            f"train={split_idx:,}  "
            f"val={len(X_file) - split_idx:,}"
        )

    X_train = pd.concat(X_train_parts, ignore_index=True)
    X_test = pd.concat(X_test_parts, ignore_index=True)
    y_train = pd.concat(y_train_parts, ignore_index=True)
    y_test = pd.concat(y_test_parts, ignore_index=True)

    print(
        f"[split] Total — Train: {X_train.shape}  Val: {X_test.shape}"
    )
    return X_train, X_test, y_train, y_test


# ---------------------------------------------------------------------------
# Preprocessing — load scaler read-only, SMOTE on train only (§10)
# CRITICAL: scaler.pkl is NEVER refit here. It was fitted once in
# train_model.py on the binary training data and must be applied read-only
# everywhere else (§10 hard constraint).
# ---------------------------------------------------------------------------
def preprocess(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    feature_names: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
    """
    1. Align feature columns to rf_features.pkl schema (fill missing with 0,
       drop extras — same fail-secure principle as §10 / §12.3).
    2. Apply scaler.pkl read-only (transform only — never fit).
    3. Apply Under-sample → SMOTE pipeline on training partition only.
    Returns scaled X_train (SMOTE-balanced), scaled X_test, y_train_res, y_test.
    """
    # Align to training schema
    def _align_features(X: pd.DataFrame, names: list[str], tag: str) -> pd.DataFrame:
        missing = [f for f in names if f not in X.columns]
        extra = [f for f in X.columns if f not in names]
        if missing:
            print(
                f"[schema:{tag}] Filling {len(missing)} missing feature(s) with 0: "
                f"{missing[:5]}{'...' if len(missing) > 5 else ''}"
            )
            for col in missing:
                X[col] = 0.0
        if extra:
            print(
                f"[schema:{tag}] Dropping {len(extra)} extra column(s) not in "
                f"training schema."
            )
        return X[names]

    X_train = _align_features(X_train.copy(), feature_names, "train")
    X_test = _align_features(X_test.copy(), feature_names, "val")

    # Load scaler read-only (§10 hard constraint)
    scaler_path = os.path.join(MODEL_DIR, "scaler.pkl")
    if not os.path.exists(scaler_path):
        raise FileNotFoundError(
            f"scaler.pkl not found at {scaler_path}. "
            "Run train_model.py (Phase 1b) before train_multiclass.py."
        )
    scaler: MinMaxScaler = joblib.load(scaler_path)
    print(f"[preprocess] Loaded scaler.pkl (read-only) from {scaler_path}")

    X_train_scaled = scaler.transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    print("[preprocess] MinMaxScaler applied (transform only — never refit).")

    # Under-sample majority then SMOTE — training partition only
    # For multiclass, RandomUnderSampler and SMOTE both support multi-class
    # natively when y has integer class labels 0–5.
    resample_pipeline = ImbPipeline(steps=[
        ("under", RandomUnderSampler(random_state=42)),
        ("smote", SMOTE(random_state=42)),
    ])
    X_train_res, y_train_res = resample_pipeline.fit_resample(
        X_train_scaled, y_train.to_numpy()
    )
    print("[smote] Under+SMOTE resampling complete. Class distribution after SMOTE:")
    for class_id, class_name in LABEL_MAP.items():
        count = (y_train_res == class_id).sum()
        print(f"         {class_id} ({class_name:<12}): {count:,}")

    X_train_res_df = pd.DataFrame(X_train_res, columns=feature_names)
    X_test_scaled_df = pd.DataFrame(
        X_test_scaled, columns=feature_names, index=X_test.index
    )

    return X_train_res_df, X_test_scaled_df, y_train_res, y_test.to_numpy()


# ---------------------------------------------------------------------------
# Model training — RF + XGBoost soft-voting (§2.2)
# ---------------------------------------------------------------------------
def train_models(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
) -> tuple[RandomForestClassifier, XGBClassifier, VotingClassifier]:
    """
    Train RF and XGBoost individually then combine into a soft-voting ensemble.
    Hyperparameters mirror the binary model (§2.2) with multiclass XGB params.
    """
    print("[train] Fitting RandomForestClassifier (multiclass) ...")
    rf = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        n_jobs=2,
    )
    rf.fit(X_train, y_train)
    print("[train] RF done.")

    print("[train] Fitting XGBClassifier (multi:softprob, num_class=6) ...")
    xgb = XGBClassifier(
        n_estimators=100,
        random_state=42,
        n_jobs=2,
        objective="multi:softprob",
        num_class=NUM_CLASSES,
        eval_metric="mlogloss",
        verbosity=0,
    )
    xgb.fit(X_train, y_train)
    print("[train] XGBoost done.")

    ensemble = VotingClassifier(
        estimators=[("rf", rf), ("xgb", xgb)],
        voting="soft",
    )
    ensemble.fit(X_train, y_train)
    print("[train] Soft-voting ensemble (multiclass) assembled.")

    return rf, xgb, ensemble


# ---------------------------------------------------------------------------
# k-fold cross-validation (§2.2 mirrors binary pattern, §12.1)
# ---------------------------------------------------------------------------
def run_cross_validation(
    ensemble: VotingClassifier,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    cv: int = 5,
) -> dict:
    """
    Stratified k-fold CV on the uncalibrated multiclass ensemble against
    SMOTE-balanced training data. Uses macro accuracy.
    """
    print(
        f"[cv] Running stratified {cv}-fold CV on uncalibrated multiclass ensemble ..."
    )
    scores = cross_val_score(
        ensemble,
        X_train,
        y_train,
        cv=cv,
        scoring="accuracy",
        n_jobs=2,
    )
    mean_score = float(scores.mean())
    std_score = float(scores.std())
    fold_scores = [float(s) for s in scores]

    print(f"[cv] Fold scores: {[f'{s:.4%}' for s in fold_scores]}")
    print(f"[cv] Mean accuracy: {mean_score:.4%}  ±  {std_score:.4%}")

    return {"mean": mean_score, "std": std_score, "folds": fold_scores}


# ---------------------------------------------------------------------------
# Calibration — CalibratedClassifierCV isotonic cv=5 (§2.2)
# ---------------------------------------------------------------------------
def calibrate_ensemble(
    ensemble: VotingClassifier,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
) -> CalibratedClassifierCV:
    """
    Wrap multiclass ensemble in CalibratedClassifierCV (isotonic, cv=5).
    This is the artefact saved as multiclass_model.pkl and loaded at
    inference time by backend/core/model.py → load_multiclass().
    """
    print("[calibrate] Fitting CalibratedClassifierCV (isotonic, cv=5) ...")
    calibrated = CalibratedClassifierCV(
        estimator=ensemble,
        method="isotonic",
        cv=5,
    )
    calibrated.fit(X_train, y_train)
    print("[calibrate] Calibration done.")
    return calibrated


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def evaluate_and_report(
    label: str,
    model: object,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
) -> float:
    """
    Print per-class classification report and overall accuracy.
    Returns accuracy. Warns if below MIN_ACCURACY gate.
    """
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    print(f"\n[eval] {label}")
    print(
        classification_report(
            y_test,
            y_pred,
            labels=list(range(NUM_CLASSES)),
            target_names=CLASS_NAMES,
            zero_division=0,
        )
    )
    print(f"[eval] Accuracy: {acc:.4%}")

    if acc < MIN_ACCURACY:
        print(
            f"[WARN] Accuracy {acc:.4%} is BELOW the multiclass minimum of "
            f"{MIN_ACCURACY:.0%}. Check class balance and label mapping."
        )
    else:
        print(f"[eval] Accuracy gate passed (≥{MIN_ACCURACY:.0%}).")

    return acc


def print_feature_importance(
    rf: RandomForestClassifier,
    feature_names: list[str],
    top_n: int = 15,
) -> None:
    """Print top-N RF feature importances for multiclass model."""
    pairs = sorted(
        zip(feature_names, rf.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    print(f"\n[importance] Top {top_n} RF feature importances (multiclass):")
    for name, score in pairs[:top_n]:
        print(f"  {name:<45} {score:.4f}")


# ---------------------------------------------------------------------------
# Save artefacts (§2.2, §5.3, §6.2)
# multiclass_model.pkl and multiclass_label_map.json only — never touches
# binary artefacts (ensemble_model.pkl, scaler.pkl, rf_features.pkl etc.)
# ---------------------------------------------------------------------------
def save_artefacts(
    calibrated_ensemble: CalibratedClassifierCV,
    rf: RandomForestClassifier,
    xgb: XGBClassifier,
    feature_names: list[str],
    raw_train_count: int,
    raw_val_count: int,
    smote_train_count: int,
    smote_class_counts: dict[str, int],
    trained_at: str,
    rf_accuracy: float,
    xgb_accuracy: float,
    ensemble_raw_accuracy: float,
    calibrated_accuracy: float,
    cv_scores: dict,
    dataset_source: dict,
    X_test_scaled: pd.DataFrame,
    y_test: np.ndarray,
) -> None:
    """
    Saves:
      multiclass_model.pkl         — calibrated 6-class ensemble (inference artefact)
      multiclass_label_map.json    — {int: label_string} map for backend model loader
      multiclass_metadata.json     — training config and metric summary
      multiclass_confusion_matrix.png
    """
    os.makedirs(MODEL_DIR, exist_ok=True)

    # Primary inference artefact
    joblib.dump(calibrated_ensemble, MULTICLASS_MODEL_FILE)
    print(f"[save] multiclass_model.pkl      → {MULTICLASS_MODEL_FILE}")

    # Label map — keys must be strings for JSON serialisation;
    # backend/core/model.py → load_label_map() converts keys back to int
    label_map_serialisable = {str(k): v for k, v in LABEL_MAP.items()}
    with open(LABEL_MAP_FILE, "w", encoding="utf-8") as lm_file:
        json.dump(label_map_serialisable, lm_file, indent=2)
    print(f"[save] multiclass_label_map.json → {LABEL_MAP_FILE}")

    # Metadata — mirrors binary metadata.json structure for consistency
    metadata = {
        "trained_at": trained_at,
        "model_type": "multiclass",
        "num_classes": NUM_CLASSES,
        "class_names": CLASS_NAMES,
        "label_map": label_map_serialisable,
        "train_count": raw_train_count,
        "val_count": raw_val_count,
        "smote_train_count": smote_train_count,
        "smote_class_counts": smote_class_counts,
        "hyperparameters": {
            "rf": {
                "n_estimators": rf.n_estimators,
                "random_state": rf.random_state,
                "n_jobs": rf.n_jobs,
            },
            "xgb": {
                "n_estimators": xgb.n_estimators,
                "random_state": xgb.random_state,
                "n_jobs": xgb.n_jobs,
                "objective": "multi:softprob",
                "num_class": NUM_CLASSES,
                "eval_metric": "mlogloss",
            },
            "ensemble": {"voting": "soft"},
            "calibration": {"method": "isotonic", "cv": 5},
        },
        "raw_accuracy": {
            "random_forest": float(rf_accuracy),
            "xgboost": float(xgb_accuracy),
            "ensemble": float(ensemble_raw_accuracy),
        },
        "calibrated_accuracy": float(calibrated_accuracy),
        "calibration_status": "isotonic applied",
        "cv_scores": cv_scores,
        "feature_count": len(feature_names),
        "scaler_source": "scaler.pkl (binary training — loaded read-only, never refit)",
        "dataset_source": dataset_source,
    }

    mc_metadata_path = os.path.join(MODEL_DIR, "multiclass_metadata.json")
    with open(mc_metadata_path, "w", encoding="utf-8") as mf:
        json.dump(metadata, mf, indent=2)
    print(f"[save] multiclass_metadata.json  → {mc_metadata_path}")

    # Confusion matrix plot
    y_pred = calibrated_ensemble.predict(X_test_scaled)
    cm = confusion_matrix(y_test, y_pred, labels=list(range(NUM_CLASSES)))
    fig, ax = plt.subplots(figsize=(8, 7))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASS_NAMES)
    disp.plot(ax=ax, colorbar=True, cmap="Blues", xticks_rotation=45)
    ax.set_title("Multiclass Confusion Matrix (Calibrated Ensemble)")
    plt.tight_layout()
    cm_path = os.path.join(MODEL_DIR, "multiclass_confusion_matrix.png")
    plt.savefig(cm_path, dpi=150)
    plt.close()
    print(f"[save] multiclass_confusion_matrix.png → {cm_path}")


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------
def main() -> None:
    # ── Cache paths ──────────────────────────────────────────────────────────
    split_cache_prefix = "cache_phase2_mc_train_files"
    CACHE_X_TRAIN = os.path.join(MODEL_DIR, f"{split_cache_prefix}_X_train_smoted.pkl")
    CACHE_X_TEST = os.path.join(MODEL_DIR, f"{split_cache_prefix}_X_test_scaled.pkl")
    CACHE_Y_TRAIN = os.path.join(MODEL_DIR, f"{split_cache_prefix}_y_train.pkl")
    CACHE_Y_TEST = os.path.join(MODEL_DIR, f"{split_cache_prefix}_y_test.pkl")
    USE_CACHE: bool = os.environ.get("ARGUS_USE_CACHE", "false").lower() == "true"

    # ── Verify TRAIN_FILES resolved correctly ────────────────────────────────
    if not TRAIN_FILES:
        print(f"[ERROR] No CSV files found in {DATA_DIR} (excluding held_out_eval.csv).")
        sys.exit(1)
    print(f"[init] Multiclass training files ({len(TRAIN_FILES)}):")
    for f in TRAIN_FILES:
        print(f"         {f}")
    if HELD_OUT_FILENAME in TRAIN_FILES:
        print("[ERROR] held_out_eval.csv is in the training file list. Aborting.")
        sys.exit(1)

    # ── Prerequisite check — scaler.pkl must exist before anything else ──────
    scaler_path = os.path.join(MODEL_DIR, "scaler.pkl")
    rf_features_path = os.path.join(MODEL_DIR, "rf_features.pkl")
    for required_path in (scaler_path, rf_features_path):
        if not os.path.exists(required_path):
            print(
                f"[ERROR] Required artefact missing: {required_path}\n"
                "        Run train_model.py (Phase 1b) to completion before "
                "train_multiclass.py."
            )
            sys.exit(1)

    # Load the binary model's feature list — multiclass uses the same schema
    feature_names: list[str] = joblib.load(rf_features_path)
    print(
        f"[init] Loaded rf_features.pkl — {len(feature_names)} features "
        f"(same schema as binary model)."
    )

    # ── Dry-run mode ─────────────────────────────────────────────────────────
    if DRY_RUN:
        dry_file = os.path.join(DATA_DIR, TRAIN_FILES[0])
        print(f"[dry-run] Schema validation on: {dry_file}")

        df_dry = pd.read_csv(dry_file, nrows=5000)
        df_dry.columns = df_dry.columns.str.strip()
        df_dry.replace([float("inf"), float("-inf")], float("nan"), inplace=True)
        df_dry.dropna(inplace=True)

        X_dry, y_dry = apply_label_encoding(df_dry)
        print(
            f"[dry-run] OK — features={X_dry.shape[1]}  "
            f"classes={y_dry.nunique()}  rows={len(X_dry)}"
        )
        print("[dry-run] Re-run without ARGUS_DRY_RUN=true for full training.")
        sys.exit(0)

    # ── Data loading and preprocessing ───────────────────────────────────────
    dataset_source: dict = {}
    raw_train_count = 0
    raw_val_count = 0

    if USE_CACHE and all(
        os.path.exists(p)
        for p in (CACHE_X_TRAIN, CACHE_X_TEST, CACHE_Y_TRAIN, CACHE_Y_TEST)
    ):
        print("[cache] Loading cached multiclass splits — skipping CSV load and SMOTE.")
        X_train = joblib.load(CACHE_X_TRAIN)
        X_test = joblib.load(CACHE_X_TEST)
        y_train_res = joblib.load(CACHE_Y_TRAIN)
        y_test = joblib.load(CACHE_Y_TEST)
        raw_train_count = len(X_train)
        raw_val_count = len(X_test)
        dataset_source = {
            "mode": "cache",
            "cache_files": [
                os.path.basename(CACHE_X_TRAIN),
                os.path.basename(CACHE_X_TEST),
                os.path.basename(CACHE_Y_TRAIN),
                os.path.basename(CACHE_Y_TEST),
            ],
        }
    else:
        train_fraction = 1.0 - INTERNAL_VALIDATION_FRACTION
        print("[data] Phase 2 — loading temporal training files for multiclass ...")
        combined_df, per_file_stats = load_training_dataframe(TRAIN_FILES, DATA_DIR)

        X_train_raw, X_test_raw, y_train_raw, y_test_raw = split_by_file_temporal(
            combined_df,
            per_file_stats,
            train_fraction,
        )

        raw_train_count = len(X_train_raw)
        raw_val_count = len(X_test_raw)

        dataset_source = {
            "mode": "phase_2_multiclass_train_files",
            "data_dir": DATA_DIR,
            "train_files": TRAIN_FILES,
            "internal_validation_fraction": INTERNAL_VALIDATION_FRACTION,
            "loaded_files": per_file_stats,
        }

        X_train, X_test, y_train_res, y_test = preprocess(
            X_train_raw,
            X_test_raw,
            y_train_raw,
            y_test_raw,
            feature_names,
        )

        os.makedirs(MODEL_DIR, exist_ok=True)
        joblib.dump(X_train, CACHE_X_TRAIN)
        joblib.dump(X_test, CACHE_X_TEST)
        joblib.dump(y_train_res, CACHE_Y_TRAIN)
        joblib.dump(y_test, CACHE_Y_TEST)
        print(f"[cache] Multiclass splits cached to {MODEL_DIR}/")

    # ── Training ──────────────────────────────────────────────────────────────
    rf, xgb, ensemble = train_models(X_train, y_train_res)

    # k-fold CV on uncalibrated ensemble (§2.2, §12.1)
    cv_scores = run_cross_validation(ensemble, X_train, y_train_res, cv=5)

    # Per-model evaluation on internal validation slice
    rf_accuracy = evaluate_and_report(
        "Random Forest — multiclass (raw)", rf, X_test, y_test
    )
    xgb_accuracy = evaluate_and_report(
        "XGBoost — multiclass (raw)", xgb, X_test, y_test
    )
    ensemble_raw_accuracy = evaluate_and_report(
        "Ensemble — soft voting (raw)", ensemble, X_test, y_test
    )

    # Calibration
    calibrated_ensemble = calibrate_ensemble(ensemble, X_train, y_train_res)

    calibrated_accuracy = evaluate_and_report(
        "Ensemble — calibrated (isotonic cv=5) ← REPORT THIS NUMBER",
        calibrated_ensemble,
        X_test,
        y_test,
    )

    # ── Save ──────────────────────────────────────────────────────────────────
    smote_class_counts = {
        LABEL_MAP[i]: int((y_train_res == i).sum())
        for i in range(NUM_CLASSES)
    }

    save_artefacts(
        calibrated_ensemble=calibrated_ensemble,
        rf=rf,
        xgb=xgb,
        feature_names=feature_names,
        raw_train_count=raw_train_count,
        raw_val_count=raw_val_count,
        smote_train_count=int(len(y_train_res)),
        smote_class_counts=smote_class_counts,
        trained_at=datetime.now(timezone.utc).isoformat(),
        rf_accuracy=rf_accuracy,
        xgb_accuracy=xgb_accuracy,
        ensemble_raw_accuracy=ensemble_raw_accuracy,
        calibrated_accuracy=calibrated_accuracy,
        cv_scores=cv_scores,
        dataset_source=dataset_source,
        X_test_scaled=X_test,
        y_test=y_test,
    )

    print_feature_importance(rf, feature_names)

    print(
        "\n[done] train_multiclass.py Phase 2 complete.\n"
        "       Artefacts saved:\n"
        f"         {MULTICLASS_MODEL_FILE}\n"
        f"         {LABEL_MAP_FILE}\n"
        "       Check calibrated accuracy above before proceeding to Phase 3."
    )


if __name__ == "__main__":
    main()