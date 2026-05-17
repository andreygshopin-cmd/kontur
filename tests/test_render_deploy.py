import httpx

import kontur_edo.render_deploy as render_deploy
from kontur_edo.render_deploy import _deploy_status, _json_or_empty


def test_json_or_empty_accepts_text_response() -> None:
    response = httpx.Response(202, content=b"accepted")

    assert _json_or_empty(response) == {}


def test_deploy_status_reads_nested_deploy_status() -> None:
    assert _deploy_status({"deploy": {"status": "live"}}) == "live"


def test_deploy_status_reads_flat_status() -> None:
    assert _deploy_status({"status": "build_in_progress"}) == "build_in_progress"


def test_main_triggers_render_api_and_waits(monkeypatch) -> None:
    calls = []

    def fake_trigger(api_key, service_id):
        calls.append(("trigger", api_key, service_id))
        return "deploy-id"

    def fake_wait(api_key, service_id, deploy_id):
        calls.append(("wait", api_key, service_id, deploy_id))
        return "live"

    monkeypatch.setenv("RENDER_API_KEY", "api-key")
    monkeypatch.setenv("RENDER_SERVICE_ID", "service-id")
    monkeypatch.setattr(render_deploy, "_trigger_render_api", fake_trigger)
    monkeypatch.setattr(render_deploy, "_wait_for_render_deploy", fake_wait)

    assert render_deploy.main() == 0
    assert calls == [
        ("trigger", "api-key", "service-id"),
        ("wait", "api-key", "service-id", "deploy-id"),
    ]


def test_main_can_skip_wait(monkeypatch) -> None:
    calls = []

    def fake_trigger(api_key, service_id):
        calls.append(("trigger", api_key, service_id))
        return "deploy-id"

    def fail_wait(*_args, **_kwargs):
        raise AssertionError("wait should be skipped")

    monkeypatch.setenv("RENDER_API_KEY", "api-key")
    monkeypatch.setenv("RENDER_SERVICE_ID", "service-id")
    monkeypatch.setenv("RENDER_DEPLOY_WAIT", "false")
    monkeypatch.setattr(render_deploy, "_trigger_render_api", fake_trigger)
    monkeypatch.setattr(render_deploy, "_wait_for_render_deploy", fail_wait)

    assert render_deploy.main() == 0
    assert calls == [("trigger", "api-key", "service-id")]
