from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from redis.exceptions import ResponseError

from backend.core.decision import DecisionResult, decide
from backend.core.model import (
    load_ensemble,
    load_features,
    load_iso_forest,
    load_label_map,
    load_multiclass,
    load_scaler,
)
from backend.core.simulation import predict_packet
from backend.services.SHAP_explainer import (
    create_explainer,
    generate_shap_analysis,
    get_top_shap_features,
)
from backend.services.stream_manager import STREAM_CLASSIFIED, STREAM_FLOWS, get_client, xadd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

REDIS_URL: str = os.environ.get("ARGUS_REDIS_URL", "redis://localhost:6379")
MODEL_DIR: str = os.environ.get("ARGUS_MODEL_DIR", "backend/model")
CONSUMER_NAME: str = os.environ.get("ARGUS_CONSUMER_NAME", "predictor-1")
FLOW_LOG_INTERVAL: int = int(os.environ.get("ARGUS_FLOW_LOG_INTERVAL", "1000"))
BATCH_SIZE: int = int(os.environ.get("ARGUS_BATCH_SIZE", "10"))
GROUP_NAME: str = "argus-predictors"

_shutdown: bool = False


def _handle_signal(signum: int, frame: object) -> None:
    global _shutdown
    log.info("Shutdown signal received (%s) — finishing current batch then exiting.", signum)
    _shutdown = True


def _load_artifacts() -> tuple[Any, Any, Any, list[str], Any, Any, dict[int, str] | None]:
    ensemble = load_ensemble()
    iso_forest = load_iso_forest()
    scaler = load_scaler()
    features = load_features()
    multiclass = load_multiclass()
    label_map = load_label_map()

    if ensemble is None:
        raise RuntimeError("ensemble_model.pkl not found in ARGUS_MODEL_DIR")
    if iso_forest is None:
        raise RuntimeError("iso_forest.pkl not found in ARGUS_MODEL_DIR")
    if scaler is None:
        raise RuntimeError("scaler.pkl not found in ARGUS_MODEL_DIR")
    if not features:
        raise RuntimeError("rf_features.pkl not found or empty in ARGUS_MODEL_DIR")

    return ensemble, iso_forest, scaler, features, multiclass, None, label_map


def _build_packet(payload: dict[str, str], feature_names: list[str], scaler: Any) -> pd.Series:
    values: list[float] = []
    for feature_name in feature_names:
        raw_value = payload.get(feature_name)
        if raw_value is None:
            values.append(0.0)
            continue
        try:
            values.append(float(raw_value))
        except (TypeError, ValueError):
            values.append(0.0)

    raw_df = pd.DataFrame([values], columns=feature_names)
    scaled_array = scaler.transform(raw_df)
    return pd.Series(scaled_array[0], index=feature_names)


def _predict_packet(
    packet: pd.Series,
    feature_names: list[str],
    ensemble: Any,
    iso_forest: Any,
) -> tuple[DecisionResult, np.ndarray]:
    result = predict_packet(
        packet=packet,
        ensemble=ensemble,
        iso_forest=iso_forest,
        feature_names=feature_names,
    )

    packet_df = packet.to_frame().T
    proba = ensemble.predict_proba(packet_df)[0]
    prediction_int = int(np.argmax(proba))
    return result, np.asarray(proba)


