from fastapi.testclient import TestClient

from kontur_edo.app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_hides_secret_values() -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["api_key_configured"] is False
