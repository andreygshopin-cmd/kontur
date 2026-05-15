from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import kontur_edo.app as app_module
from kontur_edo.app import DEFAULT_KEDO_DOCUMENT_TYPE_ID, DEFAULT_KEDO_TEST_FILENAME, app
from kontur_edo.kedo_client import (
    KedoConnectivityResponse,
    KedoDocumentType,
    KedoDocumentTypesResponse,
    KedoTestDocumentResponse,
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
    assert "Отправить тестовый файл в КЭДО" in response.text
    assert DEFAULT_KEDO_DOCUMENT_TYPE_ID in response.text
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
        file_name=None,
        file_bytes=None,
    ):
        assert document_type_id == DEFAULT_KEDO_DOCUMENT_TYPE_ID
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
        file_name=None,
        file_bytes=None,
    ):
        assert document_type_id == DEFAULT_KEDO_DOCUMENT_TYPE_ID
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
