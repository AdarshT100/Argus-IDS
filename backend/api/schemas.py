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
    explanation_text: str
    shap_top_features: list[ShapFeature]
    timestamp: str           # ISO-8601 string


class ExplainRequest(PredictRequest):
    """POST /explain request body. Reuses the same raw feature mapping."""


class ExplainResponse(BaseModel):
    """POST /explain response body with SHAP contributions."""

    feature_contributions: dict[str, float]
    top_features: list[ShapFeature]
    explanation_text: str


class ThresholdMetricsResponse(BaseModel):
    """GET /model/threshold response body."""

    threshold: float
    confusion_matrix: list[list[int]]
    precision: float
    recall: float
    f1_score: float
    support: int
    total: int
    tn: int
    fp: int
    fn: int
    tp: int


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


# Added /simulate and /predict/random schemas for §7 simulation and testing purposes.
class SimulateRequest(BaseModel):
    """POST /simulate request body."""

    window_size: int = Field(
        50,
        description="Number of packets to simulate in the sliding window.",
        example=50,
    )


class SimulateResponse(BaseModel):
    """POST /simulate response body."""

    timestamp: str
    window_size: int
    attack_count: int
    anomaly_count: int
    mean_risk_score: float
    severity: str
    alert_triggered: bool


class PredictRandomResponse(PredictResponse):
    """POST /predict/random response body."""

    raw_features: dict[str, float]


class SimulationsResponse(BaseModel):
    """GET /simulations response body."""

    simulations: list[SimulateResponse]
    total: int
