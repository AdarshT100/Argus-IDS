# filename: backend/services/alert_dispatcher.py
# purpose: Discord webhook dispatcher — fires on HIGH and ANOMALY severities only
# governed by: §8 (alerting decisions), §3.3 (trigger conditions)

from __future__ import annotations

import os
import requests

# Webhook URL must be set as env var — never hardcoded (§8, no-hardcoded-paths rule)
_DISCORD_WEBHOOK_URL: str = os.environ.get("ARGUS_DISCORD_WEBHOOK_URL", "")

# Severities that trigger an alert (§8, §3.3)
_ALERT_SEVERITIES: frozenset[str] = frozenset({"HIGH", "ANOMALY"})


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
        return False

    if not _DISCORD_WEBHOOK_URL:
        return False  # silently skip if webhook not configured

    features_text = "\n".join(
        f"  • {f['feature']}: {f['impact']:.4f}" for f in shap_top_features[:3]
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
        return resp.status_code == 204
    except requests.RequestException:
        return False
