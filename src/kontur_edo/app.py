import base64
import binascii
import os
from datetime import UTC, datetime
from functools import lru_cache
from html import escape
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
    KedoDocumentTypesResponse,
    KedoEmployeesResponse,
    KedoRecentDocumentsCompareResponse,
    KedoSignatureTypesResponse,
    KedoSignedDocumentsResponse,
    KedoStorageTestResponse,
    KedoTestDocumentResponse,
    check_connectivity,
    compare_recent_documents,
    download_content,
    download_document_print,
    get_signed_documents,
    send_test_document,
    test_temporary_storage,
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
APP_STARTED_AT = datetime.now(UTC)


class HealthResponse(BaseModel):
    status: str


class DeploymentInfoResponse(BaseModel):
    deployed_at: str
    deployed_at_display: str
    source: str
    git_commit: str | None = None


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
    deployment_info = _deployment_info()
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
    .title-stack { display: grid; gap: 6px; }
    h1 { margin: 0; font-size: 28px; line-height: 1.2; }
    .deploy-info { color: #667085; font-size: 14px; line-height: 1.35; }
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
    .kedo-form { margin-top: 18px; display: grid; gap: 8px; max-width: 900px; }
    .file-row {
      display: grid; grid-template-columns: minmax(260px, 360px) minmax(260px, 1fr);
      gap: 10px; align-items: end;
    }
    .file-field { display: grid; gap: 8px; }
    .file-buttons { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; }
    .debug-panel {
      margin-top: 18px; padding: 14px 16px; border: 1px solid #d9dee7; border-radius: 8px;
      background: #ffffff;
    }
    .debug-header { margin-bottom: 10px; color: #52606d; font-size: 14px; font-weight: 700; }
    .debug-actions { display: flex; flex-wrap: wrap; gap: 10px; }
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
      .file-row { grid-template-columns: 1fr; }
      .file-buttons { align-items: stretch; }
      .details { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div class="title-stack">
        <h1>Контур КЭДО</h1>
        __DEPLOY_INFO_HTML__
      </div>
      <div class="actions">
        <label class="action-field" for="kedo-document-type-filter">
          Фильтр типов документов
          <input id="kedo-document-type-filter" type="text" value="Несчастн">
        </label>
        <button id="load-kedo-document-types" class="secondary">
          Получить типы документов КЭДО
        </button>
        <button id="load-kedo-employees" class="secondary">Получить сотрудников</button>
        <button id="load-kedo-signature-types" class="secondary">Получить типы подписи</button>
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
      <div class="file-row">
        <div class="file-field">
          <label for="kedo-file">Файл для отправки</label>
          <input id="kedo-file" type="file">
        </div>
        <div class="file-buttons">
          <button id="send-kedo-test" class="ghost">Отправить тестовый файл в КЭДО</button>
          <button id="check-kedo-signatures" class="secondary">
            Проверить подписание документов
          </button>
        </div>
      </div>
    </div>
    <section class="debug-panel" aria-label="Отладка">
      <div class="debug-header">Отладка</div>
      <div class="debug-actions">
        <button id="check-kedo" class="secondary">Проверить КЭДО API</button>
        <button id="test-kedo-storage" class="secondary">Проверить временное хранилище</button>
        <button id="compare-kedo-documents" class="secondary">Сравнить последние документы</button>
      </div>
    </section>
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
    const storageTestButton = document.getElementById("test-kedo-storage");
    const compareDocumentsButton = document.getElementById("compare-kedo-documents");
    const checkSignaturesButton = document.getElementById("check-kedo-signatures");
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
      storageTestButton,
      compareDocumentsButton,
      checkSignaturesButton,
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

    function formatClientDateTime(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      return new Intl.DateTimeFormat("ru-RU", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short"
      }).format(date);
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

    function renderKedoSignedDocuments(data) {
      const allFields = {
        query: data.query || {},
        last_offset: data.last_offset || null,
        raw_events: data.raw_events || [],
        raw_signed_events: data.raw_signed_events || [],
        raw_processes: data.raw_processes || [],
        event_query_errors: data.event_query_errors || [],
        process_errors: data.process_errors || [],
        signed_documents: data.signed_documents || []
      };
      const allFieldsJson = JSON.stringify(allFields, null, 2);
      const rows = (data.signed_documents || []).map((document) => {
        const signerId = document.signer_employee_id || document.signer_user_id || "";
        const isValid = document.is_valid === null || document.is_valid === undefined
          ? ""
          : formatBoolean(document.is_valid);
        const signedAt = formatClientDateTime(document.signed_at);
        return `
        <tr>
          <td title="${escapeHtml(document.signed_at)}">${escapeHtml(signedAt)}</td>
          <td>${escapeHtml(document.action || "")}</td>
          <td>${escapeHtml(document.process_name || "")}</td>
          <td><code>${escapeHtml(document.process_id)}</code></td>
          <td>${escapeHtml(document.document_name || "")}</td>
          <td><code>${escapeHtml(document.document_id || "")}</code></td>
          <td><code>${escapeHtml(signerId)}</code></td>
          <td>${isValid}</td>
        </tr>
      `;
      }).join("");

      const tableHtml = rows ? `
        <table>
          <thead>
            <tr>
              <th>Дата подписи</th>
              <th>Действие</th>
              <th>Процесс</th>
              <th>ProcessId</th>
              <th>Документ</th>
              <th>DocumentId</th>
              <th>Подписант</th>
              <th>Подпись валидна</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="muted">lastOffset: <code>${escapeHtml(data.last_offset || "")}</code></p>
      ` : `
        <span class="muted">
          Подписанные документы в событиях КЭДО за последние 14 дней не найдены.
        </span>
      `;
      contentNode.innerHTML = `
        ${tableHtml}
        <h3>Все поля за последние 14 дней</h3>
        <pre class="json-block">${escapeHtml(allFieldsJson)}</pre>
      `;
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

    storageTestButton.addEventListener("click", async () => {
      try {
        const payload = await getKedoPayload();
        await loadData(
          "/api/kedo/storage-test",
          renderJsonDetails,
          (data) => {
            const failed = (data.stages || []).filter((stage) => !stage.ok).length;
            return failed
              ? `Проверка временного хранилища: ошибок ${failed}`
              : "Проверка временного хранилища успешна";
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

    compareDocumentsButton.addEventListener("click", () => loadData(
      "/api/kedo/recent-documents/compare?limit=2",
      renderJsonDetails,
      (data) => `Получено документов для сравнения: ${(data.documents || []).length}`
    ));

    checkSignaturesButton.addEventListener("click", () => loadData(
      "/api/kedo/signed-documents?limit=100&days=14",
      renderKedoSignedDocuments,
      (data) => `Найдено подписанных документов: ${(data.signed_documents || []).length}; ` +
        `событий подписи: ${(data.raw_signed_events || []).length}; ` +
        `всего событий за 14 дней: ${(data.raw_events || []).length}; ` +
        `ошибок запросов: ${(data.event_query_errors || []).length}`
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
      const uploadContentUrl = uploadedContentLocation
        ? `/api/kedo/contents/${encodeURIComponent(uploadedContentLocation)}`
          + `?filename=${safeFileName}`
        : "";
      const processedContentUrl = processedContentLocation
        ? `/api/kedo/contents/${encodeURIComponent(processedContentLocation)}`
          + `?filename=${safeFileName}`
        : "";
      const printDownloadUrl = firstProcessId && firstDocumentId
        ? `/api/kedo/processes/${encodeURIComponent(firstProcessId)}`
          + `/documents/${encodeURIComponent(firstDocumentId)}/print`
        : "";
      const uploadContentLink = uploadContentUrl
        ? `<a href="${uploadContentUrl}" target="_blank">Открыть</a>`
        : "";
      const processedContentLink = processedContentUrl
        ? `<a href="${processedContentUrl}" target="_blank">Открыть</a>`
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
          <div class="label">Скачать upload content</div>
          <div>${uploadContentLink}</div>
          <div class="label">Скачать processed content</div>
          <div>${processedContentLink}</div>
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

    function renderJsonDetails(data) {
      contentNode.innerHTML = `
        <pre class="json-block"><code>${escapeHtml(JSON.stringify(data, null, 2))}</code></pre>
      `;
    }
  </script>
</body>
</html>
""".replace("__DEPLOY_INFO_HTML__", _deployment_info_html(deployment_info))


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/deployment", response_model=DeploymentInfoResponse)
def deployment_info() -> DeploymentInfoResponse:
    return _deployment_info()


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


@app.post("/api/kedo/storage-test", response_model=KedoStorageTestResponse)
def kedo_storage_test(
    payload: KedoTestDocumentRequest | None = None,
) -> KedoStorageTestResponse:
    raw_document_type_id = payload.document_type_id if payload else None
    raw_file_name = payload.file_name if payload else None
    file_bytes = _decode_file_content(payload.file_content_base64 if payload else None)
    document_type_id = _non_empty_or(raw_document_type_id, DEFAULT_KEDO_DOCUMENT_TYPE_ID)
    file_name = _safe_file_name(_non_empty_or(raw_file_name, DEFAULT_KEDO_TEST_FILENAME))
    try:
        return test_temporary_storage(
            get_settings(),
            document_type_id=document_type_id,
            file_name=file_name,
            file_bytes=file_bytes,
        )
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error


@app.get("/api/kedo/recent-documents/compare", response_model=KedoRecentDocumentsCompareResponse)
def kedo_compare_recent_documents(
    limit: int = Query(default=2, ge=2, le=10),
) -> KedoRecentDocumentsCompareResponse:
    try:
        return compare_recent_documents(get_settings(), limit=limit)
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error


@app.get("/api/kedo/signed-documents", response_model=KedoSignedDocumentsResponse)
def kedo_signed_documents(
    limit: int = Query(default=100, ge=1, le=100),
    offset: str | None = Query(default=None),
    days: int = Query(default=14, ge=1, le=365),
) -> KedoSignedDocumentsResponse:
    try:
        return get_signed_documents(get_settings(), limit=limit, offset=offset, days=days)
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
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
        return get_kedo_document_types(get_settings(), filter_text=filter_text)
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise _to_network_http_exception("Kontur KEDO API", error) from error


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


def _deployment_info() -> DeploymentInfoResponse:
    raw_deployed_at = os.getenv("KONTUR_DEPLOYED_AT") or os.getenv("RENDER_DEPLOYED_AT")
    if raw_deployed_at:
        deployed_at, deployed_at_display = _normalize_deployment_time(raw_deployed_at)
        source = "environment"
    else:
        deployed_at = _format_deployment_iso(APP_STARTED_AT)
        deployed_at_display = _format_deployment_display(APP_STARTED_AT)
        source = "process_start"

    return DeploymentInfoResponse(
        deployed_at=deployed_at,
        deployed_at_display=deployed_at_display,
        source=source,
        git_commit=_non_empty(os.getenv("RENDER_GIT_COMMIT")),
    )


def _deployment_info_html(deployment: DeploymentInfoResponse) -> str:
    commit_text = f" - commit {escape(deployment.git_commit[:7])}" if deployment.git_commit else ""
    return (
        '<div id="deploy-info" class="deploy-info">'
        "Последний деплой: "
        f'<time datetime="{escape(deployment.deployed_at)}">'
        f"{escape(deployment.deployed_at_display)}</time>{commit_text}</div>"
    )


def _normalize_deployment_time(value: str) -> tuple[str, str]:
    parsed = _parse_deployment_time(value)
    if parsed is None:
        return value, value
    return _format_deployment_iso(parsed), _format_deployment_display(parsed)


def _parse_deployment_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_deployment_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _format_deployment_display(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _non_empty_or(value: str | None, default: str) -> str:
    stripped = value.strip() if value else ""
    return stripped or default


def _non_empty(value: str | None) -> str | None:
    stripped = value.strip() if value else ""
    return stripped or None


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
