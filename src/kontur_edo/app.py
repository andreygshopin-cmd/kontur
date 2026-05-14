from functools import lru_cache

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from kontur_edo.kedo_client import (
    KedoApiError,
    KedoAuthError,
    KedoConnectivityResponse,
    KedoDocumentTypesResponse,
    KedoTestDocumentResponse,
    check_connectivity,
    send_test_document,
)
from kontur_edo.kedo_client import (
    get_document_types as get_kedo_document_types,
)
from kontur_edo.settings import Settings

DEFAULT_KEDO_DOCUMENT_TYPE_ID = "00000000-0000-0000-0000-000000000003"
DEFAULT_KEDO_TEST_FILENAME = "document.pdf"


class HealthResponse(BaseModel):
    status: str


class KedoTestDocumentRequest(BaseModel):
    document_type_id: str | None = None
    file_name: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()


app = FastAPI(
    title="Kontur KEDO Gateway",
    description="Gateway service for Kontur KEDO API integration.",
    version="0.1.0",
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Контур КЭДО</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #1f2933; }
    main { max-width: 980px; margin: 0 auto; padding: 40px 20px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1 { margin: 0; font-size: 28px; line-height: 1.2; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }
    button {
      border: 0; border-radius: 6px; background: #0f766e; color: white;
      padding: 12px 18px; font-size: 16px; cursor: pointer; text-decoration: none;
      display: inline-flex; align-items: center; justify-content: center;
    }
    button.secondary { background: #2563eb; }
    button.ghost { background: #475569; }
    button:disabled { opacity: .65; cursor: progress; }
    .kedo-form { margin-top: 18px; display: grid; gap: 8px; max-width: 520px; }
    label { color: #52606d; font-size: 14px; font-weight: 700; }
    input {
      width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1;
      border-radius: 6px; padding: 11px 12px; font-size: 15px;
      color: #1f2933; background: white;
    }
    .panel { margin-top: 28px; background: white; border: 1px solid #d9dee7; }
    .panel { border-radius: 8px; }
    .status { padding: 16px 18px; border-bottom: 1px solid #e5e9f0; font-weight: 700; }
    .content { padding: 18px; white-space: pre-line; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td {
      text-align: left; padding: 10px; border-bottom: 1px solid #edf0f4; vertical-align: top;
    }
    th { color: #52606d; background: #fafbfc; }
    code { word-break: break-all; }
    .error { color: #b42318; }
    .muted { color: #667085; }
    .details { display: grid; grid-template-columns: 180px 1fr; gap: 10px 16px; }
    .label { color: #52606d; font-weight: 700; }
    .metadata { max-width: 280px; white-space: pre-wrap; }
    @media (max-width: 720px) {
      header { align-items: flex-start; flex-direction: column; }
      .actions { justify-content: flex-start; }
      .details { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Контур КЭДО</h1>
      <div class="actions">
        <button id="check-kedo" class="secondary">Проверить КЭДО API</button>
        <button id="load-kedo-document-types" class="secondary">
          Получить типы документов КЭДО
        </button>
        <button id="send-kedo-test" class="ghost">Отправить тестовый файл в КЭДО</button>
      </div>
    </header>
    <div class="kedo-form">
      <label for="kedo-document-type-id">KONTUR_KEDO_DOCUMENT_TYPE_ID</label>
      <input
        id="kedo-document-type-id"
        type="text"
        value="00000000-0000-0000-0000-000000000003"
      >
      <label for="kedo-test-filename">KONTUR_KEDO_TEST_FILENAME</label>
      <input id="kedo-test-filename" type="text" value="document.pdf">
    </div>
    <section class="panel">
      <div id="status" class="status muted">Готово к проверке КЭДО.</div>
      <div id="content" class="content muted">
        Получите типы документов КЭДО, выберите подходящий тип и отправьте тестовый файл.
      </div>
    </section>
  </main>
  <script>
    const checkKedoButton = document.getElementById("check-kedo");
    const documentTypesButton = document.getElementById("load-kedo-document-types");
    const kedoButton = document.getElementById("send-kedo-test");
    const kedoDocumentTypeInput = document.getElementById("kedo-document-type-id");
    const kedoFilenameInput = document.getElementById("kedo-test-filename");
    const buttons = [checkKedoButton, documentTypesButton, kedoButton];
    const statusNode = document.getElementById("status");
    const contentNode = document.getElementById("content");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      })[char]);
    }

    function setLoading(isLoading) {
      buttons.forEach((button) => { button.disabled = isLoading; });
    }

    function formatErrorDetail(detail) {
      if (typeof detail === "string") return detail;
      if (detail && typeof detail === "object") {
        const parts = [];
        if (detail.stage) parts.push(`Этап: ${detail.stage}`);
        if (detail.kontur_status_code) {
          parts.push(`HTTP Контур: ${detail.kontur_status_code}`);
        }
        if (detail.message) parts.push(`Сообщение: ${detail.message}`);
        return parts.length ? parts.join("\\n") : JSON.stringify(detail, null, 2);
      }
      return "Ошибка запроса";
    }

    function summarizeHtmlError(text, response) {
      const title = text.match(/<title[^>]*>(.*?)<\\/title>/is)?.[1];
      const heading = text.match(/<h1[^>]*>(.*?)<\\/h1>/is)?.[1];
      const summary = title || heading || response.statusText || "HTML-страница ошибки";
      return `${response.status} ${summary.replace(/<[^>]*>/g, " ").trim()}`;
    }

    async function readResponseBody(response) {
      const text = await response.text();
      if (!text) return null;
      try {
        return JSON.parse(text);
      } catch {
        const looksLikeHtml = /<!doctype html|<html/i.test(text);
        const message = looksLikeHtml
          ? summarizeHtmlError(text, response)
          : text.replace(/\\s+/g, " ").trim().slice(0, 600);
        return {
          detail: {
            stage: `HTTP ${response.status}`,
            message
          }
        };
      }
    }

    function renderKedoConnectivity(data) {
      const addresses = (data.resolved_addresses || []).join(", ");
      const tlsStatus = data.tls_connected ? escapeHtml(data.tls_version || "OK") : "Ошибка";
      const error = data.dns_error || data.tcp_error || data.tls_error || "";
      contentNode.innerHTML = `
        <div class="details">
          <div class="label">URL</div><div><code>${escapeHtml(data.url)}</code></div>
          <div class="label">Host</div><div><code>${escapeHtml(data.host)}</code></div>
          <div class="label">IP</div><div><code>${escapeHtml(addresses)}</code></div>
          <div class="label">TCP</div><div>${data.tcp_connected ? "OK" : "Ошибка"}</div>
          <div class="label">TLS</div><div>${tlsStatus}</div>
          <div class="label">Ошибка</div><div><code>${escapeHtml(error)}</code></div>
          <div class="label">Время</div><div>${escapeHtml(data.elapsed_ms)} ms</div>
        </div>
      `;
    }

    function formatBoolean(value) {
      return value ? "Да" : "Нет";
    }

    function bindDocumentTypeButtons() {
      contentNode.querySelectorAll("[data-document-type-id]").forEach((button) => {
        button.addEventListener("click", () => {
          kedoDocumentTypeInput.value = button.dataset.documentTypeId || "";
          statusNode.textContent = "Тип документа выбран";
          statusNode.className = "status muted";
        });
      });
    }

    function metadataText(documentType) {
      const metadata = documentType.metadata || {};
      return Object.keys(metadata).length ? JSON.stringify(metadata, null, 2) : "";
    }

    function renderKedoDocumentTypes(data) {
      const rows = data.document_types.map((documentType) => `
        <tr>
          <td>
            <button
              class="secondary"
              type="button"
              data-document-type-id="${escapeHtml(documentType.id)}"
            >Выбрать</button>
          </td>
          <td>${escapeHtml(documentType.name || "Без названия")}</td>
          <td><code>${escapeHtml(documentType.id)}</code></td>
          <td>${formatBoolean(documentType.is_default)}</td>
          <td>${formatBoolean(documentType.is_disabled)}</td>
          <td>${formatBoolean(documentType.is_formalized)}</td>
          <td class="metadata"><code>${escapeHtml(metadataText(documentType))}</code></td>
        </tr>
      `).join("");

      contentNode.innerHTML = rows ? `
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Тип документа</th>
              <th>DocumentTypeId</th>
              <th>Default</th>
              <th>Disabled</th>
              <th>Formalized</th>
              <th>Metadata</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      ` : `<span class="muted">Типы документов КЭДО не найдены.</span>`;
      bindDocumentTypeButtons();
    }

    function getKedoPayload() {
      const documentTypeId = kedoDocumentTypeInput.value.trim();
      const fileName = kedoFilenameInput.value.trim();
      return {
        document_type_id: documentTypeId || null,
        file_name: fileName || null
      };
    }

    async function loadData(url, onSuccess, successTitle, method = "GET", body = null) {
      setLoading(true);
      statusNode.textContent = "Запрос в Контур...";
      statusNode.className = "status muted";
      contentNode.textContent = "";

      try {
        const requestOptions = { method };
        if (body !== null) {
          requestOptions.headers = { "Content-Type": "application/json" };
          requestOptions.body = JSON.stringify(body);
        }
        const response = await fetch(url, requestOptions);
        const data = await readResponseBody(response);
        if (!response.ok) throw new Error(formatErrorDetail(data?.detail));
        statusNode.textContent = successTitle(data);
        onSuccess(data);
      } catch (error) {
        statusNode.textContent = "Ошибка";
        statusNode.className = "status error";
        contentNode.textContent = error.message;
      } finally {
        setLoading(false);
      }
    }

    checkKedoButton.addEventListener("click", () => loadData(
      "/api/kedo/connectivity",
      renderKedoConnectivity,
      (data) => data.tls_connected ? "KEDO API доступен" : "KEDO API не отвечает полностью"
    ));

    documentTypesButton.addEventListener("click", () => loadData(
      "/api/kedo/document-types",
      renderKedoDocumentTypes,
      (data) => `Найдено типов документов КЭДО: ${data.document_types.length}`
    ));

    kedoButton.addEventListener("click", () => loadData(
      "/api/kedo/test-document",
      renderKedoTestDocument,
      (data) => `Тестовый файл отправлен в КЭДО. ` +
        `Процессов: ${(data.process_ids || []).length || 1}`,
      "POST",
      getKedoPayload()
    ));

    function renderKedoTestDocument(data) {
      const contentLocation = data.processed_content_location || data.content_location || "";
      contentNode.innerHTML = `
        <div class="details">
          <div class="label">Организация</div><div><code>${escapeHtml(data.org_id)}</code></div>
          <div class="label">Сотрудник</div><div><code>${escapeHtml(data.employee_id)}</code></div>
          <div class="label">Тип документа</div>
          <div><code>${escapeHtml(data.document_type_id)}</code></div>
          <div class="label">Файл</div><div>${escapeHtml(data.file_name)}</div>
          <div class="label">Content location</div>
          <div><code>${escapeHtml(contentLocation)}</code></div>
          <div class="label">Process ID</div>
          <div><code>${escapeHtml((data.process_ids || []).join(", "))}</code></div>
        </div>
      `;
    }
  </script>
</body>
</html>
"""


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/kedo/test-document", response_model=KedoTestDocumentResponse)
def kedo_test_document(
    payload: KedoTestDocumentRequest | None = None,
) -> KedoTestDocumentResponse:
    raw_document_type_id = payload.document_type_id if payload else None
    raw_file_name = payload.file_name if payload else None
    document_type_id = _non_empty_or(raw_document_type_id, DEFAULT_KEDO_DOCUMENT_TYPE_ID)
    file_name = _non_empty_or(raw_file_name, DEFAULT_KEDO_TEST_FILENAME)

    try:
        return send_test_document(
            get_settings(),
            document_type_id=document_type_id,
            file_name=file_name,
        )
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error


@app.get("/api/kedo/connectivity", response_model=KedoConnectivityResponse)
def kedo_connectivity() -> KedoConnectivityResponse:
    return check_connectivity(get_settings())


@app.get("/api/kedo/document-types", response_model=KedoDocumentTypesResponse)
def kedo_document_types() -> KedoDocumentTypesResponse:
    try:
        return get_kedo_document_types(get_settings())
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error


def _non_empty_or(value: str | None, default: str) -> str:
    stripped = value.strip() if value else ""
    return stripped or default


def _to_http_exception(error: KedoApiError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "stage": error.stage,
            "kontur_status_code": error.status_code,
            "message": error.response_text,
        },
    )


def _to_network_http_exception(stage: str, error: httpx.HTTPError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "stage": stage,
            "kontur_status_code": 0,
            "message": f"{type(error).__name__}: {error}",
        },
    )
