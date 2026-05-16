from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import kontur_edo.app as app_module
from kontur_edo.app import DEFAULT_KEDO_DOCUMENT_TYPE_ID, DEFAULT_KEDO_TEST_FILENAME, app
from kontur_edo.kedo_client import (
    KedoConnectivityResponse,
    KedoDocumentType,
    KedoDocumentTypesResponse,
    KedoEmployee,
    KedoEmployeesResponse,
    KedoSignatureTypesResponse,
    KedoTestDocumentResponse,
    _build_process_payload,
)
from kontur_edo.settings import Settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_app_state(monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: Settings(_env_file=None),
    )
    yield


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_has_only_kedo_controls() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Проверить КЭДО API" in response.text
    assert "Получить типы документов КЭДО" in response.text
    assert "Получить сотрудников" in response.text
    assert "Получить типы подписи" in response.text
    assert "Отправить тестовый файл в КЭДО" in response.text
    assert DEFAULT_KEDO_DOCUMENT_TYPE_ID in response.text
    assert "Отправитель" in response.text
    assert 'id="kedo-sender-id"' in response.text
    assert "Участник подписания" in response.text
    assert 'id="kedo-employee-id"' in response.text
    assert "Срок выполнения, календарные дни" in response.text
    assert 'id="kedo-due-days"' in response.text
    assert "Тип подписи" in response.text
    assert 'id="kedo-signature-type"' in response.text
    assert 'id="kedo-file"' in response.text
    assert "KONTUR_KEDO_TEST_FILENAME" not in response.text
    assert "Войти в Контур" not in response.text
    assert "Получить организации" not in response.text
    assert "Получить личные данные" not in response.text


def test_kedo_test_document(monkeypatch) -> None:
    def fake_send_test_document(
        _settings,
        *,
        document_type_id=None,
        sender_id=None,
        employee_id=None,
        signature_type=None,
        due_days=None,
        file_name=None,
        file_bytes=None,
    ):
        assert document_type_id == DEFAULT_KEDO_DOCUMENT_TYPE_ID
        assert sender_id == "11111111-1111-1111-1111-111111111111"
        assert employee_id == "22222222-2222-2222-2222-222222222222"
        assert signature_type == "Pep"
        assert due_days == 1
        assert file_name == DEFAULT_KEDO_TEST_FILENAME
        assert file_bytes == b"hello"
        return KedoTestDocumentResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            employee_id="22222222-2222-2222-2222-222222222222",
            document_type_id="33333333-3333-3333-3333-333333333333",
            file_name=DEFAULT_KEDO_TEST_FILENAME,
            content_location="44444444-4444-4444-4444-444444444444",
            processed_content_location="44444444-4444-4444-4444-444444444444",
            process_ids=["66666666-6666-6666-6666-666666666666"],
            raw_response=[{"id": "66666666-6666-6666-6666-666666666666"}],
        )

    monkeypatch.setattr(app_module, "send_test_document", fake_send_test_document)

    response = client.post(
        "/api/kedo/test-document",
        json={
            "document_type_id": DEFAULT_KEDO_DOCUMENT_TYPE_ID,
            "sender_id": "11111111-1111-1111-1111-111111111111",
            "employee_id": "22222222-2222-2222-2222-222222222222",
            "signature_type": "Pep",
            "due_days": 1,
            "file_name": DEFAULT_KEDO_TEST_FILENAME,
            "file_content_base64": "aGVsbG8=",
        },
    )

    assert response.status_code == 200
    assert response.json()["process_ids"] == ["66666666-6666-6666-6666-666666666666"]