def _build_shap_payload(
    packet: pd.Series,
    feature_names: list[str],
    explainer: Any,
    prediction_int: int,
    top_n: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    packet_df = packet.to_frame().T
    shap_vector, explanation_text = generate_shap_analysis(
        explainer=explainer,
        packet_df=packet_df,
        feature_names=feature_names,
        prediction=prediction_int,
        top_n=top_n,
    )
    shap_features = get_top_shap_features(
        feature_names=feature_names,
        shap_vector=shap_vector,
        top_n=top_n,
    )
    serializable_shap = [
        {"feature": item["feature"], "impact": float(item["impact"])}
        for item in shap_features
    ]
    return serializable_shap, explanation_text


def _build_event_payload(
    message_id: str,
    prediction_result: DecisionResult,
    attack_type: str | None,
    shap_features: list[dict[str, Any]],
    label: str,
    source_file: str,
) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    severity = str(prediction_result.severity.value)
    confidence = f"{float(prediction_result.confidence):.6g}"
    anomaly_score = f"{float(prediction_result.anomaly_score):.6g}"
    shap_json = json.dumps(shap_features)

    return {
        "event_id": message_id,
        "timestamp": timestamp,
        "prediction": str(prediction_result.prediction),
        "attack_type": attack_type if attack_type is not None else "NONE",
        "severity": severity,
        "confidence": confidence,
        "anomaly_score": anomaly_score,
        "shap_top_features": shap_json,
        "label": label,
        "source_file": source_file,
    }


def _initialise_consumer_group(client: Any) -> None:
    try:
        client.xgroup_create(STREAM_FLOWS, GROUP_NAME, id="0", mkstream=True)
        log.info("Created Redis consumer group %s on %s", GROUP_NAME, STREAM_FLOWS)
    except ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            log.info("Consumer group %s already exists", GROUP_NAME)
            return
        raise


def run() -> None:
    global _shutdown

    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("═" * 60)
    log.info("Argus-IDS — Prediction Consumer (Phase 7)")
    log.info("  Redis URL    : %s", REDIS_URL)
    log.info("  Model dir    : %s", MODEL_DIR)
    log.info("  Consumer     : %s", CONSUMER_NAME)
    log.info("  Stream input : %s", STREAM_FLOWS)
    log.info("  Stream output: %s", STREAM_CLASSIFIED)
    log.info("  Log interval : every %d packets", FLOW_LOG_INTERVAL)
    log.info("═" * 60)

    client = get_client()
    _initialise_consumer_group(client)

    ensemble, iso_forest, scaler, feature_names, multiclass, _, label_map = _load_artifacts()
    explainer = create_explainer(ensemble)

    processed_count = 0
    last_seen_id = "0"

    try:
        while not _shutdown:
            raw_messages = client.xreadgroup(
                GROUP_NAME,
                CONSUMER_NAME,
                {STREAM_FLOWS: ">"},
                count=BATCH_SIZE,
                block=1000,
            )

            if not raw_messages:
                continue

            for stream_name, messages in raw_messages:
                if stream_name != STREAM_FLOWS:
                    continue

                for message_id, fields in messages:
                    if _shutdown:
                        break

                    label = str(fields.get("label", ""))
                    source_file = str(fields.get("source_file", ""))
                    packet = _build_packet(fields, feature_names, scaler)
                    prediction_result, _ = _predict_packet(
                        packet=packet,
                        feature_names=feature_names,
                        ensemble=ensemble,
                        iso_forest=iso_forest,
                    )

                    attack_type : str | None = None
                    if prediction_result.prediction == "ATTACK" and multiclass is not None:
                        payload_df = packet.to_frame().T
                        multiclass_proba = multiclass.predict_proba(payload_df)[0]
                        multiclass_class_id = int(np.argmax(multiclass_proba))
                        if label_map is not None:
                            attack_type =(label_map.get(multiclass_class_id))
                        else:
                            attack_type =(multiclass_class_id)

                    prediction_int = int(
                        np.argmax(ensemble.predict_proba(packet.to_frame().T)[0])
                    )
                    shap_features, _ = _build_shap_payload(
                        packet=packet,
                        feature_names=feature_names,
                        explainer=explainer,
                        prediction_int=prediction_int,
                        top_n=5,
                    )

                    event_payload = _build_event_payload(
                        message_id=message_id,
                        prediction_result=prediction_result,
                        attack_type=attack_type,
                        shap_features=shap_features,
                        label=label,
                        source_file=source_file,
                    )
                    published_id = xadd(STREAM_CLASSIFIED, event_payload)

                    if published_id is not None:
                        client.xack(STREAM_FLOWS, GROUP_NAME, message_id)
                        processed_count += 1
                        if processed_count % FLOW_LOG_INTERVAL == 0:
                            log.info(
                                "Processed %d packets (latest=%s prediction=%s)",
                                processed_count,
                                message_id,
                                prediction_result.prediction,
                            )
                    else:
                        log.warning("Failed to publish event for message %s", message_id)

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received — shutting down.")
        _shutdown = True
    except Exception as exc:  # pragma: no cover - defensive logging
        log.exception("Prediction consumer crashed: %s", exc)
        raise

    log.info("Prediction consumer stopped after %d packets", processed_count)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt handled at process boundary.")
        sys.exit(0)
