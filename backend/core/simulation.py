# filename: backend/core/simulation.py
# purpose: Random packet selection and sliding window simulation for the frontend


from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime

from backend.core.decision import decide, DecisionResult


def _scale_packet(
    packet: pd.Series,
    scaler: object,
    feature_names: list[str],
) -> pd.DataFrame:
    """
    Scale a single packet using the fitted MinMaxScaler.
    Returns a single-row DataFrame ready for predict() / predict_proba().
    Scaler must never be refit here — inference only (§5.2 step 4).
    """
    packet_df = (
        packet[feature_names]
        .to_frame()
        .T
    )
    scaled = scaler.transform(packet_df)
    return pd.DataFrame(scaled, columns=feature_names)


def get_random_packet(
    X_test: pd.DataFrame,
) -> tuple[pd.Series, int]:
    """
    Select a single random packet from the test set.
    X_test is already scaled (scaling happened in split_dataset).
    """
    idx = np.random.randint(0, len(X_test))
    return X_test.iloc[idx], int(idx)


def predict_packet(
    packet: pd.Series,
    ensemble: object,
    iso_forest: object,
    feature_names: list[str],
) -> DecisionResult:
    """
    Run the full detection pipeline on a single packet (§3.2):
        1. Reshape to single-row DataFrame
        2. Ensemble predict_proba → label + confidence
        3. Isolation Forest predict + score_samples → iso_label + iso_score
        4. Feed into decide() → DecisionResult

    Note: X_test is already scaled when coming from split_dataset(),
    so no scaler call needed here for test set packets.
    For raw inference (API), scaling happens in routes.py before this call.
    """
    packet_df = packet[feature_names].to_frame().T

    proba: np.ndarray = ensemble.predict_proba(packet_df)[0]
    ensemble_label = int(np.argmax(proba))
    ensemble_confidence = float(proba[ensemble_label])

    iso_label = int(iso_forest.predict(packet_df)[0])
    iso_score = float(iso_forest.score_samples(packet_df)[0])

    return decide(
        ensemble_label=ensemble_label,
        ensemble_confidence=ensemble_confidence,
        iso_label=iso_label,
        iso_score=iso_score,
    )


def simulate_window(
    ensemble: object,
    iso_forest: object,
    X_test: pd.DataFrame,
    feature_names: list[str],
    window_size: int = 50,
    start_index: int = 0,
    threshold: float = 0.6,
) -> dict:
    """
    Simulate a sequential sliding window of `window_size` packets.

    Changes from prototype:
    - Uses calibrated ensemble instead of RF only
    - Includes Isolation Forest anomaly scoring
    - Severity derived from mean_risk against fixed thresholds
      (window-level heuristic — not the §3.3 per-packet decision engine)
    - y_test dependency removed — not needed at inference time

    Returns a dict matching the alert log schema used by the frontend.
    """
    if window_size > len(X_test):
        raise ValueError("window_size cannot exceed the available test rows.")

    normalized_start = start_index % len(X_test)
    end_index = normalized_start + window_size
    if end_index <= len(X_test):
        X_window = X_test.iloc[normalized_start:end_index][feature_names]
    else:
        overflow = end_index - len(X_test)
        X_window = pd.concat(
            [
                X_test.iloc[normalized_start:][feature_names],
                X_test.iloc[:overflow][feature_names],
            ],
            ignore_index=True,
        )

    probabilities: np.ndarray = ensemble.predict_proba(X_window)[:, 1]
    mean_risk = float(np.mean(probabilities))
    attack_count = int(np.sum(probabilities > 0.5))

    iso_labels: np.ndarray = iso_forest.predict(X_window)
    anomaly_count = int(np.sum(iso_labels == -1))

    if mean_risk < 0.4:
        severity = "LOW"
    elif mean_risk < 0.6:
        severity = "MEDIUM"
    else:
        severity = "HIGH"

    return {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "window_size": int(window_size),
        "attack_count": attack_count,
        "anomaly_count": anomaly_count,
        "mean_risk_score": round(mean_risk, 4),
        "severity": severity,
        "alert_triggered": bool(mean_risk > threshold),
    }
