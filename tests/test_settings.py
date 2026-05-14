from pydantic_settings import SettingsConfigDict

from kontur_edo import Settings


def test_default_base_url() -> None:
    class TestSettings(Settings):
        model_config = SettingsConfigDict(env_file=None, env_prefix="TEST_KONTUR_")

    settings = TestSettings()

    assert str(settings.base_url) == "https://diadoc-api.kontur.ru/"
    assert str(settings.kedo_base_url) == "https://api.testkontur.ru/kedo"
