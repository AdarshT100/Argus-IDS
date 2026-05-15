# train_model.py
# Purpose : Train RF + XGBoost soft-voting ensemble, calibrate with
#           CalibratedClassifierCV (isotonic, cv=5), save all artefacts
#           to backend/model/.
# Governs : §5 (dataset + preprocessing), §6, §6.1, §6.2, §6.3

import os
import sys
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.metrics import classification_report, accuracy_score
from imblearn.over_sampling import SMOTE
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str], MinMaxScaler]:
    """
    80/20 stratified split → min-max normalise → SMOTE on train only
    → optional PCA.  Returns arrays ready for model training.
    """
    feature_names: list[str] = X.columns.tolist()

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

    # §5.2 step 6 — optional PCA (flag-controlled, default off)
    if USE_PCA:
        print(f"[pca] Applying PCA — n_components={PCA_COMPONENTS}")
        pca = PCA(n_components=PCA_COMPONENTS, random_state=42)
        X_train_res = pca.fit_transform(X_train_res)
        X_test_scaled = pca.transform(X_test_scaled)
        explained = pca.explained_variance_ratio_.sum()
        print(f"[pca] Variance explained: {explained:.3%}")
        # Feature names become PCA component labels when PCA is active
        feature_names = [f"PC{i+1}" for i in range(PCA_COMPONENTS)]
    else:
        print("[pca] PCA skipped (default). Set ARGUS_USE_PCA=true to enable.")

# adding this here for convenience — saves the scaled X_test for later use in API routes and simulation (§7)
    X_test_scaled_df = pd.DataFrame(
        X_test_scaled,
        columns=feature_names,
        index=X_test.index,
    )
    joblib.dump(X_test_scaled_df, os.path.join(MODEL_DIR, "X_test.pkl"))

    return X_train_res, X_test_scaled, y_train_res, y_test.to_numpy(), feature_names, scaler

# ---------------------------------------------------------------------------
# Model training — RF + XGBoost + soft-voting ensemble (§3.4, §6)
# ---------------------------------------------------------------------------
def train_models(
    X_train: np.ndarray,
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
    X_train: np.ndarray,
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
    X_test: np.ndarray,
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
    feature_names: list[str],
    scaler: MinMaxScaler,
) -> None:
    """
    Save all model artefacts to MODEL_DIR.
    ensemble_model.pkl  — prediction artefact (calibrated, §6.1)
    rf_model.pkl        — benchmarking only (§6.1)
    xgb_model.pkl       — benchmarking only (§6.1)
    rf_features.pkl     — feature name list
    scaler.pkl          — MinMaxScaler for inference-time normalisation
    """
    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump(calibrated_ensemble, ENSEMBLE_FILE)
    print(f"[save] ensemble_model.pkl → {ENSEMBLE_FILE}")

    joblib.dump(rf, RF_FILE)
    print(f"[save] rf_model.pkl       → {RF_FILE}  (benchmark only)")

    joblib.dump(xgb, XGB_FILE)
    print(f"[save] xgb_model.pkl      → {XGB_FILE}  (benchmark only)")

    joblib.dump(feature_names, FEATURE_FILE)
    print(f"[save] rf_features.pkl    → {FEATURE_FILE}")

    scaler_path = os.path.join(MODEL_DIR, "scaler.pkl")
    joblib.dump(scaler, scaler_path)
    print(f"[save] scaler.pkl         → {scaler_path}")


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    X, y = load_and_preprocess(DATA_FILE)

    X_train, X_test, y_train, y_test, feature_names, scaler = prepare_splits(X, y)

    rf, xgb, ensemble = train_models(X_train, y_train)

    # Evaluate raw models before calibration (benchmarking reference)
    evaluate_and_report("Random Forest (raw)", rf, X_test, y_test)
    evaluate_and_report("XGBoost (raw)", xgb, X_test, y_test)
    evaluate_and_report("Ensemble — soft voting (raw)", ensemble, X_test, y_test)

    calibrated_ensemble = calibrate_ensemble(ensemble, X_train, y_train)

    # Evaluate calibrated ensemble — this is the number that goes in the report
    evaluate_and_report(
        "Ensemble — calibrated (isotonic cv=5) ← REPORT THIS NUMBER",
        calibrated_ensemble,
        X_test,
        y_test,
    )

    save_artefacts(calibrated_ensemble, rf, xgb, feature_names, scaler)

    if not USE_PCA:
        print_feature_importance(rf, feature_names)

    print("\n[done] train_model.py complete. Check accuracy gate above before proceeding.")


if __name__ == "__main__":
    main()