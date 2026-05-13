# Kontur

Python-проект для интеграции с Контур ЭДО.

## Быстрый старт

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest
```

## Локальный запуск

```powershell
.\.venv\Scripts\uvicorn.exe kontur_edo.app:app --reload
```

После запуска:

- `/` — страница с кнопкой проверки организаций;
- `GET /health` — проверка, что сервис жив;
- `GET /api/config` — проверка, какие переменные окружения настроены без вывода секретов;
- `GET /api/kontur/organizations` — авторизация в Контуре и получение организаций;
- `/docs` — Swagger UI.

## Render

Для Web Service на Render используйте:

- Repository: `andreygshopin-cmd/kontur`
- Branch: `main`
- Runtime: `Python 3`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn kontur_edo.app:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

Environment Variables:

- `KONTUR_BASE_URL`
- `KONTUR_APP_NAME`
- `KONTUR_API_KEY`
- `KONTUR_CLIENT_ID`
- `KONTUR_CLIENT_SECRET`
- `KONTUR_LOGIN`
- `KONTUR_PASSWORD`

## Конфигурация

Скопируйте `.env.example` в `.env` и заполните значения для доступа к API.
