# train_model.py
# Purpose : Train RF + XGBoost soft-voting ensemble, calibrate with
#           CalibratedClassifierCV (isotonic, cv=5), save all artefacts
#           to backend/model/.
# Governs : §5 (dataset + preprocessing), §6, §6.1, §6.2, §6.3

import os
os.environ.setdefault("OMP_NUM_THREADS", "2")  # Limit OpenMP threads to prevent resource contention

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
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import (
    accuracy_score,
    auc,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_curve,
)
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier
from backend.core.data import load_multi_csv

# ---------------------------------------------------------------------------
# [CHANGED] Phase 1b trains from the designated temporal training files only.
# Mixed held-out evaluation is performed later by evaluate_held_out.py.
# ---------------------------------------------------------------------------
DATA_DIR: str = os.environ.get("ARGUS_DATA_DIR", "./Dataset")

TRAIN_FILES: list[str] = [
    "Tuesday-WorkingHours.pcap_ISCX.csv",
    "Wednesday-workingHours.pcap_ISCX.csv",
    "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
    "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv",
    "Friday-WorkingHours-Morning.pcap_ISCX.csv",
]

MODEL_DIR: str = os.environ.get("ARGUS_MODEL_DIR", "backend/model")

ENSEMBLE_FILE: str = os.path.join(MODEL_DIR, "ensemble_model.pkl")  # prediction
RF_FILE: str = os.path.join(MODEL_DIR, "rf_model.pkl")              # benchmark only
XGB_FILE: str = os.path.join(MODEL_DIR, "xgb_model.pkl")            # benchmark only
FEATURE_FILE: str = os.path.join(MODEL_DIR, "rf_features.pkl")

COLS_TO_DROP: list[str] = ["Flow ID", "Source IP", "Destination IP", "Timestamp"]

# PCA: off by default for primary results (§5.2 step 6)
USE_PCA: bool = os.environ.get("ARGUS_USE_PCA", "false").lower() == "true"
PCA_COMPONENTS: int = int(os.environ.get("ARGUS_PCA_COMPONENTS", "30"))
DRY_RUN: bool = os.environ.get("ARGUS_DRY_RUN", "false").lower() == "true"
INTERNAL_VALIDATION_FRACTION: float = float(
    os.environ.get("ARGUS_INTERNAL_VALIDATION_FRACTION", "0.2")
)

# Phase 1b's publication-quality accuracy is measured in Phase 1c on
# Dataset/held_out_eval.csv. This gate applies only to the internal validation
# slice retained for artefact compatibility and smoke-check plots.
MIN_ACCURACY: float = 0.80


# ---------------------------------------------------------------------------
# Step 1–3: Load + clean + label encode  (ported from prototype, §5.2)
# ---------------------------------------------------------------------------
def load_and_preprocess(filepath: str) -> tuple[pd.DataFrame, pd.Series]:
    """Load CSV, drop noise columns, handle inf/NaN, label-encode target."""
    print(f"[data] Loading: {filepath}")
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip()                        # prototype pattern
    df.replace([np.inf, -np.inf], np.nan, inplace=True)       # prototype pattern
    df.dropna(inplace=True)

    for col in COLS_TO_DROP:
        if col in df.columns:
            df.drop(col, axis=1, inplace=True)

    if "Label" not in df.columns:
        raise ValueError("Label column not found in dataset.")

    X = df.drop("Label", axis=1)
    y = df["Label"].apply(lambda v: 0 if v == "BENIGN" else 1)  # prototype pattern

    print(f"[data] Shape after cleaning: {X.shape}  |  "
          f"Benign: {(y == 0).sum()}  Attack: {(y == 1).sum()}")
    return X, y


