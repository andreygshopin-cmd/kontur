import httpx

from kontur_edo.render_deploy import _json_or_empty


def test_json_or_empty_accepts_text_response() -> None:
    response = httpx.Response(202, content=b"accepted")

    assert _json_or_empty(response) == {}