def test_kedo_test_document_strips_windows_path_from_file_name(monkeypatch) -> None:
    def fake_send_test_document(
        _settings,
        *,
        document_type_id=None,
        sender_id=None,
        employee_id=None,
        signature_type=None,
        due_days=None,
        file_name=None,
        file_bytes=None,
    ):
        assert document_type_id == DEFAULT_KEDO_DOCUMENT_TYPE_ID
        assert sender_id is None
        assert employee_id is None
        assert signature_type is None
        assert due_days == 1
        assert file_name == "test.pdf"
        assert file_bytes == b"hello"
        return KedoTestDocumentResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            employee_id="22222222-2222-2222-2222-222222222222",
            document_type_id="33333333-3333-3333-3333-333333333333",
            file_name="test.pdf",
            content_location="44444444-4444-4444-4444-444444444444",
            processed_content_location="44444444-4444-4444-4444-444444444444",
            process_ids=["66666666-6666-6666-6666-666666666666"],
            raw_response=[{"id": "66666666-6666-6666-6666-666666666666"}],
        )

    monkeypatch.setattr(app_module, "send_test_document", fake_send_test_document)

    response = client.post(
        "/api/kedo/test-document",
        json={
            "document_type_id": DEFAULT_KEDO_DOCUMENT_TYPE_ID,
            "file_name": r"D:\Codex\Kontur\TestFile\test.pdf",
            "file_content_base64": "aGVsbG8=",
        },
    )

    assert response.status_code == 200
    assert response.json()["file_name"] == "test.pdf"


def test_kedo_test_document_rejects_invalid_file_base64() -> None:
    response = client.post(
        "/api/kedo/test-document",
        json={
            "document_type_id": DEFAULT_KEDO_DOCUMENT_TYPE_ID,
            "file_name": DEFAULT_KEDO_TEST_FILENAME,
            "file_content_base64": "not base64",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid file_content_base64."


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


def test_kedo_document_types(monkeypatch) -> None:
    def fake_get_kedo_document_types(_settings):
        return KedoDocumentTypesResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            document_types=[
                KedoDocumentType(
                    id="22222222-2222-2222-2222-222222222222",
                    name="Тестовый документ",
                    is_default=True,
                    metadata={"fileNamePattern": "*.pdf"},
                )
            ],
        )

    monkeypatch.setattr(app_module, "get_kedo_document_types", fake_get_kedo_document_types)

    response = client.get("/api/kedo/document-types")

    assert response.status_code == 200
    assert response.json()["document_types"][0]["metadata"] == {"fileNamePattern": "*.pdf"}


def test_kedo_employees(monkeypatch) -> None:
    def fake_get_kedo_employees(_settings):
        return KedoEmployeesResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            employees=[
                KedoEmployee(
                    id="22222222-2222-2222-2222-222222222222",
                    org_id="11111111-1111-1111-1111-111111111111",
                    user_id="33333333-3333-3333-3333-333333333333",
                    full_name="Иван Иванов",
                    login="ivan@example.com",
                )
            ],
        )

    monkeypatch.setattr(app_module, "get_kedo_employees", fake_get_kedo_employees)

    response = client.get("/api/kedo/employees")

    assert response.status_code == 200
    assert response.json()["employees"][0]["id"] == "22222222-2222-2222-2222-222222222222"


def test_kedo_signature_types(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "get_kedo_signature_types",
        lambda _settings: KedoSignatureTypesResponse(signature_types=["Pep", "Nep"]),
    )

    response = client.get("/api/kedo/signature-types")

    assert response.status_code == 200
    assert response.json() == {"signature_types": ["Pep", "Nep"]}


def test_build_process_payload_has_sender_and_sign_step() -> None:
    payload = _build_process_payload(
        Settings(_env_file=None),
        sender_id="11111111-1111-1111-1111-111111111111",
        employee_id="22222222-2222-2222-2222-222222222222",
        document_type_id="33333333-3333-3333-3333-333333333333",
        content={"location": "content-location", "name": "test.pdf"},
        signature_type="Nep",
        due_days=3,
    )

    route = payload["processes"][0]["route"]
    sign_route = route["next"]

    assert route["type"] == "NoAction"
    assert route["target"]["id"] == "11111111-1111-1111-1111-111111111111"
    assert sign_route["type"] == "Sign"
    assert sign_route["target"]["id"] == "22222222-2222-2222-2222-222222222222"
    assert sign_route["allowedTypes"] == ["Nep"]
    assert sign_route["deadline"] == {"type": "CalendarDays", "days": 3}
