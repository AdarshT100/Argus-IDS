# filename: backend/api/routes.py
# purpose: /predict, /alerts, and /health endpoint definitions


from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import os
from typing import Deque

import numpy as np
import pandas as pd
import math
from fastapi import APIRouter, HTTPException


from backend.api.schemas import (
    AlertEntry,
    AlertsResponse,
    ExplainRequest,
    ExplainResponse,
    MulticlassPredictResponse,
    PredictRandomResponse,
    PredictRequest,
    PredictResponse,
    ShapFeature,
    SimulateRequest,
    SimulateResponse,
    SimulationsResponse,
    ThresholdMetricsResponse,
)
from backend.core.model import (
    load_features,
    load_ensemble,
    load_iso_forest,
    load_label_map,
    load_metadata,
    load_model_features,
    load_multiclass,
    load_pca,
    load_scaler,
    load_X_test,
    load_X_test_raw,
    load_y_test,
)
from backend.core.simulation import get_random_packet, predict_packet, simulate_window
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
from backend.services.alert_dispatcher import dispatch_alert
from backend.services.SHAP_explainer import (
    create_explainer,
    generate_shap_analysis,
    get_top_shap_features,
)

router = APIRouter()
METADATA_PATH = os.path.join(
    os.environ.get("ARGUS_MODEL_DIR", "backend/model"),
    "metadata.json",
)

_alert_log: Deque[AlertEntry] = deque(maxlen=50)

# ── Module-level singletons — loaded once on first predict call ─────────────
_ensemble = None
_iso_forest = None
_scaler = None
_features: list[str] | None = None
_model_features: list[str] | None = None
_pca = None
_metadata: dict[str, object] | None = None
_y_test: np.ndarray | None = None
_explainer = None
_X_test: pd.DataFrame | None = None
_X_test_raw: pd.DataFrame | None = None
_multiclass = None
_label_map: dict[int, str] | None = None
_simulation_log: Deque[SimulateResponse] = deque(maxlen=50)
_simulation_cursor: int = 0


def _load_resources() -> None:
    """Load all artefacts into singletons. No-op after first call."""
    global _ensemble, _iso_forest, _scaler, _features, _model_features, \
        _pca, _metadata, _y_test, _explainer, _X_test, _X_test_raw, \
        _multiclass, _label_map

    if _ensemble is not None and _explainer is not None:
        return

    _ensemble = load_ensemble()
    _iso_forest = load_iso_forest()
    _scaler = load_scaler()
    _features = load_features()
    _model_features = load_model_features()
    _pca = load_pca()
    _metadata = load_metadata()
    _y_test = load_y_test()
    _X_test = load_X_test()
    _X_test_raw = load_X_test_raw()
    _multiclass = load_multiclass()
    _label_map = load_label_map()

    if any(
        x is None
        for x in [
            _ensemble,
            _iso_forest,
            _scaler,
            _features,
            _model_features,
            _metadata,
            _y_test,
            _X_test,
            _X_test_raw,
        ]
    ):
        raise RuntimeError("One or more model artefacts failed to load — check backend/model/.")

    if _metadata.get("ARGUS_USE_PCA") and _pca is None:
        raise RuntimeError("Model metadata indicates PCA was used, but pca.pkl is missing.")

    _explainer = create_explainer(_ensemble)


def _build_packet(request_features: dict[str, float]) -> pd.Series:
    """Scale and optionally PCA-transform an incoming raw feature vector."""
    if _features is None or _model_features is None or _scaler is None:
        raise RuntimeError("Model artefacts are not loaded.")

    raw_vector = np.array(
        [float(request_features.get(f, 0.0)) for f in _features]
    ).reshape(1, -1)
    scaled_array = _scaler.transform(raw_vector)
    if _pca is not None:
        scaled_array = _pca.transform(scaled_array)

    return pd.Series(scaled_array[0], index=_model_features)


# Endpoints

