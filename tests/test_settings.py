from kontur_edo import Settings


def test_default_base_url() -> None:
    settings = Settings()

    assert str(settings.base_url) == "https://diadoc-api.kontur.ru/"