def load_training_dataframe(
    filenames: list[str],
    data_dir: str,
) -> tuple[pd.DataFrame, list[dict[str, int | str]]]:
    """
    Load only the Phase 1b training files via load_multi_csv().

    load_multi_csv() accepts a directory, not a filename list. To keep
    backend/core/data.py unchanged, create a temporary directory containing
    symlinks to the selected training CSVs, then delegate all cleaning and
    common-schema alignment to load_multi_csv().
    """
    for fname in filenames:
        fpath = os.path.join(data_dir, fname)
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"[data] Expected training file not found: {fpath}")

    with tempfile.TemporaryDirectory(prefix="argus_train_files_") as temp_dir:
        symlink_names: dict[str, str] = {}
        for index, fname in enumerate(filenames):
            source = os.path.abspath(os.path.join(data_dir, fname))
            link_name = f"{index:02d}__{fname}"
            target = os.path.join(temp_dir, link_name)
            os.symlink(source, target)
            symlink_names[link_name] = fname

        combined_df, per_file_stats = load_multi_csv(temp_dir)

    for stat in per_file_stats:
        stat["filename"] = symlink_names.get(str(stat["filename"]), stat["filename"])

    print(
        f"[data] Phase 1b loaded {len(filenames)} training files only. "
        "Dataset/held_out_eval.csv is reserved for Phase 1c evaluation."
    )
    return combined_df, per_file_stats


