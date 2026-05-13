from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import kontur_edo.app as app_module
from kontur_edo.app import app
from kontur_edo.kontur_client import (
    KonturBox,
    KonturOrganization,
    KonturOrganizationsResponse,
    KonturUserResponse,
)
from kontur_edo.settings import Settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_settings_cache(monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(app_module, "get_settings", lambda: Settings(_env_file=None))
    yield


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_has_buttons() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Получить организации" in response.text
    assert "Получить личные данные" in response.text


def test_config_hides_secret_values() -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["api_key_configured"] is False


def test_kontur_organizations(monkeypatch) -> None:
    def fake_get_organizations(_settings):
        return KonturOrganizationsResponse(
            organizations=[
                KonturOrganization(
                    name="ООО Тест",
                    inn="1234567890",
                    kpp="123456789",
                    boxes=[KonturBox(box_id="box-id@diadoc.ru")],
                )
            ]
        )

    monkeypatch.setattr(app_module, "get_organizations", fake_get_organizations)

    response = client.get("/api/kontur/organizations")

    assert response.status_code == 200
    assert response.json()["organizations"][0]["boxes"][0]["box_id"] == "box-id@diadoc.ru"


def test_kontur_user(monkeypatch) -> None:
    def fake_get_current_user(_settings):
        return KonturUserResponse(
            user_id="user-id",
            login="test-login",
            email="test@example.com",
            last_name="Иванов",
            first_name="Иван",
        )

    monkeypatch.setattr(app_module, "get_current_user", fake_get_current_user)

    response = client.get("/api/kontur/user")

    assert response.status_code == 200
    assert response.json()["last_name"] == "Иванов"
    assert response.json()["email"] == "test@example.com"
