from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KONTUR_", extra="ignore")

    base_url: HttpUrl = Field(default=HttpUrl("https://diadoc-api.kontur.ru"))
    auth_base_url: HttpUrl = Field(default=HttpUrl("https://identity.testkontur.ru"))
    scope: str = "openid profile email offline_access Diadoc.PublicAPI.Staging"
    redirect_uri: str | None = None
    app_name: str | None = "KOT_test"
    api_key: str | None = None
    client_id: str | None = "KOT_test"
    client_secret: str | None = None
    login: str | None = None
    password: str | None = None
    kedo_base_url: HttpUrl = Field(default=HttpUrl("https://api.testkontur.ru/kedo"))
    kedo_api_key: str | None = None
    kedo_org_id: str | None = None
    kedo_employee_id: str | None = None
    kedo_document_type_id: str | None = None
    kedo_document_type_name: str | None = None
    kedo_signature_types: str = "Pep,Nep"
    kedo_login: str | None = None
    kedo_password: str | None = None
    kedo_test_filename: str | None = None
    kedo_test_text: str | None = None