def split_training_dataframe_by_file(
    combined_df: pd.DataFrame,
    per_file_stats: list[dict[str, int | str]],
    train_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Keep temporal order inside each Phase 1b training file. Early rows train the
    model; later rows form an internal validation slice for compatibility
    artefacts and plots. The mixed held-out CSV is never loaded here.
    """
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("Internal train fraction must be between 0 and 1.")

    if "Label" not in combined_df.columns:
        raise ValueError("Label column not found in combined training dataframe.")

    X_train_parts: list[pd.DataFrame] = []
    X_test_parts: list[pd.DataFrame] = []
    y_train_parts: list[pd.Series] = []
    y_test_parts: list[pd.Series] = []

    cursor = 0
    for stat in per_file_stats:
        fname = str(stat["filename"])
        row_count = int(stat["total_rows"])
        file_df = combined_df.iloc[cursor:cursor + row_count].copy()
        cursor += row_count

        if file_df.empty:
            raise ValueError(f"[data] No usable rows after cleaning for {fname}.")

        split_idx = int(len(file_df) * train_fraction)
        if split_idx <= 0 or split_idx >= len(file_df):
            raise ValueError(
                f"[data] Invalid internal validation split for {fname}: "
                f"{split_idx}/{len(file_df)}"
            )

        y_file = file_df["Label"].apply(lambda v: 0 if str(v).strip().upper() == "BENIGN" else 1)
        X_file = file_df.drop("Label", axis=1)

        X_train_file = X_file.iloc[:split_idx].copy()
        X_test_file = X_file.iloc[split_idx:].copy()
        y_train_file = y_file.iloc[:split_idx].copy()
        y_test_file = y_file.iloc[split_idx:].copy()

        X_train_parts.append(X_train_file)
        X_test_parts.append(X_test_file)
        y_train_parts.append(y_train_file)
        y_test_parts.append(y_test_file)

        print(
            f"[split:file] {fname}  train={len(X_train_file)} "
            f"(benign={(y_train_file == 0).sum()} attack={(y_train_file == 1).sum()})  "
            f"test={len(X_test_file)} "
            f"(benign={(y_test_file == 0).sum()} attack={(y_test_file == 1).sum()})"
        )

    X_train = pd.concat(X_train_parts, ignore_index=True)
    X_test = pd.concat(X_test_parts, ignore_index=True)
    y_train = pd.concat(y_train_parts, ignore_index=True)
    y_test = pd.concat(y_test_parts, ignore_index=True)

    print(
        f"[data] Phase 1b internal temporal validation split — "
        f"{len(per_file_stats)} train files  |  "
        f"Train: {X_train.shape}  Benign: {(y_train == 0).sum()}  "
        f"Attack: {(y_train == 1).sum()}  |  "
        f"Validation: {X_test.shape}  Benign: {(y_test == 0).sum()}  "
        f"Attack: {(y_test == 1).sum()}"
    )
    return X_train, X_test, y_train, y_test


# ---------------------------------------------------------------------------
# Step 4–6: Normalise, SMOTE, optional PCA  (§5.1, §5.2)
# [CHANGED] prepare_splits no longer performs train/test split internally.
# It now receives pre-split X_train / X_test / y_train / y_test from the
# temporal file-based split performed in main(). train_test_split() removed.
# ---------------------------------------------------------------------------
def prepare_splits(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    np.ndarray,
    np.ndarray,
    list[str],
    MinMaxScaler,
    PCA | None,
    list[str],
]:
    """
    Min-max normalise (fit on train only) → SMOTE on train only
    → optional PCA. Returns DataFrames ready for model training.
    """
    os.makedirs(MODEL_DIR, exist_ok=True)

    raw_feature_names: list[str] = X_train.columns.tolist()
    model_feature_names: list[str] = raw_feature_names

    missing_test_features = [
        feature for feature in raw_feature_names if feature not in X_test.columns
    ]
    if missing_test_features:
        raise ValueError(
            "Test partition is missing training features: "
            f"{missing_test_features}"
        )

    extra_test_features = [
        feature for feature in X_test.columns if feature not in raw_feature_names
    ]
    if extra_test_features:
        print(
            "[schema] Dropping test-only columns not present in training schema: "
            f"{extra_test_features}"
        )
        X_test = X_test[raw_feature_names]

    print(f"[split] Train: {len(X_train)}  Test: {len(X_test)}")

    X_test_raw = X_test.copy()
    joblib.dump(X_test_raw, os.path.join(MODEL_DIR, "X_test_raw.pkl"))

    # §5.2 step 4 — min-max normalisation (fit on train, transform both)
    scaler = MinMaxScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    print("[preprocess] Min-max normalisation applied.")

    # §5.2 step 5 — Under-sample majority THEN SMOTE on training partition only
    resample_pipeline = ImbPipeline(steps=[
        ("under", RandomUnderSampler(random_state=42)),
        ("smote", SMOTE(random_state=42)),
    ])
    X_train_res, y_train_res = resample_pipeline.fit_resample(X_train_scaled, y_train)
    print(
        f"[smote] Under+SMOTE resampling applied — "
        f"Benign: {(y_train_res == 0).sum()}  "
        f"Attack: {(y_train_res == 1).sum()}"
    )

    pca: PCA | None = None
    if USE_PCA:
        print(f"[pca] Applying PCA — n_components={PCA_COMPONENTS}")
        pca = PCA(n_components=PCA_COMPONENTS, random_state=42)
        X_train_res = pca.fit_transform(X_train_res)
        X_test_scaled = pca.transform(X_test_scaled)
        explained = pca.explained_variance_ratio_.sum()
        model_feature_names = [f"PC{i+1}" for i in range(PCA_COMPONENTS)]
        print(f"[pca] Variance explained: {explained:.3%}")
    else:
        print("[pca] PCA skipped (default). Set ARGUS_USE_PCA=true to enable.")

    X_train_res_df = pd.DataFrame(
        X_train_res,
        columns=model_feature_names,
    )
    X_test_scaled_df = pd.DataFrame(
        X_test_scaled,
        columns=model_feature_names,
        index=X_test.index,
    )
    joblib.dump(X_test_scaled_df, os.path.join(MODEL_DIR, "X_test.pkl"))

    return (
        X_train_res_df,
        X_test_scaled_df,
        y_train_res,
        y_test.to_numpy(),
        raw_feature_names,
        scaler,
        pca,
        model_feature_names,
    )


# ---------------------------------------------------------------------------
# Model training — RF + XGBoost + soft-voting ensemble (§3.4, §6)
# ---------------------------------------------------------------------------
def train_models(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
) -> tuple[RandomForestClassifier, XGBClassifier, VotingClassifier]:
    """Train RF and XGBoost individually, then combine into soft-voting ensemble."""

    print("[train] Fitting RandomForestClassifier ...")
    rf = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        n_jobs=2,
    )
    rf.fit(X_train, y_train)
    print("[train] RF done.")

    print("[train] Fitting XGBClassifier ...")
    xgb = XGBClassifier(
        n_estimators=100,
        random_state=42,
        n_jobs=2,
        eval_metric="logloss",
        verbosity=0,
    )
    xgb.fit(X_train, y_train)
    print("[train] XGBoost done.")

    ensemble = VotingClassifier(
        estimators=[("rf", rf), ("xgb", xgb)],
        voting="soft",
    )
    ensemble.fit(X_train, y_train)
    print("[train] Soft-voting ensemble assembled.")

    return rf, xgb, ensemble


# ---------------------------------------------------------------------------
# Calibration — CalibratedClassifierCV isotonic cv=5 (§6.3)
# ---------------------------------------------------------------------------
def calibrate_ensemble(
    ensemble: VotingClassifier,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
) -> CalibratedClassifierCV:
    """
    Wrap ensemble in CalibratedClassifierCV (isotonic, cv=5).
    This is the ONLY artefact loaded at prediction time (§6.1).
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
# [NEW] k-fold cross-validation reporting (§3.1, §12.1)
# Runs stratified 5-fold CV on the uncalibrated VotingClassifier against
# SMOTE-balanced training data. Results printed and returned for metadata.
# ---------------------------------------------------------------------------
def run_cross_validation(
    ensemble: VotingClassifier,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    cv: int = 5,
) -> dict:
    """
    Stratified k-fold CV on uncalibrated ensemble, SMOTE-balanced train data.
    Returns dict with mean, std, and per-fold scores for metadata.json.
    """
    print(f"[cv] Running stratified {cv}-fold cross-validation on uncalibrated ensemble ...")
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

    return {
        "mean": mean_score,
        "std": std_score,
        "folds": fold_scores,
    }


# ---------------------------------------------------------------------------
# Evaluation + accuracy gate (§6.2)
# ---------------------------------------------------------------------------
def evaluate_and_report(
    label: str,
    model: object,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
) -> float:
    """Print classification report, return accuracy. Warns if below §6.2 floor."""
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n[eval] {label}")
    print(
        classification_report(
            y_test,
            y_pred,
            labels=[0, 1],
            target_names=["BENIGN", "ATTACK"],
            zero_division=0,
        )
    )
    print(f"[eval] Accuracy: {acc:.4%}")

    if acc < MIN_ACCURACY:
        print(
            f"[WARN] Accuracy {acc:.4%} is BELOW the §3.1 minimum of "
            f"{MIN_ACCURACY:.0%}. Revisit preprocessing before proceeding."
        )
    else:
        print(f"[eval] Accuracy gate passed (≥{MIN_ACCURACY:.0%}).")

    return acc


# ---------------------------------------------------------------------------
# Save artefacts (§6.1)
# [CHANGED] cv_scores added to metadata.json under key "cv_scores" (§12.1).
# dataset_source now records temporal split file lists.
# ---------------------------------------------------------------------------
def save_artefacts(
    calibrated_ensemble: CalibratedClassifierCV,
    rf: RandomForestClassifier,
    xgb: XGBClassifier,
    raw_feature_names: list[str],
    model_feature_names: list[str],
    scaler: MinMaxScaler,
    pca: PCA | None,
    X_test_scaled: pd.DataFrame,
    y_test: np.ndarray,
    raw_X_test: pd.DataFrame,
    y_train_res: np.ndarray,
    raw_train_count: int,
    raw_test_count: int,
    smote_train_count: int,
    smote_counts: dict[str, int],
    trained_at: str,
    rf_accuracy: float,
    xgb_accuracy: float,
    ensemble_raw_accuracy: float,
    calibrated_accuracy: float,
    dataset_source: dict,
    cv_scores: dict,
) -> None:
    """
    Save all model artefacts to MODEL_DIR.
    ensemble_model.pkl  — prediction artefact (calibrated, §6.1)
    rf_model.pkl        — benchmarking only (§6.1)
    xgb_model.pkl       — benchmarking only (§6.1)
    rf_features.pkl     — raw feature name list
    model_features.pkl  — model input schema (PCA components or raw features)
    scaler.pkl          — MinMaxScaler for inference-time normalisation
    pca.pkl             — fitted PCA transform for inference-time projection
    metadata.json       — training configuration and metric summary
    y_test.pkl          — ground truth labels for threshold tuning
    """
    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump(calibrated_ensemble, ENSEMBLE_FILE)
    print(f"[save] ensemble_model.pkl → {ENSEMBLE_FILE}")

    joblib.dump(rf, RF_FILE)
    print(f"[save] rf_model.pkl       → {RF_FILE}  (benchmark only)")

    joblib.dump(xgb, XGB_FILE)
    print(f"[save] xgb_model.pkl      → {XGB_FILE}  (benchmark only)")

    joblib.dump(raw_feature_names, FEATURE_FILE)
    print(f"[save] rf_features.pkl    → {FEATURE_FILE}")

    model_feature_file = os.path.join(MODEL_DIR, "model_features.pkl")
    joblib.dump(model_feature_names, model_feature_file)
    print(f"[save] model_features.pkl → {model_feature_file}")

    scaler_path = os.path.join(MODEL_DIR, "scaler.pkl")
    joblib.dump(scaler, scaler_path)
    print(f"[save] scaler.pkl         → {scaler_path}")

    if pca is not None:
        pca_path = os.path.join(MODEL_DIR, "pca.pkl")
        joblib.dump(pca, pca_path)
        print(f"[save] pca.pkl            → {pca_path}")

    joblib.dump(raw_X_test, os.path.join(MODEL_DIR, "X_test_raw.pkl"))
    print(f"[save] X_test_raw.pkl     → {os.path.join(MODEL_DIR, 'X_test_raw.pkl')}")

    y_test_path = os.path.join(MODEL_DIR, "y_test.pkl")
    joblib.dump(y_test, y_test_path)
    print(f"[save] y_test.pkl         → {y_test_path}")

    metadata = {
        "trained_at": trained_at,
        "ARGUS_USE_PCA": USE_PCA,
        "ARGUS_PCA_COMPONENTS": PCA_COMPONENTS,
        "ARGUS_CONTAMINATION": os.environ.get("ARGUS_CONTAMINATION"),
        "train_count": raw_train_count,
        "test_count": raw_test_count,
        "smote_train_count": smote_train_count,
        "smote_class_counts": smote_counts,
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
                "eval_metric": xgb.get_params().get("eval_metric"),
            },
            "ensemble": {"voting": "soft"},
        },
        "raw_accuracy": {
            "random_forest": float(rf_accuracy),
            "xgboost": float(xgb_accuracy),
            "ensemble": float(ensemble_raw_accuracy),
        },
        "calibrated_accuracy": float(calibrated_accuracy),
        "calibration_status": "isotonic applied",
        "cv_scores": cv_scores,
        "model_feature_names": model_feature_names,
        "dataset_source": dataset_source,
    }

    metadata_path = os.path.join(MODEL_DIR, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=2)
    print(f"[save] metadata.json     → {metadata_path}")


