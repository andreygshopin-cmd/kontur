from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import kontur_edo.app as app_module
import kontur_edo.kedo_client as kedo_client_module
from kontur_edo.app import DEFAULT_KEDO_DOCUMENT_TYPE_ID, DEFAULT_KEDO_TEST_FILENAME, app
from kontur_edo.kedo_client import (
    KedoApiError,
    KedoConnectivityResponse,
    KedoDocumentType,
    KedoDocumentTypesResponse,
    KedoDownloadedFile,
    KedoEmployee,
    KedoEmployeesResponse,
    KedoSignatureTypesResponse,
    KedoSignedDocument,
    KedoSignedDocumentsResponse,
    KedoTestDocumentResponse,
    _build_process_payload,
    get_document_types,
    get_signed_documents,
    send_test_document,
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
    assert 'id="deploy-info"' in response.text
    assert "Проверить КЭДО API" in response.text
    assert "Фильтр типов документов" not in response.text
    assert 'id="kedo-document-type-filter"' not in response.text
    assert "documentTypesUrl" not in response.text
    assert "Получить типы документов КЭДО" in response.text
    assert "Следующие 20" in response.text
    assert 'id="load-next-kedo-document-types"' in response.text
    assert "loadDocumentTypesPage(documentTypesOffset)" in response.text
    assert "Получить сотрудников" in response.text
    assert "Получить типы подписи" in response.text
    assert "Проверить подписание документов" in response.text
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
    assert 'class="file-row"' in response.text
    assert 'class="file-buttons"' in response.text
    assert 'id="kedo-file"' in response.text
    assert 'class="debug-panel"' in response.text
    assert 'class="debug-actions"' in response.text
    assert "formatClientDateTime(document.signed_at)" in response.text
    assert 'title="${escapeHtml(document.signed_at)}"' in response.text
    assert "updateDeploymentInfoTime()" in response.text
    assert 'document.querySelector("#deploy-info time")' in response.text
    assert "KONTUR_KEDO_TEST_FILENAME" not in response.text
    assert "Войти в Контур" not in response.text
    assert "Получить организации" not in response.text
    assert "Получить личные данные" not in response.text


def test_deployment_info_uses_deploy_environment(monkeypatch) -> None:
    monkeypatch.setenv("KONTUR_DEPLOYED_AT", "2026-05-17T12:30:40Z")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")

    response = client.get("/api/deployment")

    assert response.status_code == 200
    assert response.json() == {
        "deployed_at": "2026-05-17T12:30:40Z",
        "deployed_at_display": "2026-05-17 12:30:40 UTC",
        "source": "environment",
        "git_commit": "abcdef1234567890",
    }


def test_index_shows_deployment_info(monkeypatch) -> None:
    monkeypatch.setenv("KONTUR_DEPLOYED_AT", "2026-05-17T12:30:40Z")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")

    response = client.get("/")

    assert response.status_code == 200
    assert '<time datetime="2026-05-17T12:30:40Z">' in response.text
    assert "2026-05-17 12:30:40 UTC" in response.text
    assert "updateDeploymentInfoTime()" in response.text
    assert "commit abcdef1" in response.text


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


def test_kedo_test_document_normalizes_file_name_for_kedo(monkeypatch) -> None:
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
        assert file_name == "test_kedo.pdf"
        return KedoTestDocumentResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            employee_id="22222222-2222-2222-2222-222222222222",
            document_type_id=document_type_id or DEFAULT_KEDO_DOCUMENT_TYPE_ID,
            file_name=file_name,
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
            "file_name": "test-kedo.pdf",
            "file_content_base64": "aGVsbG8=",
        },
    )

    assert response.status_code == 200
    assert response.json()["file_name"] == "test_kedo.pdf"


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


