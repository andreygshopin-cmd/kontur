from __future__ import annotations

import os
import sys
from time import perf_counter, sleep
from typing import Any, cast

import httpx
from dotenv import load_dotenv

RENDER_API_BASE_URL = "https://api.render.com/v1"
SUCCESS_DEPLOY_STATUSES = {"live"}
FAILED_DEPLOY_STATUSES = {
    "build_failed",
    "canceled",
    "deactivated",
    "pre_deploy_failed",
    "update_failed",
}


class RenderDeployError(RuntimeError):
    pass


def main() -> int:
    load_dotenv()

    api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    if api_key and service_id:
        try:
            deploy_id = _trigger_render_api(api_key, service_id)
            print(f"Render deploy triggered via API: {deploy_id}")
            if _should_wait_for_deploy():
                status = _wait_for_render_deploy(api_key, service_id, deploy_id)
                print(f"Render deploy finished: {deploy_id} ({status})")
        except (httpx.HTTPError, RenderDeployError, TimeoutError) as error:
            print(f"Render deploy failed: {error}", file=sys.stderr)
            return 1
        return 0

    deploy_hook_url = os.getenv("RENDER_DEPLOY_HOOK_URL")
    if deploy_hook_url:
        try:
            deploy_id = _trigger_deploy_hook(deploy_hook_url)
        except httpx.HTTPError as error:
            print(f"Render deploy hook failed: {error}", file=sys.stderr)
            return 1

        print(f"Render deploy triggered via deploy hook: {deploy_id}")
        if _should_wait_for_deploy():
            print(
                "Render deploy waiting skipped: set RENDER_API_KEY and RENDER_SERVICE_ID.",
                file=sys.stderr,
            )
        return 0

    print(
        "Set RENDER_DEPLOY_HOOK_URL or both RENDER_API_KEY and RENDER_SERVICE_ID.",
        file=sys.stderr,
    )
    return 2


def _trigger_deploy_hook(deploy_hook_url: str) -> str:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(deploy_hook_url)
        response.raise_for_status()
        payload = _json_or_empty(response)

    return str(payload.get("deployId") or payload.get("id") or "accepted")


def _trigger_render_api(api_key: str, service_id: str) -> str:
    with httpx.Client(base_url=RENDER_API_BASE_URL, timeout=30.0) as client:
        response = client.post(
            f"/services/{service_id}/deploys",
            headers=_render_headers(api_key),
            json={"clearCache": "do_not_clear"},
        )
        response.raise_for_status()
        payload = _json_or_empty(response)

    deploy = payload.get("deploy")
    deploy_id = cast(dict[str, Any], deploy).get("id") if isinstance(deploy, dict) else None
    return str(payload.get("id") or deploy_id or "accepted")


def _wait_for_render_deploy(
    api_key: str,
    service_id: str,
    deploy_id: str,
    *,
    timeout_seconds: float | None = None,
    poll_seconds: float | None = None,
) -> str:
    timeout_seconds = timeout_seconds or _float_env("RENDER_DEPLOY_TIMEOUT_SECONDS", 900.0)
    poll_seconds = poll_seconds or _float_env("RENDER_DEPLOY_POLL_SECONDS", 10.0)
    deadline = perf_counter() + timeout_seconds
    last_status: str | None = None

    with httpx.Client(base_url=RENDER_API_BASE_URL, timeout=30.0) as client:
        while True:
            payload = _retrieve_render_deploy(client, api_key, service_id, deploy_id)
            status = _deploy_status(payload)
            if status != last_status:
                print(f"Render deploy status: {deploy_id} ({status})")
                last_status = status

            if status in SUCCESS_DEPLOY_STATUSES:
                return status
            if status in FAILED_DEPLOY_STATUSES:
                raise RenderDeployError(f"{deploy_id} finished with status {status}.")
            if perf_counter() >= deadline:
                raise TimeoutError(f"{deploy_id} did not finish within {timeout_seconds:g}s.")

            sleep(max(poll_seconds, 1.0))


def _retrieve_render_deploy(
    client: httpx.Client,
    api_key: str,
    service_id: str,
    deploy_id: str,
) -> dict[str, object]:
    response = client.get(
        f"/services/{service_id}/deploys/{deploy_id}",
        headers=_render_headers(api_key),
    )
    response.raise_for_status()
    return _json_or_empty(response)


def _deploy_status(payload: dict[str, object]) -> str:
    deploy = payload.get("deploy")
    if isinstance(deploy, dict):
        status = deploy.get("status")
        if isinstance(status, str) and status:
            return status

    status = payload.get("status")
    if isinstance(status, str) and status:
        return status

    return "unknown"


def _render_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _should_wait_for_deploy() -> bool:
    value = os.getenv("RENDER_DEPLOY_WAIT", "true").strip().casefold()
    return value not in {"0", "false", "no", "off"}


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _json_or_empty(response: httpx.Response) -> dict[str, object]:
    if not response.content:
        return {}
    try:
        value = response.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