# ---------------------------------------------------------------------------
# Feature importance (ported from prototype — RF only)
# ---------------------------------------------------------------------------
def print_feature_importance(
    rf: RandomForestClassifier,
    feature_names: list[str],
    top_n: int = 15,
) -> None:
    """Print top-N RF feature importances (prototype pattern, §6)."""
    pairs = sorted(
        zip(feature_names, rf.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    print(f"\n[importance] Top {top_n} RF feature importances:")
    for name, score in pairs[:top_n]:
        print(f"  {name:<45} {score:.4f}")


def _save_training_plots(
    model,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    raw_model,
    calibrated_model,
) -> None:
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(6, 5))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("Confusion Matrix")
    plt.colorbar()
    plt.xticks([0, 1], ["BENIGN", "ATTACK"])
    plt.yticks([0, 1], ["BENIGN", "ATTACK"])
    plt.xlabel("Predicted label")
    plt.ylabel("True label")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(j, i, cm[i, j], ha="center", va="center", color="white")
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, "confusion_matrix.png"), dpi=150)
    plt.close()

    fpr, tpr, _ = roc_curve(y_test, y_prob)
    plt.figure(figsize=(6, 5))
    plt.plot(fpr, tpr, label=f"AUC = {auc(fpr, tpr):.4f}")
    plt.plot([0, 1], [0, 1], color="navy", linestyle="--")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curve")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, "roc_curve.png"), dpi=150)
    plt.close()

    precision_curve, recall_curve, _ = precision_recall_curve(y_test, y_prob)
    plt.figure(figsize=(6, 5))
    plt.plot(recall_curve, precision_curve, color="darkorange")
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Precision-Recall Curve")
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, "precision_recall_curve.png"), dpi=150)
    plt.close()

    raw_prob = raw_model.predict_proba(X_test)[:, 1]
    calibrated_prob = calibrated_model.predict_proba(X_test)[:, 1]
    raw_true, raw_pred = calibration_curve(y_test, raw_prob, n_bins=10)
    calib_true, calib_pred = calibration_curve(y_test, calibrated_prob, n_bins=10)

    plt.figure(figsize=(6, 5))
    plt.plot(raw_pred, raw_true, marker="o", label="Raw ensemble")
    plt.plot(calib_pred, calib_true, marker="o", label="Calibrated ensemble")
    plt.plot([0, 1], [0, 1], linestyle="--", color="gray")
    plt.xlabel("Mean predicted probability")
    plt.ylabel("Fraction of positives")
    plt.title("Calibration Curve")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, "calibration_curve.png"), dpi=150)
    plt.close()


