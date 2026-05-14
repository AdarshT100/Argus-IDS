# filename: tests/core/test_decision.py
# purpose: Unit tests for decision engine — all four §3.3 severity conditions
# governed by: §11.1 (CI requirement — all four conditions must have a test)

import pytest
from backend.core.decision import decide, DecisionResult, Severity


# ── Helpers ──────────────────────────────────────────────────────────────────

def _decide(
    ensemble_label: int,
    ensemble_confidence: float,
    iso_label: int,
    iso_score: float = -0.05,
) -> DecisionResult:
    """Thin wrapper so tests only specify what they care about."""
    return decide(
        ensemble_label=ensemble_label,
        ensemble_confidence=ensemble_confidence,
        iso_label=iso_label,
        iso_score=iso_score,
    )


# ── §3.3 Condition 1: benign + IF normal → LOW ───────────────────────────────

def test_benign_normal_is_low():
    result = _decide(ensemble_label=0, ensemble_confidence=0.1, iso_label=1)
    assert result.severity == Severity.LOW
    assert result.prediction == "BENIGN"
    assert result.is_anomaly is False


# ── §3.3 Condition 2: benign + IF anomaly → ANOMALY ─────────────────────────

def test_benign_anomaly_is_anomaly():
    result = _decide(ensemble_label=0, ensemble_confidence=0.1, iso_label=-1)
    assert result.severity == Severity.ANOMALY
    assert result.prediction == "BENIGN"
    assert result.is_anomaly is True


# ── §3.3 Condition 3: attack + confidence < 0.75 → MEDIUM ───────────────────

def test_attack_low_confidence_is_medium():
    result = _decide(ensemble_label=1, ensemble_confidence=0.74, iso_label=1)
    assert result.severity == Severity.MEDIUM
    assert result.prediction == "ATTACK"


def test_attack_low_confidence_boundary():
    """0.749... must still be MEDIUM — boundary is exclusive below 0.75."""
    result = _decide(ensemble_label=1, ensemble_confidence=0.7499, iso_label=1)
    assert result.severity == Severity.MEDIUM


# ── §3.3 Condition 4: attack + confidence >= 0.75 → HIGH ────────────────────

def test_attack_high_confidence_is_high():
    result = _decide(ensemble_label=1, ensemble_confidence=0.90, iso_label=1)
    assert result.severity == Severity.HIGH
    assert result.prediction == "ATTACK"


def test_attack_high_confidence_boundary():
    """Exactly 0.75 must be HIGH — threshold is inclusive."""
    result = _decide(ensemble_label=1, ensemble_confidence=0.75, iso_label=1)
    assert result.severity == Severity.HIGH


# ── Output field integrity ───────────────────────────────────────────────────

def test_confidence_rounded_to_4dp():
    result = _decide(ensemble_label=1, ensemble_confidence=0.123456, iso_label=1)
    assert result.confidence == round(0.123456, 4)


def test_anomaly_score_passed_through():
    result = _decide(
        ensemble_label=0, ensemble_confidence=0.2, iso_label=-1, iso_score=-0.1234567
    )
    assert result.anomaly_score == round(-0.1234567, 4)


def test_iso_label_ignored_for_attack():
    """When ensemble says attack, IF label must not change severity."""
    high_normal = _decide(ensemble_label=1, ensemble_confidence=0.80, iso_label=1)
    high_anomaly = _decide(ensemble_label=1, ensemble_confidence=0.80, iso_label=-1)
    assert high_normal.severity == high_anomaly.severity == Severity.HIGH