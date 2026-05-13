from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KONTUR_")

    base_url: HttpUrl = Field(default=HttpUrl("https://diadoc-api.kontur.ru"))
    api_key: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