def test_kedo_download_content(monkeypatch) -> None:
    def fake_download_content(_settings, *, file_id, file_name, access_token=None):
        assert file_id == "44444444-4444-4444-4444-444444444444"
        assert file_name == "test.pdf"
        assert access_token is None
        return KedoDownloadedFile(
            content=b"%PDF-content",
            content_type="application/pdf",
            file_name=file_name,
        )

    monkeypatch.setattr(app_module, "download_content", fake_download_content)

    response = client.get(
        "/api/kedo/contents/44444444-4444-4444-4444-444444444444",
        params={"filename": "test.pdf"},
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-content"
    assert response.headers["content-type"] == "application/pdf"
    assert "test.pdf" in response.headers["content-disposition"]


def test_kedo_download_document_print(monkeypatch) -> None:
    def fake_download_document_print(
        _settings,
        *,
        process_id,
        document_id,
        file_name,
        access_token=None,
    ):
        assert process_id == "55555555-5555-5555-5555-555555555555"
        assert document_id == "66666666-6666-6666-6666-666666666666"
        assert file_name == "66666666-6666-6666-6666-666666666666.pdf"
        assert access_token is None
        return KedoDownloadedFile(
            content=b"%PDF-print",
            content_type="application/pdf",
            file_name=file_name,
        )

    monkeypatch.setattr(app_module, "download_document_print", fake_download_document_print)

    response = client.get(
        "/api/kedo/processes/55555555-5555-5555-5555-555555555555"
        "/documents/66666666-6666-6666-6666-666666666666/print"
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-print"
    assert response.headers["content-type"] == "application/pdf"


def test_download_content_asks_kedo_for_octet_stream(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            assert method == "GET"
            assert url.endswith("/contents/file-id")
            assert kwargs["headers"]["Accept"] == "application/octet-stream"
            return kedo_client_module.httpx.Response(
                200,
                content=b"%PDF-content",
                headers={"content-type": "application/pdf"},
            )

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    file = kedo_client_module.download_content(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        file_id="file-id",
        file_name="test.pdf",
    )

    assert file.content == b"%PDF-content"
    assert file.content_type == "application/pdf"


def test_send_test_document_uses_processed_content(monkeypatch) -> None:
    process_payloads = []

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            if url.endswith("/contents"):
                assert method == "POST"
                assert kwargs["content"] == b"%PDF-test"
                return kedo_client_module.httpx.Response(
                    200,
                    json={"location": "upload-location"},
                )
            if url.endswith("/documents/process/tasks"):
                assert method == "POST"
                assert kwargs["json"]["content"] == {
                    "location": "upload-location",
                    "name": "test.pdf",
                }
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "id": "task-id",
                        "status": "Complete",
                        "result": {
                            "content": {
                                "location": "processed-location",
                                "name": "processed.pdf",
                            }
                        },
                    },
                )
            if url.endswith("/processes"):
                assert method == "POST"
                assert "/api/v1/" in url
                process_payloads.append(kwargs["json"])
                return kedo_client_module.httpx.Response(200, json=[{"id": "process-id"}])
            if url.endswith("/processes/process-id"):
                assert method == "GET"
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "id": "process-id",
                        "documents": {
                            "0": {
                                "id": "document-id",
                                "contentType": "Document",
                                "isDraft": False,
                                "content": {
                                    "location": "processed-location",
                                    "name": "processed.pdf",
                                },
                                "children": [],
                                "metadata": {},
                            }
                        },
                    },
                )
            raise AssertionError(f"Unexpected request URL: {url}")

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = send_test_document(
        Settings(
            _env_file=None,
            kedo_api_key="api-key",
            kedo_org_id="org-id",
        ),
        access_token="token",
        document_type_id=DEFAULT_KEDO_DOCUMENT_TYPE_ID,
        sender_id="sender-id",
        employee_id="employee-id",
        signature_type="Nep",
        due_days=2,
        file_name="test.pdf",
        file_bytes=b"%PDF-test",
    )

    process_document = process_payloads[0]["processes"][0]["documents"]["0"]
    assert process_document["content"]["location"] == "processed-location"
    assert process_document["content"]["name"] == "processed.pdf"
    assert response.content_location == "upload-location"
    assert response.processed_content_location == "processed-location"
    assert response.document_ids == ["document-id"]
    assert response.request_payload == process_payloads[0]
    assert response.download_checks == []