@router.get("/health", status_code=200)
async def health() -> dict:
    """Health check — used by Streamlit to verify the API is awake (§9.1)."""
    return {"status": "ok"}


@router.get("/model/metadata")
def get_model_metadata() -> dict:
    """Return the metadata fields required by the model overview page."""
    if not os.path.exists(METADATA_PATH):
        raise HTTPException(
            status_code=404,
            detail="metadata.json not found. Run train_model.py first.",
        )

    with open(METADATA_PATH, "r", encoding="utf-8") as metadata_file:
        meta = json.load(metadata_file)

    return {
        "trained_at": meta.get("trained_at"),
        "calibrated_accuracy": meta.get("calibrated_accuracy"),
        "raw_accuracy": meta.get("raw_accuracy"),
        "train_count": meta.get("train_count"),
        "test_count": meta.get("test_count"),
        "smote_train_count": meta.get("smote_train_count"),
        "smote_class_counts": meta.get("smote_class_counts"),
        "feature_count": len(meta.get("model_feature_names", [])),
        "use_pca": meta.get("ARGUS_USE_PCA"),
        "dataset_source": meta.get("dataset_source"),
        "calibration_status": meta.get("calibration_status"),
        "hyperparameters": meta.get("hyperparameters"),
    }


@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    """Full §3.2 pipeline: scale → ensemble → iso_forest → decide → SHAP → alert."""
    try:
        _load_resources()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    packet = _build_packet(request.features)

    # §3.2 pipeline — predict_packet handles ensemble + iso_forest + decide()
    result = predict_packet(
        packet=packet,
        ensemble=_ensemble,
        iso_forest=_iso_forest,
        feature_names=_model_features,
    )

    # SHAP — generate_shap_analysis returns (shap_vector, explanation_text)
    packet_df = packet.to_frame().T
    proba = _ensemble.predict_proba(packet_df)[0]
    prediction_int = int(np.argmax(proba))
    shap_vector, explanation_text = generate_shap_analysis(
        explainer=_explainer,
        packet_df=packet_df,
        feature_names=_model_features,
        prediction=prediction_int,
    )

    # get_top_shap_features returns list[dict], convert to list[ShapFeature]
    shap_dicts = get_top_shap_features(
        feature_names=_model_features,
        shap_vector=shap_vector,
        top_n=5,
    )
    shap_features = [ShapFeature(**d) for d in shap_dicts]

    timestamp = datetime.now(timezone.utc).isoformat()

    # Discord webhook — HIGH and ANOMALY only (§8)
    if result.severity in ("HIGH", "ANOMALY"):
        dispatch_alert(
            severity=result.severity,
            timestamp=timestamp,
            confidence=result.confidence,
            anomaly_score=result.anomaly_score,
            shap_top_features=shap_dicts[:3],
        )

    entry = AlertEntry(
        timestamp=timestamp,
        prediction=result.prediction,
        severity=result.severity,
        confidence=round(result.confidence, 4),
        anomaly_score=round(result.anomaly_score, 4),
        shap_top_features=shap_features,
    )
    _alert_log.append(entry)

    return PredictResponse(
        prediction=entry.prediction,
        severity=entry.severity,
        anomaly_score=entry.anomaly_score,
        confidence=entry.confidence,
        explanation_text=explanation_text,
        shap_top_features=shap_features,
        timestamp=timestamp,
    )


