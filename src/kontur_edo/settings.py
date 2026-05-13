from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KONTUR_")

    base_url: HttpUrl = Field(default=HttpUrl("https://diadoc-api.kontur.ru"))
    auth_base_url: HttpUrl = Field(default=HttpUrl("https://identity.testkontur.ru"))
    scope: str = "openid profile email offline_access Diadoc.PublicAPI.Staging"
    redirect_uri: str | None = None
    app_name: str | None = None
    api_key: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    login: str | None = None
    password: str | None = None
