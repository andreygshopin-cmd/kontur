import base64
import binascii
from functools import lru_cache
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from kontur_edo.kedo_client import (
    KedoApiError,
    KedoAuthError,
    KedoConnectivityResponse,
    KedoDocumentType,
    KedoDocumentTypesResponse,
    KedoEmployeesResponse,
    KedoSignatureTypesResponse,
    KedoTestDocumentResponse,
    check_connectivity,
    download_content,
    download_document_print,
    send_test_document,
)
from kontur_edo.kedo_client import (
    get_document_types as get_kedo_document_types,
)
from kontur_edo.kedo_client import (
    get_employees as get_kedo_employees,
)
from kontur_edo.kedo_client import (
    get_signature_types as get_kedo_signature_types,
)
from kontur_edo.settings import Settings

DEFAULT_KEDO_DOCUMENT_TYPE_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_KEDO_TEST_FILENAME = "document.pdf"
INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
DEFAULT_KEDO_FILE_EXTENSION = "pdf"


class HealthResponse(BaseModel):
    status: str


class KedoTestDocumentRequest(BaseModel):
    document_type_id: str | None = None
    sender_id: str | None = None
    employee_id: str | None = None
    signature_type: str | None = None
    due_days: int | None = None
    file_name: str | None = None
    file_content_base64: str | None = None


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
    .action-field { display: grid; gap: 4px; min-width: 180px; }
    .action-field input { padding: 10px 12px; }
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
    .json-block {
      margin: 0; max-height: 360px; overflow: auto; white-space: pre-wrap;
      background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px;
    }
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
        <label class="action-field" for="kedo-document-type-filter">
          Фильтр типов документов
          <input id="kedo-document-type-filter" type="text" value="Несчастн">
        </label>
        <button id="load-kedo-document-types" class="secondary">
          Получить типы документов КЭДО
        </button>
        <button id="load-kedo-employees" class="secondary">Получить сотрудников</button>
        <button id="load-kedo-signature-types" class="secondary">Получить типы подписи</button>
        <button id="send-kedo-test" class="ghost">Отправить тестовый файл в КЭДО</button>
      </div>
    </header>
    <div class="kedo-form">
      <label for="kedo-document-type-id">KONTUR_KEDO_DOCUMENT_TYPE_ID</label>
      <input
        id="kedo-document-type-id"
        type="text"
        value="00000000-0000-0000-0000-000000000001"
      >
      <label for="kedo-sender-id">Отправитель</label>
      <input id="kedo-sender-id" type="text" placeholder="Выберите отправителя">
      <label for="kedo-employee-id">Участник подписания</label>
      <input id="kedo-employee-id" type="text" placeholder="Выберите сотрудника">
      <label for="kedo-signature-type">Тип подписи</label>
      <input id="kedo-signature-type" type="text" value="Pep">
      <label for="kedo-due-days">Срок выполнения, календарные дни</label>
      <input id="kedo-due-days" type="number" min="1" step="1" value="1">
      <label for="kedo-file">Файл для отправки</label>
      <input id="kedo-file" type="file">
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
    const documentTypeFilterInput = document.getElementById("kedo-document-type-filter");
    const documentTypesButton = document.getElementById("load-kedo-document-types");
    const employeesButton = document.getElementById("load-kedo-employees");
    const signatureTypesButton = document.getElementById("load-kedo-signature-types");
    const kedoButton = document.getElementById("send-kedo-test");
    const kedoDocumentTypeInput = document.getElementById("kedo-document-type-id");
    const kedoSenderInput = document.getElementById("kedo-sender-id");
    const kedoEmployeeInput = document.getElementById("kedo-employee-id");
    const kedoSignatureTypeInput = document.getElementById("kedo-signature-type");
    const kedoDueDaysInput = document.getElementById("kedo-due-days");
    const kedoFileInput = document.getElementById("kedo-file");
    const buttons = [
      checkKedoButton,
      documentTypesButton,
      employeesButton,
      signatureTypesButton,
      kedoButton
    ];
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

    function bindEmployeeButtons() {
      contentNode.querySelectorAll("[data-employee-id]").forEach((button) => {
        button.addEventListener("click", () => {
          kedoSenderInput.value = button.dataset.employeeId || "";
          kedoEmployeeInput.value = button.dataset.employeeId || "";
          statusNode.textContent = "Отправитель и участник подписания выбраны";
          statusNode.className = "status muted";
        });
      });
    }

    function bindSignatureTypeButtons() {
      contentNode.querySelectorAll("[data-signature-type]").forEach((button) => {
        button.addEventListener("click", () => {
          kedoSignatureTypeInput.value = button.dataset.signatureType || "";
          statusNode.textContent = "Тип подписи выбран";
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

    function renderKedoEmployees(data) {
      const rows = data.employees.map((employee) => `
        <tr>
          <td>
            <button
              class="secondary"
              type="button"
              data-employee-id="${escapeHtml(employee.id)}"
            >Выбрать</button>
          </td>
          <td>${escapeHtml(employee.full_name || employee.login || "Без имени")}</td>
          <td><code>${escapeHtml(employee.id)}</code></td>
          <td><code>${escapeHtml(employee.user_id || "")}</code></td>
          <td>${escapeHtml(employee.login || "")}</td>
        </tr>
      `).join("");

      contentNode.innerHTML = rows ? `
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Сотрудник</th>
              <th>EmployeeId</th>
              <th>UserId</th>
              <th>Login</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      ` : `<span class="muted">Сотрудники КЭДО не найдены.</span>`;
      bindEmployeeButtons();
    }

    function renderKedoSignatureTypes(data) {
      const rows = data.signature_types.map((signatureType) => `
        <tr>
          <td>
            <button
              class="secondary"
              type="button"
              data-signature-type="${escapeHtml(signatureType)}"
            >Выбрать</button>
          </td>
          <td><code>${escapeHtml(signatureType)}</code></td>
        </tr>
      `).join("");

      contentNode.innerHTML = rows ? `
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Тип подписи</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      ` : `<span class="muted">Типы подписи не найдены.</span>`;
      bindSignatureTypeButtons();
    }

    function readFileAsBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = String(reader.result || "");
          resolve(result.includes(",") ? result.split(",", 2)[1] : result);
        };
        reader.onerror = () => reject(reader.error || new Error("Не удалось прочитать файл"));
        reader.readAsDataURL(file);
      });
    }

    async function getKedoPayload() {
      const documentTypeId = kedoDocumentTypeInput.value.trim();
      const senderId = kedoSenderInput.value.trim();
      const employeeId = kedoEmployeeInput.value.trim();
      const signatureType = kedoSignatureTypeInput.value.trim();
      const dueDays = Number.parseInt(kedoDueDaysInput.value, 10);
      const file = kedoFileInput.files && kedoFileInput.files[0];
      if (!file) throw new Error("Выберите файл для отправки.");
      const payload = {
        document_type_id: documentTypeId || null,
        sender_id: senderId || null,
        employee_id: employeeId || null,
        signature_type: signatureType || null,
        due_days: Number.isFinite(dueDays) && dueDays > 0 ? dueDays : 1,
        file_name: file.name
      };
      payload.file_content_base64 = await readFileAsBase64(file);
      return payload;
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

    function documentTypesUrl() {
      const filter = documentTypeFilterInput.value.trim();
      const query = filter ? `?filter=${encodeURIComponent(filter)}` : "";
      return `/api/kedo/document-types${query}`;
    }

    checkKedoButton.addEventListener("click", () => loadData(
      "/api/kedo/connectivity",
      renderKedoConnectivity,
      (data) => data.tls_connected ? "KEDO API доступен" : "KEDO API не отвечает полностью"
    ));

    documentTypesButton.addEventListener("click", () => loadData(
      documentTypesUrl(),
      renderKedoDocumentTypes,
      (data) => `Найдено типов документов КЭДО: ${data.document_types.length}`
    ));

    employeesButton.addEventListener("click", () => loadData(
      "/api/kedo/employees",
      renderKedoEmployees,
      (data) => `Найдено сотрудников КЭДО: ${data.employees.length}`
    ));

    signatureTypesButton.addEventListener("click", () => loadData(
      "/api/kedo/signature-types",
      renderKedoSignatureTypes,
      (data) => `Найдено типов подписи: ${data.signature_types.length}`
    ));

    kedoFileInput.addEventListener("change", () => {
      const file = kedoFileInput.files && kedoFileInput.files[0];
      if (file) statusNode.textContent = `Выбран файл: ${file.name}`;
    });

    kedoButton.addEventListener("click", async () => {
      try {
        const payload = await getKedoPayload();
        await loadData(
          "/api/kedo/test-document",
          renderKedoTestDocument,
          (data) => {
            const processCount = (data.process_ids || []).length || 1;
            const documentCount = (data.document_ids || []).length;
            return `Тестовый файл отправлен в КЭДО. ` +
              `Процессов: ${processCount}, документов: ${documentCount}`;
          },
          "POST",
          payload
        );
      } catch (error) {
        statusNode.textContent = "Ошибка";
        statusNode.className = "status error";
        contentNode.textContent = error.message;
      }
    });

    function renderKedoTestDocument(data) {
      const uploadedContentLocation = data.content_location || "";
      const processedContentLocation = data.processed_content_location || "";
      const rawResponse = JSON.stringify(data.raw_response || [], null, 2);
      const requestPayload = JSON.stringify(data.request_payload || {}, null, 2);
      const processDetails = JSON.stringify(data.process_details || [], null, 2);
      const downloadChecks = (data.download_checks || []).length
        ? JSON.stringify(data.download_checks, null, 2)
        : "Автоматическая проверка не запускалась, чтобы не ронять отправку по таймауту. "
          + "Используйте ссылки скачивания отдельно.";
      const firstProcessId = (data.process_ids || [])[0] || "";
      const firstDocumentId = (data.document_ids || [])[0] || "";
      const safeFileName = encodeURIComponent(data.file_name || "document.pdf");
      const contentDownloadUrl = processedContentLocation
        ? `/api/kedo/contents/${encodeURIComponent(processedContentLocation)}`
          + `?filename=${safeFileName}`
        : "";
      const printDownloadUrl = firstProcessId && firstDocumentId
        ? `/api/kedo/processes/${encodeURIComponent(firstProcessId)}`
          + `/documents/${encodeURIComponent(firstDocumentId)}/print`
        : "";
      const contentLink = contentDownloadUrl
        ? `<a href="${contentDownloadUrl}" target="_blank">Открыть</a>`
        : "";
      const printLink = printDownloadUrl
        ? `<a href="${printDownloadUrl}" target="_blank">Открыть</a>`
        : "";
      contentNode.innerHTML = `
        <div class="details">
          <div class="label">Организация</div><div><code>${escapeHtml(data.org_id)}</code></div>
          <div class="label">Сотрудник</div><div><code>${escapeHtml(data.employee_id)}</code></div>
          <div class="label">Тип документа</div>
          <div><code>${escapeHtml(data.document_type_id)}</code></div>
          <div class="label">Файл</div><div>${escapeHtml(data.file_name)}</div>
          <div class="label">Upload location</div>
          <div><code>${escapeHtml(uploadedContentLocation)}</code></div>
          <div class="label">Processed location</div>
          <div><code>${escapeHtml(processedContentLocation)}</code></div>
          <div class="label">Process ID</div>
          <div><code>${escapeHtml((data.process_ids || []).join(", "))}</code></div>
          <div class="label">Document ID</div>
          <div><code>${escapeHtml((data.document_ids || []).join(", "))}</code></div>
          <div class="label">Скачать content</div>
          <div>${contentLink}</div>
          <div class="label">Скачать print</div>
          <div>${printLink}</div>
          <div class="label">Проверка скачивания</div>
          <pre class="json-block"><code>${escapeHtml(downloadChecks)}</code></pre>
          <div class="label">Запрос процесса</div>
          <pre class="json-block"><code>${escapeHtml(requestPayload)}</code></pre>
          <div class="label">Ответ КЭДО</div>
          <pre class="json-block"><code>${escapeHtml(rawResponse)}</code></pre>
          <div class="label">Проверка процесса</div>
          <pre class="json-block"><code>${escapeHtml(processDetails)}</code></pre>
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
    raw_sender_id = payload.sender_id if payload else None
    raw_employee_id = payload.employee_id if payload else None
    raw_signature_type = payload.signature_type if payload else None
    raw_file_name = payload.file_name if payload else None
    document_type_id = _non_empty_or(raw_document_type_id, DEFAULT_KEDO_DOCUMENT_TYPE_ID)
    sender_id = _non_empty(raw_sender_id)
    employee_id = _non_empty(raw_employee_id)
    signature_type = _non_empty(raw_signature_type)
    due_days = max(payload.due_days or 1, 1) if payload else 1
    file_name = _safe_file_name(_non_empty_or(raw_file_name, DEFAULT_KEDO_TEST_FILENAME))
    file_bytes = _decode_file_content(payload.file_content_base64 if payload else None)

    try:
        return send_test_document(
            get_settings(),
            document_type_id=document_type_id,
            sender_id=sender_id,
            employee_id=employee_id,
            signature_type=signature_type,
            due_days=due_days,
            file_name=file_name,
            file_bytes=file_bytes,
        )
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error


@app.get("/api/kedo/contents/{file_id}")
def kedo_download_content(
    file_id: str,
    filename: str | None = Query(default=None),
) -> Response:
    try:
        file = download_content(
            get_settings(),
            file_id=file_id,
            file_name=_safe_file_name(filename or DEFAULT_KEDO_TEST_FILENAME),
        )
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error

    return _download_response(file.content, file.content_type, file.file_name)


@app.get("/api/kedo/processes/{process_id}/documents/{document_id}/print")
def kedo_download_document_print(process_id: str, document_id: str) -> Response:
    try:
        file = download_document_print(
            get_settings(),
            process_id=process_id,
            document_id=document_id,
            file_name=f"{document_id}.pdf",
        )
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error

    return _download_response(file.content, file.content_type, file.file_name)


@app.get("/api/kedo/connectivity", response_model=KedoConnectivityResponse)
def kedo_connectivity() -> KedoConnectivityResponse:
    return check_connectivity(get_settings())


@app.get("/api/kedo/document-types", response_model=KedoDocumentTypesResponse)
def kedo_document_types(
    filter_text: str | None = Query(default=None, alias="filter"),
) -> KedoDocumentTypesResponse:
    try:
        response = get_kedo_document_types(get_settings())
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error

    normalized_filter = filter_text.strip().casefold() if filter_text else ""
    if not normalized_filter:
        return response

    return KedoDocumentTypesResponse(
        org_id=response.org_id,
        document_types=[
            document_type
            for document_type in response.document_types
            if _document_type_matches_filter(document_type, normalized_filter)
        ],
    )


@app.get("/api/kedo/employees", response_model=KedoEmployeesResponse)
def kedo_employees() -> KedoEmployeesResponse:
    try:
        return get_kedo_employees(get_settings())
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error


@app.get("/api/kedo/signature-types", response_model=KedoSignatureTypesResponse)
def kedo_signature_types() -> KedoSignatureTypesResponse:
    return get_kedo_signature_types(get_settings())


def _non_empty_or(value: str | None, default: str) -> str:
    stripped = value.strip() if value else ""
    return stripped or default


def _non_empty(value: str | None) -> str | None:
    stripped = value.strip() if value else ""
    return stripped or None


def _document_type_matches_filter(document_type: KedoDocumentType, filter_text: str) -> bool:
    haystack = f"{document_type.id} {document_type.name or ''} {document_type.metadata}".casefold()
    return filter_text in haystack


def _safe_file_name(value: str) -> str:
    file_name = value.strip().replace("\x00", "")
    file_name = PureWindowsPath(file_name).name
    file_name = PurePosixPath(file_name).name
    parts = [part for part in file_name.split(".") if part]
    if not parts:
        return DEFAULT_KEDO_TEST_FILENAME

    extension = "".join(char for char in parts[-1].casefold() if char.isascii() and char.isalnum())
    if len(extension) not in {3, 4}:
        extension = DEFAULT_KEDO_FILE_EXTENSION

    name_parts = parts[:-1] or [parts[0]]
    safe_parts = [_safe_file_name_part(part) for part in name_parts]
    safe_name = ".".join(part for part in safe_parts if part).strip("._")
    return f"{safe_name or 'document'}.{extension}"


def _safe_file_name_part(value: str) -> str:
    safe_part = "".join(
        char if _is_kedo_file_name_char(char) else "_" for char in value.strip(" .")
    ).strip("_")
    return safe_part[:250]


def _is_kedo_file_name_char(char: str) -> bool:
    return (
        char == "_"
        or "0" <= char <= "9"
        or "A" <= char <= "Z"
        or "a" <= char <= "z"
        or "А" <= char <= "Я"
        or "а" <= char <= "я"
        or char in {"Ё", "ё"}
    )


def _decode_file_content(file_content_base64: str | None) -> bytes | None:
    if not file_content_base64:
        return None
    try:
        return base64.b64decode(file_content_base64, validate=True)
    except binascii.Error as error:
        raise HTTPException(status_code=400, detail="Invalid file_content_base64.") from error


def _download_response(content: bytes, content_type: str, file_name: str) -> Response:
    safe_name = _safe_file_name(file_name)
    quoted_name = quote(safe_name)
    content_disposition = (
        f"attachment; filename={quoted_name}; filename*=UTF-8''{quoted_name}"
    )
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": content_disposition},
    )


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
