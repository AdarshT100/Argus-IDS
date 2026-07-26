# filename: backend/core/decision.py
# purpose: Decision engine — combines ensemble output + anomaly score into severity


from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    ANOMALY = "ANOMALY"


@dataclass
class DecisionResult:
    prediction: str       # "ATTACK" or "BENIGN"
    severity: Severity
    confidence: float     # calibrated probability from ensemble
    anomaly_score: float  # raw Isolation Forest score (higher = more anomalous)
    is_anomaly: bool      # True if Isolation Forest flags as anomaly


def decide(
    ensemble_label: int,
    ensemble_confidence: float,
    iso_label: int,
    iso_score: float,
) -> DecisionResult:
    """
    Args:
        iso_score: raw Isolation Forest score_samples() value — more negative = more anomalous.
                   Passed through directly to DecisionResult; no thresholding done here.
    """
    is_anomaly: bool = iso_label == -1
    prediction: str = "ATTACK" if ensemble_label == 1 else "BENIGN"

    if ensemble_label == 0:
        severity = Severity.ANOMALY if is_anomaly else Severity.LOW
    else:
        severity = Severity.HIGH if ensemble_confidence >= 0.75 else Severity.MEDIUM

    return DecisionResult(
        prediction=prediction,
        severity=severity,
        confidence=round(ensemble_confidence, 4),
        anomaly_score=round(iso_score, 4),   # ← fixed
        is_anomaly=is_anomaly,
    )
