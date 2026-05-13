from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import kontur_edo.app as app_module
from kontur_edo.app import SESSION_COOKIE_NAME, UserSession, app
from kontur_edo.kontur_client import (
    KonturBox,
    KonturOrganization,
    KonturOrganizationsResponse,
    KonturTokenResponse,
    KonturUserResponse,
)
from kontur_edo.settings import Settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_app_state(monkeypatch) -> Iterator[None]:
    app_module._PENDING_AUTH.clear()
    app_module._SESSIONS.clear()
    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            client_id="KOT_test",
            client_secret="hidden-token",
            redirect_uri="https://example.com/auth/kontur/callback",
        ),
    )
    yield
    app_module._PENDING_AUTH.clear()
    app_module._SESSIONS.clear()


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_has_buttons() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Войти в Контур" in response.text
    assert "Получить организации" in response.text
    assert "Получить личные данные" in response.text


def test_config_hides_secret_values() -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["client_secret_configured"] is True
    assert "hidden-token" not in response.text


def test_login_redirects_to_kontur_identity() -> None:
    response = client.get("/auth/kontur/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://identity.testkontur.ru/connect/authorize?")
    assert "client_id=KOT_test" in location
    assert "Diadoc.PublicAPI.Staging" in location


def test_login_uses_kot_test_default_when_env_missing(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_settings", lambda: Settings(_env_file=None))

    response = client.get("/auth/kontur/login", follow_redirects=False)

    assert response.status_code == 307
    assert "client_id=KOT_test" in response.headers["location"]


def test_kontur_organizations_requires_login() -> None:
    response = client.get("/api/kontur/organizations")

    assert response.status_code == 401


def test_kontur_organizations(monkeypatch) -> None:
    def fake_get_organizations(_settings, _access_token):
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
    _set_session_cookie()

    response = client.get("/api/kontur/organizations")

    assert response.status_code == 200
    assert response.json()["organizations"][0]["boxes"][0]["box_id"] == "box-id@diadoc.ru"


def test_kontur_user(monkeypatch) -> None:
    def fake_get_current_user(_settings, _access_token):
        return KonturUserResponse(
            user_id="user-id",
            login="test-login",
            email="test@example.com",
            last_name="Иванов",
            first_name="Иван",
        )

    monkeypatch.setattr(app_module, "get_current_user", fake_get_current_user)
    _set_session_cookie()

    response = client.get("/api/kontur/user")

    assert response.status_code == 200
    assert response.json()["last_name"] == "Иванов"
    assert response.json()["email"] == "test@example.com"


def _set_session_cookie() -> None:
    session_id = "test-session"
    app_module._SESSIONS[session_id] = UserSession(
        token=KonturTokenResponse(access_token="access-token"),
        created_at=0,
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_id)