@router.post("/predict/multiclass", response_model=MulticlassPredictResponse)
async def predict_multiclass(request: PredictRequest) -> MulticlassPredictResponse:
    """Run the binary pipeline first, then classify attack type with the multiclass model."""
    try:
        _load_resources()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if _multiclass is None:
        raise HTTPException(
            status_code=503,
            detail="Multiclass model not available. Run train_multiclass.py first.",
        )

    packet = _build_packet(request.features)

    result = predict_packet(
        packet=packet,
        ensemble=_ensemble,
        iso_forest=_iso_forest,
        feature_names=_model_features,
    )

    packet_df = packet.to_frame().T
    multiclass_proba = _multiclass.predict_proba(packet_df)[0]
    multiclass_class_id = int(np.argmax(multiclass_proba))
    attack_type = None
    if result.prediction == "ATTACK" and _label_map is not None:
        attack_type = _label_map.get(multiclass_class_id)

    proba = _ensemble.predict_proba(packet_df)[0]
    prediction_int = int(np.argmax(proba))
    shap_vector, explanation_text = generate_shap_analysis(
        explainer=_explainer,
        packet_df=packet_df,
        feature_names=_model_features,
        prediction=prediction_int,
    )

    shap_dicts = get_top_shap_features(
        feature_names=_model_features,
        shap_vector=shap_vector,
        top_n=5,
    )
    shap_features = [ShapFeature(**d) for d in shap_dicts]

    timestamp = datetime.now(timezone.utc).isoformat()

    if result.severity in ("HIGH", "ANOMALY"):
        dispatch_alert(
            severity=result.severity,
            timestamp=timestamp,
            confidence=result.confidence,
            anomaly_score=result.anomaly_score,
            shap_top_features=shap_dicts[:3],
        )

    entry = AlertEntry(
        timestamp=timestamp,
        prediction=result.prediction,
        severity=result.severity,
        confidence=round(result.confidence, 4),
        anomaly_score=round(result.anomaly_score, 4),
        shap_top_features=shap_features,
    )
    _alert_log.append(entry)

    return MulticlassPredictResponse(
        prediction=result.prediction,
        attack_type=attack_type,
        severity=result.severity,
        confidence=round(result.confidence, 4),
        multiclass_confidence=round(float(multiclass_proba[multiclass_class_id]), 4),
        anomaly_score=round(result.anomaly_score, 4),
        explanation_text=explanation_text,
        shap_top_features=shap_features,
        timestamp=timestamp,
    )


@router.post("/explain", response_model=ExplainResponse)
async def explain(request: ExplainRequest) -> ExplainResponse:
    """Return SHAP explainability for a single raw packet without dispatching an alert."""
    try:
        _load_resources()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    packet = _build_packet(request.features)
    packet_df = packet.to_frame().T
    proba = _ensemble.predict_proba(packet_df)[0]
    prediction_int = int(np.argmax(proba))

    shap_vector, explanation_text = generate_shap_analysis(
        explainer=_explainer,
        packet_df=packet_df,
        feature_names=_model_features,
        prediction=prediction_int,
    )
    feature_contributions = {
        name: float(value)
        for name, value in zip(_model_features, shap_vector)
    }
    shap_dicts = get_top_shap_features(
        feature_names=_model_features,
        shap_vector=shap_vector,
        top_n=5,
    )
    top_features = [ShapFeature(**d) for d in shap_dicts]

    return ExplainResponse(
        feature_contributions=feature_contributions,
        top_features=top_features,
        explanation_text=explanation_text,
    )


@router.get("/model/threshold", response_model=ThresholdMetricsResponse)
async def threshold_metrics(threshold: float = 0.5) -> ThresholdMetricsResponse:
    """Compute confusion matrix and summary metrics for an arbitrary decision threshold."""
    try:
        _load_resources()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if _y_test is None or _X_test is None:
        raise HTTPException(status_code=503, detail="Threshold tuning artifacts are not available.")
    if not math.isfinite(threshold):
        raise HTTPException(status_code=400, detail="threshold must be a finite number.")
    if threshold < 0.0 or threshold > 1.0:
        raise HTTPException(status_code=400, detail="threshold must be between 0.0 and 1.0")

    y_prob = _ensemble.predict_proba(_X_test)[:, 1]
    y_pred = (y_prob >= threshold).astype(int)
    cm = confusion_matrix(_y_test, y_pred)
    precision = precision_score(_y_test, y_pred, zero_division=0)
    recall = recall_score(_y_test, y_pred, zero_division=0)
    f1 = f1_score(_y_test, y_pred, zero_division=0)
    support = int((_y_test == 1).sum())

    return ThresholdMetricsResponse(
        threshold=threshold,
        confusion_matrix=cm.tolist(),
        precision=round(float(precision), 4),
        recall=round(float(recall), 4),
        f1_score=round(float(f1), 4),
        support=support,
        total=int(len(_y_test)),
        tn=int(cm[0, 0]),
        fp=int(cm[0, 1]),
        fn=int(cm[1, 0]),
        tp=int(cm[1, 1]),
    )