def main() -> None:
    # ── Cache paths ──────────────────────────────────────────────────────────
    split_cache_prefix = "cache_phase1b_train_files"
    CACHE_X_TRAIN = os.path.join(MODEL_DIR, f"{split_cache_prefix}_X_train_smoted.pkl")
    CACHE_X_TEST = os.path.join(MODEL_DIR, f"{split_cache_prefix}_X_test_scaled.pkl")
    CACHE_Y_TRAIN = os.path.join(MODEL_DIR, f"{split_cache_prefix}_y_train.pkl")
    CACHE_Y_TEST = os.path.join(MODEL_DIR, f"{split_cache_prefix}_y_test.pkl")
    USE_CACHE: bool = os.environ.get("ARGUS_USE_CACHE", "false").lower() == "true"

    # ── Dry-run mode ─────────────────────────────────────────────────────────
    # [CHANGED] Dry-run now uses the first TRAIN file rather than a directory
    # scan, consistent with temporal split approach.
    if DRY_RUN:
        dry_file = os.path.join(DATA_DIR, TRAIN_FILES[0])
        print(f"[dry-run] Validating schema on first train file: {dry_file}")

        X_dry, y_dry = load_and_preprocess(dry_file)

        # Fabricate a minimal test partition from a slice so prepare_splits works
        split_idx = int(len(X_dry) * 0.8)
        X_dry_train = X_dry.iloc[:split_idx].copy()
        X_dry_test = X_dry.iloc[split_idx:].copy()
        y_dry_train = y_dry.iloc[:split_idx].copy()
        y_dry_test = y_dry.iloc[split_idx:].copy()

        original_joblib_dump = joblib.dump
        joblib.dump = lambda *args, **kwargs: None
        try:
            (
                X_train,
                X_test,
                y_train_res,
                y_test,
                feature_names,
                scaler,
                pca,
                model_feature_names,
            ) = prepare_splits(X_dry_train, X_dry_test, y_dry_train, y_dry_test)
        finally:
            joblib.dump = original_joblib_dump

        print(f"[dry-run] Feature list: {feature_names}")
        print(
            f"[dry-run] Schema OK — X_train={X_train.shape}, X_test={X_test.shape}, "
            f"features={len(feature_names)}"
        )
        print(
            "[dry-run] Schema OK — re-run without ARGUS_DRY_RUN=true for full training"
        )
        sys.exit(0)

    dataset_source: dict = {}
    cache_loaded = False
    raw_train_count = 0
    raw_test_count = 0

    if USE_CACHE and all(
        os.path.exists(path)
        for path in (CACHE_X_TRAIN, CACHE_X_TEST, CACHE_Y_TRAIN, CACHE_Y_TEST)
    ):
        print("[cache] Loaded cached splits — skipping CSV load and SMOTE")
        X_train = joblib.load(CACHE_X_TRAIN)
        X_test = joblib.load(CACHE_X_TEST)
        y_train_res = joblib.load(CACHE_Y_TRAIN)
        y_test = joblib.load(CACHE_Y_TEST)

        rf_features_path = os.path.join(MODEL_DIR, "rf_features.pkl")
        if os.path.exists(rf_features_path):
            feature_names = joblib.load(rf_features_path)
        else:
            feature_names = X_train.columns.tolist()

        model_feature_names = X_train.columns.tolist()
        scaler_path = os.path.join(MODEL_DIR, "scaler.pkl")
        scaler = joblib.load(scaler_path) if os.path.exists(scaler_path) else MinMaxScaler()
        pca_path = os.path.join(MODEL_DIR, "pca.pkl")
        pca = joblib.load(pca_path) if os.path.exists(pca_path) else None

        dataset_source = {
            "mode": "cache",
            "cache_files": [
                os.path.basename(CACHE_X_TRAIN),
                os.path.basename(CACHE_X_TEST),
                os.path.basename(CACHE_Y_TRAIN),
                os.path.basename(CACHE_Y_TEST),
            ],
        }
        raw_train_count = len(X_train)
        raw_test_count = len(X_test)
        cache_loaded = True
    else:
        train_fraction = 1.0 - INTERNAL_VALIDATION_FRACTION
        print("[data] Phase 1b — loading designated temporal training files ...")
        combined_df, per_file_stats = load_training_dataframe(TRAIN_FILES, DATA_DIR)
        X_train_raw, X_test_raw_df, y_train_raw, y_test_raw = split_training_dataframe_by_file(
            combined_df,
            per_file_stats,
            train_fraction,
        )

        dataset_source = {
            "mode": "phase_1b_train_files_only",
            "data_dir": DATA_DIR,
            "train_files": TRAIN_FILES,
            "held_out_eval_file": os.path.join(DATA_DIR, "held_out_eval.csv"),
            "held_out_eval_usage": "reserved_for_phase_1c_not_loaded_by_training",
            "internal_validation_fraction": INTERNAL_VALIDATION_FRACTION,
            "loaded_files": per_file_stats,
        }

        (
            X_train,
            X_test,
            y_train_res,
            y_test,
            feature_names,
            scaler,
            pca,
            model_feature_names,
        ) = prepare_splits(X_train_raw, X_test_raw_df, y_train_raw, y_test_raw)

        raw_train_count = len(X_train_raw)
        raw_test_count = len(X_test_raw_df)

        os.makedirs(MODEL_DIR, exist_ok=True)
        joblib.dump(X_train, CACHE_X_TRAIN)
        joblib.dump(X_test, CACHE_X_TEST)
        joblib.dump(y_train_res, CACHE_Y_TRAIN)
        joblib.dump(y_test, CACHE_Y_TEST)
        print(f"[cache] Splits cached to {MODEL_DIR}/")

    if cache_loaded:
        if not os.path.exists(os.path.join(MODEL_DIR, "X_test_raw.pkl")):
            raise FileNotFoundError(
                "Cached splits loaded, but X_test_raw.pkl is missing from MODEL_DIR. "
                "Run train_model.py once without ARGUS_USE_CACHE=true to create artefacts."
            )

    rf, xgb, ensemble = train_models(X_train, y_train_res)

    # [NEW] k-fold CV on uncalibrated ensemble before calibration (§3.1, §12.1)
    cv_scores = run_cross_validation(ensemble, X_train, y_train_res, cv=5)

    rf_accuracy = evaluate_and_report("Random Forest (raw)", rf, X_test, y_test)
    xgb_accuracy = evaluate_and_report("XGBoost (raw)", xgb, X_test, y_test)
    ensemble_raw_accuracy = evaluate_and_report(
        "Ensemble — soft voting (raw)",
        ensemble,
        X_test,
        y_test,
    )

    calibrated_ensemble = calibrate_ensemble(ensemble, X_train, y_train_res)

    calibrated_accuracy = evaluate_and_report(
        "Ensemble — calibrated (isotonic cv=5) ← REPORT THIS NUMBER",
        calibrated_ensemble,
        X_test,
        y_test,
    )

    save_artefacts(
        calibrated_ensemble,
        rf,
        xgb,
        feature_names,
        model_feature_names,
        scaler,
        pca,
        X_test,
        y_test,
        joblib.load(os.path.join(MODEL_DIR, "X_test_raw.pkl")),
        y_train_res,
        raw_train_count,
        raw_test_count,
        len(y_train_res),
        {
            "benign": int((y_train_res == 0).sum()),
            "attack": int((y_train_res == 1).sum()),
        },
        datetime.now(timezone.utc).isoformat(),
        rf_accuracy,
        xgb_accuracy,
        ensemble_raw_accuracy,
        calibrated_accuracy,
        dataset_source,
        cv_scores,
    )

    _save_training_plots(
        calibrated_ensemble,
        X_test,
        y_test,
        ensemble,
        calibrated_ensemble,
    )

    if not USE_PCA:
        print_feature_importance(rf, feature_names)

    print("\n[done] train1_model.py Phase 1b complete. Check accuracy gate above before proceeding.")


if __name__ == "__main__":
    main()
