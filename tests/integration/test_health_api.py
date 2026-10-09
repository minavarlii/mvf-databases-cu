"""Health endpoint integration tests."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint() -> None:
    """Health endpoint should report an operational API."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }
