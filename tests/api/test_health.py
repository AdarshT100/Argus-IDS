"""
tests/api/test_health.py

§11.1 CI requirements:
  - GET /health must return 200
  - POST /predict with missing `features` field must return 422

Model loading is mocked so no .pkl files are required on disk.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

# Explicit imports ensure the modules are registered in sys.modules
# before patch() tries to resolve "backend.api.routes.*" targets.
import backend.api.routes 
import backend.api.main  


# ---------------------------------------------------------------------------
# Shared mock factories
# ---------------------------------------------------------------------------

def _make_mock_models() -> dict:
    """Return a dict matching the singleton structure in routes.py."""
    ensemble = MagicMock()
    iso_forest = MagicMock()
    scaler = MagicMock()

    # scaler.transform returns a 2-D array with the same shape as input
    scaler.transform.side_effect = lambda x: np.zeros((1, len(x[0])))

    # ensemble predict_proba → [[benign_prob, attack_prob]]
    ensemble.predict_proba.return_value = np.array([[0.1, 0.9]])
    ensemble.predict.return_value = np.array([1])

    # iso_forest.decision_function → negative = anomaly; positive = normal
    iso_forest.decision_function.return_value = np.array([0.5])

    feature_names = ["feat_a", "feat_b", "feat_c"]

    return {
        "ensemble": ensemble,
        "iso_forest": iso_forest,
        "scaler": scaler,
        "feature_names": feature_names,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """
    Build a TestClient with model loading patched out.

    Patches the singleton `_models` dict inside routes.py so the
    app never touches the filesystem during tests.
    """
    mock_models = _make_mock_models()

    # Also patch get_top_shap_features and dispatch_alert to stay isolated
    with (
        patch("backend.api.routes._ensemble", mock_models["ensemble"]),
        patch("backend.api.routes._iso_forest", mock_models["iso_forest"]),
        patch("backend.api.routes._scaler", mock_models["scaler"]),
        patch("backend.api.routes._features", mock_models["feature_names"]),
        patch(
            "backend.api.routes.get_top_shap_features",
            return_value=[{"feature": "feat_a", "impact": 0.34}],
        ),
        patch("backend.api.routes.dispatch_alert", return_value=True),
    ):
        yield TestClient(backend.api.main.app)


# ---------------------------------------------------------------------------
# §11.1 Test 1 — /health must return 200
# ---------------------------------------------------------------------------

def test_health_returns_200(client: TestClient) -> None:
    """GET /health must return HTTP 200 with {"status": "ok"}."""
    response = client.get("/health")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text}"
    )
    assert response.json() == {"status": "ok"}, (
        f"Unexpected body: {response.json()}"
    )


# ---------------------------------------------------------------------------
# §11.1 Test 2 — /predict with missing `features` must return 422
# ---------------------------------------------------------------------------

def test_predict_missing_features_returns_422(client: TestClient) -> None:
    """POST /predict without the `features` key must return HTTP 422."""
    response = client.post("/predict", json={"wrong_key": {}})

    assert response.status_code == 422, (
        f"Expected 422 (Unprocessable Entity), got {response.status_code}. "
        f"Body: {response.text}"
    )