# filename: backend/core/model.py
# purpose: Load model artifacts from backend/model/ — ensemble_model.pkl only at
#          prediction time; rf/xgb are benchmarking artifacts (§6.1)
# governed by: §6.1 (model save locations)

from __future__ import annotations

import os
import joblib

# All paths resolved from env var or default — no hardcoded absolute paths
_MODEL_DIR: str = os.environ.get("ARGUS_MODEL_DIR", "backend/model")


def _model_path(filename: str) -> str:
    return os.path.join(_MODEL_DIR, filename)


def load_ensemble(
) -> object | None:
    """
    Load the calibrated RF+XGBoost ensemble (ensemble_model.pkl).
    This is the ONLY model loaded at prediction time (§6.1).
    """
    path = _model_path("ensemble_model.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_iso_forest() -> object | None:
    """Load the Isolation Forest model (iso_forest.pkl) for anomaly scoring."""
    path = _model_path("iso_forest.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_scaler() -> object | None:
    """
    Load the MinMaxScaler (scaler.pkl) fitted on training data only (§5.2 step 4).
    Must be applied to every input before prediction — never refit at inference time.
    """
    path = _model_path("scaler.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_features() -> list[str] | None:
    """Load the saved feature name list (rf_features.pkl)."""
    path = _model_path("rf_features.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def save_model(model: object, filename: str) -> None:
    """Persist any model artifact to backend/model/. Filename must be explicit."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    joblib.dump(model, _model_path(filename))


def save_features(feature_names: list[str]) -> None:
    """Persist the feature name list to backend/model/rf_features.pkl."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    joblib.dump(feature_names, _model_path("rf_features.pkl"))
