# filename: backend/api/routes.py
# purpose: /predict, /alerts, and /health endpoint definitions
# governed by: §4 (API design), §3.2 (detection pipeline), §8 (alerting)

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Deque

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from backend.api.schemas import (
    AlertEntry,
    AlertsResponse,
    PredictRequest,
    PredictResponse,
    ShapFeature,
)
from backend.core.model import (
    load_features,
    load_ensemble,
    load_iso_forest,
    load_scaler,
)
from backend.core.simulation import predict_packet
from backend.services.alert_dispatcher import dispatch_alert
from backend.services.SHAP_explainer import (
    create_explainer,
    generate_shap_analysis,
    get_top_shap_features,
)

router = APIRouter()

# ── In-memory alert log — capped at 50 per §4 ──────────────────────────────
_alert_log: Deque[AlertEntry] = deque(maxlen=50)

# ── Module-level singletons — loaded once on first predict call ─────────────
_ensemble = None
_iso_forest = None
_scaler = None
_features: list[str] | None = None
_explainer = None

# _MODEL_DIR = os.getenv("MODEL_DIR", "backend/model")


def _load_resources() -> None:
    """Load all artefacts into singletons. No-op after first call."""
    global _ensemble, _iso_forest, _scaler, _features, _explainer

    if _ensemble is not None and _explainer is not None:
        return

    _ensemble = load_ensemble()
    _iso_forest = load_iso_forest()
    _scaler = load_scaler()
    _features = load_features()

    if any(x is None for x in [_ensemble, _iso_forest, _scaler, _features]):
        raise RuntimeError("One or more model artefacts failed to load — check backend/model/.")

    _explainer = create_explainer(_ensemble)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health", status_code=200)
async def health() -> dict:
    """Health check — used by Streamlit to verify the API is awake (§9.1)."""
    return {"status": "ok"}


@router.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    """Full §3.2 pipeline: scale → ensemble → iso_forest → decide → SHAP → alert."""
    try:
        _load_resources()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # Build scaled single-row DataFrame in feature order
    raw_vector = np.array(
        [float(request.features.get(f, 0.0)) for f in _features]
    ).reshape(1, -1)
    scaled_array = _scaler.transform(raw_vector)
    packet = pd.Series(scaled_array[0], index=_features)

    # §3.2 pipeline — predict_packet handles ensemble + iso_forest + decide()
    result = predict_packet(
        packet=packet,
        ensemble=_ensemble,
        iso_forest=_iso_forest,
        feature_names=_features,
    )

    # SHAP — generate_shap_analysis returns (shap_vector, explanation_text)
    packet_df = packet.to_frame().T
    shap_vector, _ = generate_shap_analysis(
        explainer=_explainer,
        packet_df=packet_df,
        feature_names=_features,
        prediction=result.prediction,
    )

    # get_top_shap_features returns list[dict], convert to list[ShapFeature]
    shap_dicts = get_top_shap_features(
        feature_names=_features,
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
        prediction="ATTACK" if result.prediction == 1 else "BENIGN",
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
        shap_top_features=shap_features,
        timestamp=timestamp,
    )


@router.get("/alerts", response_model=AlertsResponse)
async def alerts() -> AlertsResponse:
    """Return last 50 alerts, most recent first (§4)."""
    ordered = list(reversed(_alert_log))
    return AlertsResponse(alerts=ordered, total=len(ordered))