def test_send_test_document_requires_processed_content(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            if url.endswith("/contents"):
                return kedo_client_module.httpx.Response(
                    200,
                    json={"location": "upload-location"},
                )
            if url.endswith("/documents/process/tasks"):
                return kedo_client_module.httpx.Response(
                    200,
                    json={"id": "task-id", "status": "Complete", "result": {}},
                )
            if url.endswith("/processes"):
                raise AssertionError("Process must not be created without converted content.")
            raise AssertionError(f"Unexpected request URL: {url}")

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    with pytest.raises(KedoApiError, match="Content processing did not return converted content"):
        send_test_document(
            Settings(
                _env_file=None,
                kedo_api_key="api-key",
                kedo_org_id="org-id",
            ),
            access_token="token",
            document_type_id=DEFAULT_KEDO_DOCUMENT_TYPE_ID,
            sender_id="sender-id",
            employee_id="employee-id",
            signature_type="Nep",
            due_days=2,
            file_name="test.pdf",
            file_bytes=b"%PDF-test",
        )


def test_send_test_document_rejects_draft_process_document(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            if url.endswith("/contents"):
                return kedo_client_module.httpx.Response(
                    200,
                    json={"location": "upload-location"},
                )
            if url.endswith("/documents/process/tasks"):
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "id": "task-id",
                        "status": "Complete",
                        "result": {
                            "content": {
                                "location": "processed-location",
                                "name": "processed.pdf",
                            }
                        },
                    },
                )
            if url.endswith("/processes"):
                return kedo_client_module.httpx.Response(200, json=[{"id": "process-id"}])
            if url.endswith("/processes/process-id"):
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "id": "process-id",
                        "documents": {
                            "0": {
                                "id": "document-id",
                                "isDraft": True,
                                "children": [],
                                "metadata": {},
                            }
                        },
                    },
                )
            raise AssertionError(f"Unexpected request URL: {url}")

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    with pytest.raises(KedoApiError, match="Created document is still a draft"):
        send_test_document(
            Settings(
                _env_file=None,
                kedo_api_key="api-key",
                kedo_org_id="org-id",
            ),
            access_token="token",
            document_type_id=DEFAULT_KEDO_DOCUMENT_TYPE_ID,
            sender_id="sender-id",
            employee_id="employee-id",
            signature_type="Nep",
            due_days=2,
            file_name="test.pdf",
            file_bytes=b"%PDF-test",
        )


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
    def fake_get_kedo_document_types(_settings, *, filter_text=None, offset=0):
        assert filter_text is None
        assert offset == 0
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


def test_kedo_document_types_filters_by_name(monkeypatch) -> None:
    def fake_get_kedo_document_types(_settings, *, filter_text=None, offset=0):
        assert filter_text == "Несчастн"
        assert offset == 20
        return KedoDocumentTypesResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            document_types=[
                KedoDocumentType(
                    id="22222222-2222-2222-2222-222222222222",
                    name="Несчастный случай",
                )
            ],
        )

    monkeypatch.setattr(app_module, "get_kedo_document_types", fake_get_kedo_document_types)

    response = client.get(
        "/api/kedo/document-types",
        params={"filter": "Несчастн", "offset": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["document_types"]) == 1
    assert payload["document_types"][0]["name"] == "Несчастный случай"


def test_get_document_types_uses_bounded_filtered_query(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            assert method == "GET"
            assert url.endswith("/document-types")
            calls.append(kwargs["params"])
            return kedo_client_module.httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": "22222222-2222-2222-2222-222222222222",
                            "name": "Несчастный случай",
                        },
                        {
                            "id": "33333333-3333-3333-3333-333333333333",
                            "name": "Кадровый документ",
                        },
                    ]
                },
            )

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_document_types(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        filter_text="Несчастн",
    )

    assert calls == [
        {
            "limit": 10,
            "offset": 0,
            "includeDeleted": False,
            "includeDisabled": False,
            "includeSystems": False,
        }
    ]
    assert len(response.document_types) == 1
    assert response.document_types[0].name == "Несчастный случай"


def test_get_document_types_returns_first_20_without_filter(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            assert method == "GET"
            assert url.endswith("/document-types")
            calls.append(kwargs["params"])
            offset = kwargs["params"]["offset"]
            return kedo_client_module.httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": f"00000000-0000-0000-0000-{offset + index:012d}",
                            "name": f"Document {offset + index}",
                        }
                        for index in range(20)
                    ]
                },
            )

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_document_types(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
    )

    assert [call["offset"] for call in calls] == [0]
    assert all(call["limit"] == 20 for call in calls)
    assert all(call["includeSystems"] is True for call in calls)
    assert len(response.document_types) == 20
    assert response.document_types[-1].name == "Document 19"


def test_get_document_types_returns_next_20_without_filter(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            assert method == "GET"
            assert url.endswith("/document-types")
            calls.append(kwargs["params"])
            offset = kwargs["params"]["offset"]
            return kedo_client_module.httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": f"00000000-0000-0000-0000-{offset + index:012d}",
                            "name": f"Document {offset + index}",
                        }
                        for index in range(20)
                    ]
                },
            )

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_document_types(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        offset=20,
    )

    assert [call["offset"] for call in calls] == [20]
    assert all(call["limit"] == 20 for call in calls)
    assert len(response.document_types) == 20
    assert response.document_types[0].name == "Document 20"
    assert response.document_types[-1].name == "Document 39"


