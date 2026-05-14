# filename: backend/api/schemas.py
# purpose: Pydantic request/response models for the FastAPI endpoints
# governed by: §4 (request/response shapes), §11.1 (schema validation test requirement)

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """POST /predict request body. The `features` field is required."""

    features: dict[str, Any] = Field(
        ...,
        description="Mapping of feature name to numeric value.",
        example={"Flow Duration": 123456, "Total Fwd Packets": 10},
    )


class ShapFeature(BaseModel):
    """A single SHAP feature impact entry in the prediction response."""

    feature: str
    impact: float


class PredictResponse(BaseModel):
    """POST /predict response body. Shape fixed by §4."""

    prediction: str          # "ATTACK" or "BENIGN"
    severity: str            # "LOW" | "MEDIUM" | "HIGH" | "ANOMALY"
    anomaly_score: float
    confidence: float
    shap_top_features: list[ShapFeature]
    timestamp: str           # ISO-8601 string


class AlertEntry(BaseModel):
    """Single entry in the alert log. Written on every /predict call."""

    timestamp: str
    prediction: str
    severity: str
    confidence: float
    anomaly_score: float
    shap_top_features: list[ShapFeature]


class AlertsResponse(BaseModel):
    """GET /alerts response body. Returns last 50 entries, most recent first."""

    alerts: list[AlertEntry]
    total: int
