import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services import alert_dispatcher


class _MockResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_dispatch_alert_skips_low_severity(monkeypatch):
    monkeypatch.setattr(alert_dispatcher, "_DISCORD_WEBHOOK_URL", "https://discord.example.com/webhook")

    called = {"count": 0}

    def fake_post(*args, **kwargs):
        called["count"] += 1
        return _MockResponse(204)

    monkeypatch.setattr(alert_dispatcher.requests, "post", fake_post)

    assert alert_dispatcher.dispatch_alert(
        severity="LOW",
        timestamp="2026-07-15T12:00:00Z",
        confidence=0.91,
        anomaly_score=0.35,
        shap_top_features=[{"feature": "src_port", "impact": 0.12}],
    ) is False
    assert called["count"] == 0


def test_dispatch_alert_sends_for_high_severity(monkeypatch):
    monkeypatch.setattr(alert_dispatcher, "_DISCORD_WEBHOOK_URL", "https://discord.example.com/webhook")

    captured = {}

    def fake_post(url, json=None, timeout=5):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _MockResponse(204)

    monkeypatch.setattr(alert_dispatcher.requests, "post", fake_post)

    assert alert_dispatcher.dispatch_alert(
        severity="HIGH",
        timestamp="2026-07-15T12:00:00Z",
        confidence=0.96,
        anomaly_score=0.88,
        shap_top_features=[{"feature": "src_port", "impact": 0.21}],
    ) is True
    assert captured["url"] == "https://discord.example.com/webhook"
    assert "ARGUS-IDS ALERT" in captured["json"]["content"]


def test_dispatch_alert_skips_placeholder_webhook(monkeypatch):
    monkeypatch.setattr(
        alert_dispatcher,
        "_DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/your-webhook-url",
    )

    called = {"count": 0}

    def fake_post(*args, **kwargs):
        called["count"] += 1
        return _MockResponse(204)

    monkeypatch.setattr(alert_dispatcher.requests, "post", fake_post)

    assert alert_dispatcher.dispatch_alert(
        severity="HIGH",
        timestamp="2026-07-15T12:00:00Z",
        confidence=0.97,
        anomaly_score=0.91,
        shap_top_features=[{"feature": "src_port", "impact": 0.22}],
    ) is False
    assert called["count"] == 0
