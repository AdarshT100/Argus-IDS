# train_model.py
# Purpose : Train RF + XGBoost soft-voting ensemble, calibrate with
#           CalibratedClassifierCV (isotonic, cv=5), save all artefacts
#           to backend/model/.
# Governs : §5 (dataset + preprocessing), §6, §6.1, §6.2, §6.3

import json
import os
import sys
from datetime import datetime, timezone

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
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
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier

# ---------------------------------------------------------------------------
# Config — all paths via env var; no hardcoded paths (§6.1)
# ---------------------------------------------------------------------------
DATA_FILE: str = os.environ.get(
    "ARGUS_DATA_FILE",
    "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
)
MODEL_DIR: str = os.environ.get("ARGUS_MODEL_DIR", "backend/model")

ENSEMBLE_FILE: str = os.path.join(MODEL_DIR, "ensemble_model.pkl")  # prediction
RF_FILE: str = os.path.join(MODEL_DIR, "rf_model.pkl")              # benchmark only
XGB_FILE: str = os.path.join(MODEL_DIR, "xgb_model.pkl")            # benchmark only
FEATURE_FILE: str = os.path.join(MODEL_DIR, "rf_features.pkl")

COLS_TO_DROP: list[str] = ["Flow ID", "Source IP", "Destination IP", "Timestamp"]

# PCA: off by default for primary results (§5.2 step 6)
USE_PCA: bool = os.environ.get("ARGUS_USE_PCA", "false").lower() == "true"
PCA_COMPONENTS: int = int(os.environ.get("ARGUS_PCA_COMPONENTS", "30"))

MIN_ACCURACY: float = 0.95  # §6.2 — flag if below this


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

# ---------------------------------------------------------------------------
# Step 4–6: Split, normalise, SMOTE, optional PCA  (§5.1, §5.2)
# ---------------------------------------------------------------------------
def prepare_splits(
    X: pd.DataFrame,
    y: pd.Series,
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
    80/20 stratified split → min-max normalise → SMOTE on train only
    → optional PCA. Returns named DataFrames ready for model training.
    """
    os.makedirs(MODEL_DIR, exist_ok=True)

    raw_feature_names: list[str] = X.columns.tolist()
    model_feature_names: list[str] = raw_feature_names

    # §5.1 — 80/20 stratified split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )
    print(f"[split] Train: {len(X_train)}  Test: {len(X_test)}")

    X_test_raw = X_test.copy()
    joblib.dump(X_test_raw, os.path.join(MODEL_DIR, "X_test_raw.pkl"))

    # §5.2 step 4 — min-max normalisation (fit on train, transform both)
    scaler = MinMaxScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    print("[preprocess] Min-max normalisation applied.")

    # §5.2 step 5 — SMOTE on training split only, never on test
    smote = SMOTE(random_state=42)
    X_train_res, y_train_res = smote.fit_resample(X_train_scaled, y_train)
    print(
        f"[smote] After resampling — "
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

    # Random Forest — ported from prototype (§6)
    print("[train] Fitting RandomForestClassifier ...")
    rf = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    print("[train] RF done.")

    # XGBoost — new (§6); eval_metric suppresses default warning
    # FLAG: hyperparameters not specified in master reference — using
    #       symmetric defaults to RF. Revisit if accuracy < 95%.
    print("[train] Fitting XGBClassifier ...")
    xgb = XGBClassifier(
        n_estimators=100,
        random_state=42,
        n_jobs=-1,
        eval_metric="logloss",
        verbosity=0,
    )
    xgb.fit(X_train, y_train)
    print("[train] XGBoost done.")

    # Soft-voting ensemble — argmax of averaged predict_proba (§3.4)
    ensemble = VotingClassifier(
        estimators=[("rf", rf), ("xgb", xgb)],
        voting="soft",
    )
    # VotingClassifier must be re-fit; estimators already trained above
    # so this is fast — it delegates to the fitted sub-estimators.
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
    print(classification_report(y_test, y_pred, target_names=["BENIGN", "ATTACK"]))
    print(f"[eval] Accuracy: {acc:.4%}")

    if acc < MIN_ACCURACY:
        print(
            f"[WARN] Accuracy {acc:.4%} is BELOW the §6.2 minimum of "
            f"{MIN_ACCURACY:.0%}. Revisit preprocessing before proceeding."
        )
    else:
        print(f"[eval] Accuracy gate passed (≥{MIN_ACCURACY:.0%}).")

    return acc


# ---------------------------------------------------------------------------
# Save artefacts (§6.1)
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
        "model_feature_names": model_feature_names,
    }

    metadata_path = os.path.join(MODEL_DIR, "metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=2)
    print(f"[save] metadata.json     → {metadata_path}")


# ---------------------------------------------------------------------------
# Feature importance (ported from prototype — RF only, not available on
# calibrated ensemble wrapper)
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
    X, y = load_and_preprocess(DATA_FILE)

    (
        X_train,
        X_test,
        y_train_res,
        y_test,
        feature_names,
        scaler,
        pca,
        model_feature_names,
    ) = prepare_splits(X, y)

    rf, xgb, ensemble = train_models(X_train, y_train_res)

    # Evaluate raw models before calibration (benchmarking reference)
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
        len(X_train),
        len(X_test),
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

    print("\n[done] train_model.py complete. Check accuracy gate above before proceeding.")


if __name__ == "__main__":
    main()
