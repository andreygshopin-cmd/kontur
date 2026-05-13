from functools import lru_cache

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from kontur_edo.kontur_client import (
    KonturApiError,
    KonturAuthError,
    KonturOrganizationsResponse,
    KonturUserResponse,
    get_current_user,
    get_organizations,
)
from kontur_edo.settings import Settings


class HealthResponse(BaseModel):
    status: str


class ConfigResponse(BaseModel):
    kontur_base_url: str
    app_name: str | None
    api_key_configured: bool
    client_id_configured: bool
    client_secret_configured: bool
    login_configured: bool
    password_configured: bool


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
    main { max-width: 920px; margin: 0 auto; padding: 40px 20px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    h1 { margin: 0; font-size: 28px; line-height: 1.2; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }
    button {
      border: 0; border-radius: 6px; background: #0f766e; color: white;
      padding: 12px 18px; font-size: 16px; cursor: pointer;
    }
    button.secondary { background: #2563eb; }
    button:disabled { opacity: .65; cursor: progress; }
    .panel { margin-top: 28px; background: white; border: 1px solid #d9dee7; border-radius: 8px; }
    .status { padding: 16px 18px; border-bottom: 1px solid #e5e9f0; font-weight: 700; }
    .content { padding: 18px; }
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
    @media (max-width: 680px) {
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
        <button id="load-organizations">Получить организации</button>
        <button id="load-user" class="secondary">Получить личные данные</button>
      </div>
    </header>
    <section class="panel">
      <div id="status" class="status muted">Готово</div>
      <div id="content" class="content muted">Нажмите кнопку, чтобы проверить доступ.</div>
    </section>
  </main>
  <script>
    const organizationsButton = document.getElementById("load-organizations");
    const userButton = document.getElementById("load-user");
    const buttons = [organizationsButton, userButton];
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

    async function loadData(url, onSuccess, successTitle) {
      setLoading(true);
      statusNode.textContent = "Запрос в Контур...";
      statusNode.className = "status muted";
      contentNode.textContent = "";

      try {
        const response = await fetch(url);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Ошибка запроса");
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
  </script>
</body>
</html>
"""


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/config", response_model=ConfigResponse)
def config() -> ConfigResponse:
    settings = get_settings()

    return ConfigResponse(
        kontur_base_url=str(settings.base_url),
        app_name=settings.app_name,
        api_key_configured=bool(settings.api_key),
        client_id_configured=bool(settings.client_id),
        client_secret_configured=bool(settings.client_secret),
        login_configured=bool(settings.login),
        password_configured=bool(settings.password),
    )


@app.get("/api/kontur/organizations", response_model=KonturOrganizationsResponse)
def kontur_organizations() -> KonturOrganizationsResponse:
    try:
        return get_organizations(get_settings())
    except KonturAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except KonturApiError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "stage": error.stage,
                "kontur_status_code": error.status_code,
                "message": error.response_text,
            },
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Kontur API is unavailable.") from error


@app.get("/api/kontur/user", response_model=KonturUserResponse)
def kontur_user() -> KonturUserResponse:
    try:
        return get_current_user(get_settings())
    except KonturAuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except KonturApiError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "stage": error.stage,
                "kontur_status_code": error.status_code,
                "message": error.response_text,
            },
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Kontur API is unavailable.") from error
