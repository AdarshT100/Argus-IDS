from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.api.main


@pytest.fixture()
def client() -> TestClient:
    return TestClient(backend.api.main.app)


def test_predict_multiclass_returns_attack_type_and_confidence(client: TestClient) -> None:
    multiclass_model = MagicMock()
    multiclass_model.predict_proba.return_value = np.array([[0.1, 0.7, 0.2]])

    with (
        patch("backend.api.routes._load_resources", return_value=None),
        patch("backend.api.routes._build_packet", return_value=pd.Series([1.0, 2.0, 3.0], index=["feat_a", "feat_b", "feat_c"])),
        patch("backend.api.routes._ensemble", MagicMock()),
        patch("backend.api.routes._multiclass", multiclass_model),
        patch("backend.api.routes._label_map", {0: "BENIGN", 1: "DoS", 2: "PortScan"}),
        patch("backend.api.routes._model_features", ["feat_a", "feat_b", "feat_c"]),
        patch("backend.api.routes._explainer", MagicMock()),
        patch(
            "backend.api.routes.predict_packet",
            return_value=SimpleNamespace(prediction="ATTACK", severity="HIGH", confidence=0.95, anomaly_score=0.7),
        ),
        patch(
            "backend.api.routes.generate_shap_analysis",
            return_value=(np.array([0.1, -0.2, 0.3]), "explanation text"),
        ),
        patch(
            "backend.api.routes.get_top_shap_features",
            return_value=[{"feature": "feat_a", "impact": 0.1}],
        ),
        patch("backend.api.routes.dispatch_alert", return_value=True),
    ):
        response = client.post(
            "/predict/multiclass",
            json={"features": {"feat_a": 1, "feat_b": 2, "feat_c": 3}},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prediction"] == "ATTACK"
    assert body["attack_type"] == "DoS"
    assert body["multiclass_confidence"] == 0.7


def test_predict_multiclass_returns_503_when_model_missing(client: TestClient) -> None:
    with (
        patch("backend.api.routes._load_resources", return_value=None),
        patch("backend.api.routes._build_packet", return_value=pd.Series([1.0, 2.0, 3.0], index=["feat_a", "feat_b", "feat_c"])),
        patch("backend.api.routes._multiclass", None),
    ):
        response = client.post(
            "/predict/multiclass",
            json={"features": {"feat_a": 1, "feat_b": 2, "feat_c": 3}},
        )

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Multiclass model not available. Run train_multiclass.py first."
