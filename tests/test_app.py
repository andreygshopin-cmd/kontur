from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import kontur_edo.app as app_module
from kontur_edo.app import (
    DEFAULT_KEDO_DOCUMENT_TYPE_ID,
    SESSION_COOKIE_NAME,
    UserSession,
    app,
)
from kontur_edo.kedo_client import KedoConnectivityResponse, KedoTestDocumentResponse
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
    assert "Проверить КЭДО API" in response.text
    assert "Отправить тестовый файл в КЭДО" in response.text
    assert DEFAULT_KEDO_DOCUMENT_TYPE_ID in response.text


def test_config_hides_secret_values() -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["client_secret_configured"] is True
    assert payload["kedo_base_url"] == "https://api.testkontur.ru/kedo"
    assert payload["kedo_api_key_configured"] is True
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


def test_kedo_test_document(monkeypatch) -> None:
    def fake_send_test_document(_settings, *, access_token=None, document_type_id=None):
        assert access_token is None
        assert document_type_id == DEFAULT_KEDO_DOCUMENT_TYPE_ID
        return KedoTestDocumentResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            employee_id="22222222-2222-2222-2222-222222222222",
            document_type_id="33333333-3333-3333-3333-333333333333",
            file_name="test-kedo.txt",
            content_location="44444444-4444-4444-4444-444444444444",
            processed_content_location="55555555-5555-5555-5555-555555555555",
            process_ids=["66666666-6666-6666-6666-666666666666"],
            raw_response=[{"id": "66666666-6666-6666-6666-666666666666"}],
        )

    monkeypatch.setattr(app_module, "send_test_document", fake_send_test_document)

    response = client.post(
        "/api/kedo/test-document",
        json={"document_type_id": DEFAULT_KEDO_DOCUMENT_TYPE_ID},
    )

    assert response.status_code == 200
    assert response.json()["process_ids"] == ["66666666-6666-6666-6666-666666666666"]


def test_kedo_connectivity(monkeypatch) -> None:
    def fake_check_connectivity(_settings):
        return KedoConnectivityResponse(
            url="https://api.testkontur.ru/kedo",
            host="api.testkontur.ru",
            port=443,
            resolved_addresses=["46.17.203.148"],
            tcp_connected=True,
            tls_connected=False,
            tls_error="TimeoutError: timed out",
            elapsed_ms=10000,
        )

    monkeypatch.setattr(app_module, "check_connectivity", fake_check_connectivity)

    response = client.get("/api/kedo/connectivity")

    assert response.status_code == 200
    assert response.json()["tls_error"] == "TimeoutError: timed out"


def _set_session_cookie() -> None:
    session_id = "test-session"
    app_module._SESSIONS[session_id] = UserSession(
        token=KonturTokenResponse(access_token="access-token"),
        created_at=0,
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_id)
