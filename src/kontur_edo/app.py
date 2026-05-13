from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel

from kontur_edo.settings import Settings


class HealthResponse(BaseModel):
    status: str


class ConfigResponse(BaseModel):
    kontur_base_url: str
    api_key_configured: bool
    client_id_configured: bool
    client_secret_configured: bool


@lru_cache
def get_settings() -> Settings:
    return Settings()


app = FastAPI(
    title="Kontur EDO Gateway",
    description="Gateway service for Kontur EDO API integration.",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/config", response_model=ConfigResponse)
def config() -> ConfigResponse:
    settings = get_settings()

    return ConfigResponse(
        kontur_base_url=str(settings.base_url),
        api_key_configured=bool(settings.api_key),
        client_id_configured=bool(settings.client_id),
        client_secret_configured=bool(settings.client_secret),
    )