def test_get_document_types_returns_filtered_matches_after_late_timeout(monkeypatch) -> None:
    calls = 0

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise kedo_client_module.httpx.ReadTimeout("timed out")
            return kedo_client_module.httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": f"00000000-0000-0000-0000-{index:012d}",
                            "name": "Несчастный случай" if index == 0 else "Кадровый документ",
                        }
                        for index in range(100)
                    ]
                },
            )

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_document_types(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        filter_text="Несчастн",
    )

    assert calls == 2
    assert len(response.document_types) == 1
    assert response.document_types[0].name == "Несчастный случай"


def test_get_document_types_tries_system_types_after_no_matches(monkeypatch) -> None:
    include_systems_values = []

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            include_systems = kwargs["params"]["includeSystems"]
            include_systems_values.append(include_systems)
            if not include_systems:
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "result": [
                            {
                                "id": "33333333-3333-3333-3333-333333333333",
                                "name": "Other document",
                            }
                        ]
                    },
                )
            return kedo_client_module.httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": "22222222-2222-2222-2222-222222222222",
                            "name": "Несчастный случай",
                        }
                    ]
                },
            )

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_document_types(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        filter_text="Несчастн",
    )

    assert include_systems_values == [False, True]
    assert len(response.document_types) == 1
    assert response.document_types[0].name == "Несчастный случай"


def test_get_document_types_returns_empty_filtered_result_after_timeout(monkeypatch) -> None:
    calls = 0

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            nonlocal calls
            calls += 1
            raise kedo_client_module.httpx.ReadTimeout("timed out")

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_document_types(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        filter_text="test",
    )

    assert calls == 2
    assert response.document_types == []


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


def test_kedo_signed_documents(monkeypatch) -> None:
    def fake_get_signed_documents(_settings, *, limit, offset=None, days=None):
        assert limit == 25
        assert offset == "offset-id"
        assert days == 14
        return KedoSignedDocumentsResponse(
            org_id="11111111-1111-1111-1111-111111111111",
            last_offset="last-offset-id",
            signed_documents=[
                KedoSignedDocument(
                    process_id="22222222-2222-2222-2222-222222222222",
                    process_name="test.pdf",
                    document_key=0,
                    document_id="33333333-3333-3333-3333-333333333333",
                    document_name="test.pdf",
                    signed_at="2026-05-17T12:34:56Z",
                    action="Admission",
                    signature_id="44444444-4444-4444-4444-444444444444",
                    is_checked=True,
                    is_valid=True,
                )
            ],
        )

    monkeypatch.setattr(app_module, "get_signed_documents", fake_get_signed_documents)

    response = client.get(
        "/api/kedo/signed-documents",
        params={"limit": 25, "offset": "offset-id", "days": 14},
    )

    assert response.status_code == 200
    assert response.json()["signed_documents"][0]["signed_at"] == "2026-05-17T12:34:56Z"


def test_get_signed_documents_reads_signed_contents_from_recent_processes(monkeypatch) -> None:
    signed_at = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            if url.endswith("/processes/query"):
                assert method == "POST"
                assert kwargs["params"] == {"limit": 100, "offset": 0}
                assert set(kwargs["json"]["timeRange"]) == {"from", "to"}
                assert kwargs["json"]["detailedStatuses"] == ["Signed"]
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "result": [
                            {"id": "process-id", "createdAt": signed_at},
                        ],
                    },
                )
            if url.endswith("/processes/process-id"):
                assert method == "GET"
                assert kwargs["params"]["flat"] is True
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "id": "process-id",
                        "name": "test.pdf",
                        "createdAt": "2026-05-17T12:00:00Z",
                        "flatDocuments": [
                            {
                                "documentKey": 0,
                                "id": "document-id",
                                "content": {"name": "test.pdf"},
                            }
                        ],
                        "flatPath": {
                            "nodes": [
                                {
                                    "type": "Sign",
                                    "routeNodeId": "route-node-id",
                                    "isFinished": True,
                                    "signedContents": {
                                        "0": {
                                            "signature": {
                                                "isChecked": True,
                                                "isValid": True,
                                                "signature": {
                                                    "id": "signature-id",
                                                    "action": "Admission",
                                                    "location": "signature-location-id",
                                                    "createdAt": signed_at,
                                                    "author": {
                                                        "employeeId": "employee-id",
                                                        "userId": "user-id",
                                                    },
                                                },
                                            }
                                        }
                                    },
                                }
                            ]
                        },
                    },
                )
            raise AssertionError(f"Unexpected request URL: {url}")

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_signed_documents(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        days=1,
    )

    assert response.org_id == "org-id"
    assert response.last_offset is None
    assert len(response.signed_documents) == 1
    signed_document = response.signed_documents[0]
    assert signed_document.process_id == "process-id"
    assert signed_document.document_id == "document-id"
    assert signed_document.document_name == "test.pdf"
    assert signed_document.signed_at == signed_at
    assert signed_document.action == "Admission"
    assert signed_document.signature_location == "signature-location-id"
    assert signed_document.signer_employee_id == "employee-id"
    assert signed_document.is_valid is True


