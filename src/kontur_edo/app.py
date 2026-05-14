from dataclasses import dataclass
from functools import lru_cache
from secrets import token_urlsafe
from time import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from kontur_edo.kedo_client import (
    KedoApiError,
    KedoAuthError,
    KedoTestDocumentResponse,
    send_test_document,
)
from kontur_edo.kontur_client import (
    KonturApiError,
    KonturAuthError,
    KonturOrganizationsResponse,
    KonturTokenResponse,
    KonturUserResponse,
    build_authorization_url,
    exchange_authorization_code,
    get_current_user,
    get_organizations,
)
from kontur_edo.settings import Settings

SESSION_COOKIE_NAME = "kontur_session"
AUTH_STATE_TTL_SECONDS = 600


@dataclass
class PendingAuth:
    redirect_uri: str
    created_at: float


@dataclass
class UserSession:
    token: KonturTokenResponse
    created_at: float


_PENDING_AUTH: dict[str, PendingAuth] = {}
_SESSIONS: dict[str, UserSession] = {}


class HealthResponse(BaseModel):
    status: str


class AuthStatusResponse(BaseModel):
    authenticated: bool


class ConfigResponse(BaseModel):
    kontur_base_url: str
    kontur_auth_base_url: str
    scope: str
    redirect_uri: str | None
    app_name: str | None
    api_key_configured: bool
    client_id_configured: bool
    client_secret_configured: bool
    login_configured: bool
    password_configured: bool
    kedo_base_url: str
    kedo_api_key_configured: bool
    kedo_org_id: str | None
    kedo_employee_id: str | None
    kedo_document_type_id: str | None
    kedo_document_type_name: str | None
    kedo_signature_types: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