@router.post("/simulate", response_model=SimulateResponse)
async def simulate(request: SimulateRequest) -> SimulateResponse:
    """Simulate a sliding window and append the result to the simulation log."""
    global _simulation_cursor

    try:
        _load_resources()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    result = simulate_window(
        ensemble=_ensemble,
        iso_forest=_iso_forest,
        X_test=_X_test,
        feature_names=_model_features,
        window_size=request.window_size,
        start_index=_simulation_cursor,
    )

    step_size = max(1, request.window_size // 2)
    _simulation_cursor = (_simulation_cursor + step_size) % len(_X_test)

    entry = SimulateResponse(**result)
    _simulation_log.append(entry)
    return entry


@router.get("/simulations", response_model=SimulationsResponse)
async def simulations() -> SimulationsResponse:
    """Return the most recent simulation results, most recent first."""
    ordered = list(reversed(_simulation_log))
    return SimulationsResponse(simulations=ordered, total=len(ordered))


@router.post("/predict/random", response_model=PredictRandomResponse)
async def predict_random() -> PredictRandomResponse:
    """Select a random test packet, run the full pipeline, and return prediction plus raw features."""
    try:
        _load_resources()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    packet, idx = get_random_packet(_X_test)

    result = predict_packet(
        packet=packet,
        ensemble=_ensemble,
        iso_forest=_iso_forest,
        feature_names=_model_features,
    )

    packet_df = packet.to_frame().T
    proba = _ensemble.predict_proba(packet_df)[0]
    prediction_int = int(np.argmax(proba))
    shap_vector, explanation_text = generate_shap_analysis(
        explainer=_explainer,
        packet_df=packet_df,
        feature_names=_model_features,
        prediction=prediction_int,
    )

    shap_dicts = get_top_shap_features(
        feature_names=_model_features,
        shap_vector=shap_vector,
        top_n=5,
    )
    shap_features = [ShapFeature(**d) for d in shap_dicts]

    raw_row = _X_test_raw.iloc[idx]
    raw_features = {
        k: float(v)
        for k, v in raw_row.to_dict().items()
    }

    timestamp = datetime.now(timezone.utc).isoformat()

    if result.severity in ("HIGH", "ANOMALY"):
        dispatch_alert(
            severity=result.severity,
            timestamp=timestamp,
            confidence=result.confidence,
            anomaly_score=result.anomaly_score,
            shap_top_features=shap_dicts[:3],
        )

    entry = PredictRandomResponse(
        prediction=result.prediction,
        severity=result.severity,
        anomaly_score=round(result.anomaly_score, 4),
        confidence=round(result.confidence, 4),
        explanation_text=explanation_text,
        shap_top_features=shap_features,
        timestamp=timestamp,
        raw_features=raw_features,
    )

    _alert_log.append(
        AlertEntry(
            timestamp=timestamp,
            prediction=entry.prediction,
            severity=entry.severity,
            confidence=entry.confidence,
            anomaly_score=entry.anomaly_score,
            shap_top_features=shap_features,
        )
    )

    return entry


@router.get("/alerts", response_model=AlertsResponse)
async def alerts() -> AlertsResponse:
    """Return last 50 alerts, most recent first (§4)."""
    ordered = list(reversed(_alert_log))
    return AlertsResponse(alerts=ordered, total=len(ordered))
