# filename: backend/services/alert_dispatcher.py
# purpose: Discord webhook dispatcher — fires on HIGH and ANOMALY severities only


from __future__ import annotations

import logging
import os
import requests

logger = logging.getLogger(__name__)

_DISCORD_WEBHOOK_URL: str = os.environ.get("ARGUS_DISCORD_WEBHOOK_URL", "")

# Severities that trigger an alert (§8, §3.3)
_ALERT_SEVERITIES: frozenset[str] = frozenset({"HIGH", "ANOMALY"})
_PLACEHOLDER_WEBHOOK_FRAGMENT: str = "your-webhook-url"


def dispatch_alert(
    severity: str,
    timestamp: str,
    confidence: float,
    anomaly_score: float,
    shap_top_features: list[dict],
) -> bool:
    """
    Send a Discord webhook alert if severity warrants it (§8).

    Args:
        severity:          "LOW" | "MEDIUM" | "HIGH" | "ANOMALY"
        timestamp:         ISO-8601 string
        confidence:        ensemble calibrated confidence score
        anomaly_score:     Isolation Forest anomaly score
        shap_top_features: list of top-3 {"feature": str, "impact": float} dicts

    Returns:
        True if webhook was fired, False if skipped or failed.
    """
    if severity not in _ALERT_SEVERITIES:
        logger.info("Skipping Discord alert for non-trigger severity: %s", severity)
        return False

    if not _DISCORD_WEBHOOK_URL:
        logger.warning("Discord alert skipped because no webhook URL is configured")
        return False

    if _PLACEHOLDER_WEBHOOK_FRAGMENT in _DISCORD_WEBHOOK_URL:
        logger.warning("Discord alert skipped because webhook URL still contains the placeholder")
        return False

    safe_features = []
    for feature in shap_top_features[:3]:
        feature_name = feature.get("feature", "unknown")
        feature_impact = feature.get("impact", 0.0)
        safe_features.append({"feature": str(feature_name), "impact": float(feature_impact)})

    features_text = "\n".join(
        f"  • {feature['feature']}: {feature['impact']:.4f}" for feature in safe_features
    )
    payload = {
        "content": (
            f"🚨 **ARGUS-IDS ALERT** — `{severity}`\n"
            f"**Timestamp:** {timestamp}\n"
            f"**Confidence:** {confidence:.3f}\n"
            f"**Anomaly Score:** {anomaly_score:.3f}\n"
            f"**Top SHAP Features:**\n{features_text}"
        )
    }

    try:
        resp = requests.post(_DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if resp.status_code == 204:
            logger.info("Discord alert dispatched successfully for severity %s", severity)
            return True

        logger.warning(
            "Discord alert failed with status %s for severity %s",
            resp.status_code,
            severity,
        )
        return False
    except requests.RequestException as exc:
        logger.exception("Discord alert request failed: %s", exc)
        return False
