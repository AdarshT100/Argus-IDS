# filename: backend/core/model.py
# purpose: Load model artifacts from backend/model/ — ensemble_model.pkl only at
#          prediction time; rf/xgb are benchmarking artifacts (§6.1)


from __future__ import annotations

import json
import os
import joblib
import numpy as np
import pandas as pd


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
    """Load the saved raw feature name list (rf_features.pkl)."""
    path = _model_path("rf_features.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_model_features() -> list[str] | None:
    """Load the saved model input feature names (model_features.pkl)."""
    path = _model_path("model_features.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_pca() -> object | None:
    """Load the saved PCA transformer (pca.pkl) if present."""
    path = _model_path("pca.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_y_test() -> np.ndarray | None:
    """Load the saved ground truth y_test labels for threshold tuning."""
    path = _model_path("y_test.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_metadata() -> dict[str, object] | None:
    """Load training metadata and configuration summary."""
    path = _model_path("metadata.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as metadata_file:
        return json.load(metadata_file)


# Added load_X_test and load_X_test_raw to load saved X_test splits
# for API routes and simulation (§7).

def load_X_test() -> pd.DataFrame | None:
    """Load the scaled X_test DataFrame saved during training."""
    path = _model_path("X_test.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def load_X_test_raw() -> pd.DataFrame | None:
    """Load the unscaled X_test raw DataFrame saved before scaler application."""
    path = _model_path("X_test_raw.pkl")
    return joblib.load(path) if os.path.exists(path) else None


def save_model(model: object, filename: str) -> None:
    """Persist any model artifact to backend/model/. Filename must be explicit."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    joblib.dump(model, _model_path(filename))


def save_features(feature_names: list[str]) -> None:
    """Persist the feature name list to backend/model/rf_features.pkl."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    joblib.dump(feature_names, _model_path("rf_features.pkl"))
