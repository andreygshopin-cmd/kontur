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

- `/` — страница входа в Контур и кнопки проверки данных;
- `GET /health` — проверка, что сервис жив;
- `GET /api/config` — проверка, какие переменные окружения настроены без вывода секретов;
- `GET /auth/kontur/login` — вход через Контур ID / OIDC;
- `GET /auth/kontur/callback` — callback для Authorization Code Flow;
- `GET /api/kontur/organizations` — авторизация в Контуре и получение организаций;
- `GET /api/kontur/user` — авторизация в Контуре и получение данных пользователя;
- `POST /api/kedo/test-document` — отправка тестового файла в Контур.КЭДО на подписание;
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
- `KONTUR_AUTH_BASE_URL`
- `KONTUR_SCOPE`
- `KONTUR_REDIRECT_URI`
- `KONTUR_APP_NAME`
- `KONTUR_CLIENT_ID`
- `KONTUR_CLIENT_SECRET`
- `KONTUR_KEDO_BASE_URL`
- `KONTUR_KEDO_API_KEY`
- `KONTUR_KEDO_ORG_ID`
- `KONTUR_KEDO_EMPLOYEE_ID`
- `KONTUR_KEDO_DOCUMENT_TYPE_ID`
- `KONTUR_KEDO_SIGNATURE_TYPES`

Для тестового контура:

```text
KONTUR_BASE_URL=https://diadoc-api.kontur.ru
KONTUR_AUTH_BASE_URL=https://identity.testkontur.ru
KONTUR_SCOPE=openid profile email offline_access Diadoc.PublicAPI.Staging
KONTUR_CLIENT_ID=KOT_test
KONTUR_CLIENT_SECRET=<API key из Кабинета интегратора>
KONTUR_REDIRECT_URI=https://<render-service>/auth/kontur/callback
KONTUR_KEDO_BASE_URL=https://api.testkontur.ru/kedo
KONTUR_KEDO_API_KEY=<API key из Кабинета интегратора, если отличается от KONTUR_CLIENT_SECRET>
KONTUR_KEDO_SIGNATURE_TYPES=Pep,Nep
```

В Кабинете интегратора для приложения укажите такой же redirect URI.

Для тестовой отправки в КЭДО можно не заполнять `KONTUR_KEDO_ORG_ID`,
`KONTUR_KEDO_EMPLOYEE_ID` и `KONTUR_KEDO_DOCUMENT_TYPE_ID`: приложение попробует
выбрать первую доступную организацию, сотрудника текущего пользователя и первый
подходящий неформализованный тип документа. Для точного получателя задайте эти
значения явно.

## Render deploy из командной строки

Для прямого запуска деплоя задайте один из вариантов:

- `RENDER_DEPLOY_HOOK_URL`
- `RENDER_API_KEY` и `RENDER_SERVICE_ID`

После этого:

```powershell
.\.venv\Scripts\python.exe -m kontur_edo.render_deploy
```

## Конфигурация

Скопируйте `.env.example` в `.env` и заполните значения для доступа к API.