app = FastAPI(
    title="Kontur EDO Gateway",
    description="Gateway service for Kontur EDO API integration.",
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
  <title>Контур ЭДО</title>
  <style>
    :root { color-scheme: light; font-family: Arial, sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #1f2933; }
    main { max-width: 980px; margin: 0 auto; padding: 40px 20px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1 { margin: 0; font-size: 28px; line-height: 1.2; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }
    button, a.button {
      border: 0; border-radius: 6px; background: #0f766e; color: white;
      padding: 12px 18px; font-size: 16px; cursor: pointer; text-decoration: none;
      display: inline-flex; align-items: center; justify-content: center;
    }
    button.secondary, a.secondary { background: #2563eb; }
    button.ghost, a.ghost { background: #475569; }
    button:disabled { opacity: .65; cursor: progress; }
    .panel { margin-top: 28px; background: white; border: 1px solid #d9dee7; border-radius: 8px; }
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
      <h1>Контур ЭДО</h1>
      <div class="actions">
        <a href="/auth/kontur/login" class="button ghost" id="login">Войти в Контур</a>
        <button id="load-organizations">Получить организации</button>
        <button id="load-user" class="secondary">Получить личные данные</button>
        <button id="send-kedo-test" class="ghost">Отправить тестовый файл в КЭДО</button>
      </div>
    </header>
    <section class="panel">
      <div id="status" class="status muted">Проверяем вход...</div>
      <div id="content" class="content muted">Для доступа к данным сначала войдите в Контур.</div>
    </section>
  </main>
  <script>
    const organizationsButton = document.getElementById("load-organizations");
    const userButton = document.getElementById("load-user");
    const kedoButton = document.getElementById("send-kedo-test");
    const loginLink = document.getElementById("login");
    const buttons = [organizationsButton, userButton, kedoButton];
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
        if (detail.kontur_status_code) parts.push(`HTTP Контур: ${detail.kontur_status_code}`);
        if (detail.message) parts.push(`Сообщение: ${detail.message}`);
        return parts.length ? parts.join("\\n") : JSON.stringify(detail, null, 2);
      }
      return "Ошибка запроса";
    }

    function renderOrganizations(data) {
      const rows = data.organizations.flatMap((org) => {
        const boxes = org.boxes.length ? org.boxes : [{ box_id: "", title: "" }];
        return boxes.map((box) => `
          <tr>
            <td>${escapeHtml(org.name || "Без названия")}</td>
            <td>${escapeHtml(org.inn || "")}</td>
            <td>${escapeHtml(org.kpp || "")}</td>
            <td><code>${escapeHtml(box.box_id)}</code></td>
          </tr>
        `);
      }).join("");

      contentNode.innerHTML = rows ? `
        <table>
          <thead><tr><th>Организация</th><th>ИНН</th><th>КПП</th><th>BoxId</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      ` : `<span class="muted">Организации не найдены.</span>`;
    }

    function renderUser(user) {
      const fullName = [user.last_name, user.first_name, user.middle_name]
        .filter(Boolean)
        .join(" ");
      contentNode.innerHTML = `
        <div class="details">
          <div class="label">ФИО</div><div>${escapeHtml(fullName || "Не передано")}</div>
          <div class="label">Фамилия</div><div>${escapeHtml(user.last_name || "Не передано")}</div>
          <div class="label">Email</div><div>${escapeHtml(user.email || "Не передано")}</div>
          <div class="label">Login</div><div>${escapeHtml(user.login || "Не передано")}</div>
          <div class="label">User ID</div><div><code>${escapeHtml(user.user_id || "")}</code></div>
        </div>
      `;
    }

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

    async function renderConfigHint() {
      const response = await fetch("/api/config");
      const config = await response.json();
      if (contentNode.dataset.touched === "true") return;
      contentNode.innerHTML = `
        <div class="details">
          <div class="label">Redirect URI</div>
          <div><code>${escapeHtml(config.redirect_uri || "")}</code></div>
          <div class="label">Scope</div>
          <div><code>${escapeHtml(config.scope || "")}</code></div>
          <div class="label">KEDO API</div>
          <div><code>${escapeHtml(config.kedo_base_url || "")}</code></div>
          <div class="label">KEDO target</div>
          <div><code>${escapeHtml(config.kedo_employee_id || "auto")}</code></div>
        </div>
      `;
    }

    async function refreshAuthStatus() {
      const response = await fetch("/api/auth/status");
      const data = await response.json();
      statusNode.textContent = data.authenticated ? "Вход выполнен" : "Нужно войти в Контур";
      loginLink.textContent = data.authenticated ? "Войти заново" : "Войти в Контур";
    }

    async function loadData(url, onSuccess, successTitle, method = "GET") {
      setLoading(true);
      statusNode.textContent = "Запрос в Контур...";
      statusNode.className = "status muted";
      contentNode.textContent = "";
      contentNode.dataset.touched = "true";

      try {
        const response = await fetch(url, { method });
        const data = await response.json();
        if (response.status === 401) {
          window.location.href = "/auth/kontur/login";
          return;
        }
        if (!response.ok) throw new Error(formatErrorDetail(data.detail));
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

    organizationsButton.addEventListener("click", () => loadData(
      "/api/kontur/organizations",
      renderOrganizations,
      (data) => `Найдено организаций: ${data.organizations.length}`
    ));

    userButton.addEventListener("click", () => loadData(
      "/api/kontur/user",
      renderUser,
      () => "Личные данные получены"
    ));

    kedoButton.addEventListener("click", () => loadData(
      "/api/kedo/test-document",
      renderKedoTestDocument,
      (data) => `Тестовый файл отправлен в КЭДО. ` +
        `Процессов: ${(data.process_ids || []).length || 1}`,
      "POST"
    ));

    refreshAuthStatus().catch(() => {
      statusNode.textContent = "Не удалось проверить вход";
      statusNode.className = "status error";
    });
    renderConfigHint().catch(() => {});
  </script>
</body>
</html>
"""


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/auth/status", response_model=AuthStatusResponse)
def auth_status(request: Request) -> AuthStatusResponse:
    return AuthStatusResponse(authenticated=_get_session(request) is not None)


@app.get("/auth/kontur/login")
def kontur_login(request: Request) -> RedirectResponse:
    settings = get_settings()
    state = token_urlsafe(24)
    nonce = token_urlsafe(24)
    redirect_uri = _get_redirect_uri(request, settings)
    _cleanup_pending_auth()
    _PENDING_AUTH[state] = PendingAuth(redirect_uri=redirect_uri, created_at=time())

    try:
        authorization_url = build_authorization_url(
            settings,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
        )
    except KonturAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return RedirectResponse(authorization_url)


@app.get("/auth/kontur/callback", response_model=None)
def kontur_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse | HTMLResponse:
    if error:
        return _auth_result_page("Ошибка входа", error_description or error)

    if not code or not state or state not in _PENDING_AUTH:
        return _auth_result_page("Ошибка входа", "Некорректный или устаревший state.")

    pending_auth = _PENDING_AUTH.pop(state)

    try:
        token = exchange_authorization_code(
            get_settings(),
            code=code,
            redirect_uri=pending_auth.redirect_uri,
        )
    except (KonturAuthError, KonturApiError, httpx.HTTPError) as exc:
        return _auth_result_page("Ошибка получения токена", str(exc))

    session_id = token_urlsafe(32)
    _SESSIONS[session_id] = UserSession(token=token, created_at=time())
    response = RedirectResponse("/")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=token.expires_in or 3600,
    )
    return response


@app.get("/api/config", response_model=ConfigResponse)
def config(request: Request) -> ConfigResponse:
    settings = get_settings()

    return ConfigResponse(
        kontur_base_url=str(settings.base_url),
        kontur_auth_base_url=str(settings.auth_base_url),
        scope=settings.scope,
        redirect_uri=_get_redirect_uri(request, settings),
        app_name=settings.app_name,
        api_key_configured=bool(settings.api_key),
        client_id_configured=bool(settings.client_id or settings.app_name),
        client_secret_configured=bool(settings.client_secret or settings.api_key),
        login_configured=bool(settings.login),
        password_configured=bool(settings.password),
        kedo_base_url=str(settings.kedo_base_url),
        kedo_api_key_configured=bool(
            settings.kedo_api_key or settings.client_secret or settings.api_key
        ),
        kedo_org_id=settings.kedo_org_id,
        kedo_employee_id=settings.kedo_employee_id,
        kedo_document_type_id=settings.kedo_document_type_id,
        kedo_document_type_name=settings.kedo_document_type_name,
        kedo_signature_types=settings.kedo_signature_types,
    )


@app.get("/api/kontur/organizations", response_model=KonturOrganizationsResponse)
def kontur_organizations(request: Request) -> KonturOrganizationsResponse:
    session = _require_session(request)

    try:
        return get_organizations(get_settings(), session.token.access_token)
    except KonturApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Kontur API is unavailable.") from error


@app.get("/api/kontur/user", response_model=KonturUserResponse)
def kontur_user(request: Request) -> KonturUserResponse:
    session = _require_session(request)

    try:
        return get_current_user(get_settings(), session.token.access_token)
    except KonturApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Kontur API is unavailable.") from error


@app.post("/api/kedo/test-document", response_model=KedoTestDocumentResponse)
def kedo_test_document(request: Request) -> KedoTestDocumentResponse:
    session = _get_session(request)

    try:
        return send_test_document(
            get_settings(),
            access_token=session.token.access_token if session else None,
        )
    except KedoAuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except KedoApiError as error:
        raise _to_http_exception(error) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Kontur KEDO API is unavailable.") from error


def _get_redirect_uri(request: Request, settings: Settings) -> str:
    if settings.redirect_uri:
        return settings.redirect_uri

    return str(request.url_for("kontur_callback"))


def _get_session(request: Request) -> UserSession | None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    return _SESSIONS.get(session_id)


def _require_session(request: Request) -> UserSession:
    session = _get_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return session


def _cleanup_pending_auth() -> None:
    now = time()
    expired_states = [
        state
        for state, pending_auth in _PENDING_AUTH.items()
        if now - pending_auth.created_at > AUTH_STATE_TTL_SECONDS
    ]
    for state in expired_states:
        del _PENDING_AUTH[state]


def _to_http_exception(error: KonturApiError | KedoApiError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "stage": error.stage,
            "kontur_status_code": error.status_code,
            "message": error.response_text,
        },
    )


def _auth_result_page(title: str, message: str) -> HTMLResponse:
    escaped_title = title.replace("<", "&lt;").replace(">", "&gt;")
    escaped_message = message.replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{escaped_title}</title>
</head>
<body>
  <h1>{escaped_title}</h1>
  <pre>{escaped_message}</pre>
  <a href="/">Вернуться</a>
</body>
</html>
""",
        status_code=400,
    )