def test_get_signed_documents_skips_timed_out_process_details(monkeypatch) -> None:
    signed_at = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    class FakeClient:
        def __init__(self, *, base_url, timeout) -> None:
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def request(self, method, url, **kwargs):
            if url.endswith("/processes/query"):
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "result": [
                            {"id": "slow-process-id", "createdAt": signed_at},
                            {"id": "process-id", "createdAt": signed_at},
                        ],
                    },
                )
            if url.endswith("/processes/slow-process-id"):
                raise kedo_client_module.httpx.ReadTimeout("timed out")
            if url.endswith("/processes/process-id"):
                return kedo_client_module.httpx.Response(
                    200,
                    json={
                        "id": "process-id",
                        "flatDocuments": [
                            {
                                "documentKey": 0,
                                "id": "document-id",
                                "content": {"name": "test.pdf"},
                            }
                        ],
                        "flatPath": {
                            "nodes": [
                                {
                                    "type": "Sign",
                                    "signedContents": {
                                        "0": {
                                            "signature": {
                                                "signature": {
                                                    "createdAt": signed_at,
                                                    "author": {"employeeId": "employee-id"},
                                                },
                                            }
                                        }
                                    },
                                }
                            ]
                        },
                    },
                )
            raise AssertionError(f"Unexpected request URL: {url}")

    monkeypatch.setattr(kedo_client_module.httpx, "Client", FakeClient)

    response = get_signed_documents(
        Settings(_env_file=None, kedo_api_key="api-key", kedo_org_id="org-id"),
        access_token="token",
        days=1,
    )

    assert len(response.signed_documents) == 1
    assert response.signed_documents[0].process_id == "process-id"


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
    UUID(route["id"])
    assert route["target"]["id"] == "11111111-1111-1111-1111-111111111111"
    assert route["comment"] is None
    assert "allowedTypes" not in route
    assert "documentKeys" not in route
    assert sign_route["type"] == "Sign"
    UUID(sign_route["id"])
    assert sign_route["target"]["id"] == "22222222-2222-2222-2222-222222222222"
    assert sign_route["allowedTypes"] == ["Nep"]
    assert sign_route["documentKeys"] == [0]
    assert sign_route["allowedActions"] == ["Admission", "Rejection"]
    assert sign_route["next"] is None
    assert sign_route["comment"] is None
    assert sign_route["deadlineAt"] is None
    assert sign_route["deadline"] == {"deadlineAt": None, "relativeDeadlineAt": 3}


def test_build_process_payload_uses_single_sign_step_for_same_sender_and_signer() -> None:
    payload = _build_process_payload(
        Settings(_env_file=None),
        sender_id="11111111-1111-1111-1111-111111111111",
        employee_id="11111111-1111-1111-1111-111111111111",
        document_type_id="33333333-3333-3333-3333-333333333333",
        content={"location": "content-location", "name": "test.pdf"},
        signature_type="Pep",
        due_days=3,
    )

    route = payload["processes"][0]["route"]
    sign_route = route["next"]

    assert route["type"] == "NoAction"
    assert route["target"]["id"] == "11111111-1111-1111-1111-111111111111"
    assert sign_route["type"] == "Sign"
    assert sign_route["target"]["id"] == "11111111-1111-1111-1111-111111111111"
    assert sign_route["allowedTypes"] == ["Pep"]
    assert sign_route["documentKeys"] == [0]
    assert sign_route["allowedActions"] == ["Admission", "Rejection"]
    assert sign_route["next"] is None
    assert sign_route["deadline"] == {"deadlineAt": None, "relativeDeadlineAt": 3}
