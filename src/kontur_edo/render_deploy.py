from __future__ import annotations

import os
import sys
from typing import Any, cast

import httpx
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()

    deploy_hook_url = os.getenv("RENDER_DEPLOY_HOOK_URL")
    if deploy_hook_url:
        deploy_id = _trigger_deploy_hook(deploy_hook_url)
        print(f"Render deploy triggered via deploy hook: {deploy_id}")
        return 0

    api_key = os.getenv("RENDER_API_KEY")
    service_id = os.getenv("RENDER_SERVICE_ID")
    if api_key and service_id:
        deploy_id = _trigger_render_api(api_key, service_id)
        print(f"Render deploy triggered via API: {deploy_id}")
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
    with httpx.Client(base_url="https://api.render.com/v1", timeout=30.0) as client:
        response = client.post(
            f"/services/{service_id}/deploys",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            json={"clearCache": "do_not_clear"},
        )
        response.raise_for_status()
        payload = _json_or_empty(response)

    deploy = payload.get("deploy")
    deploy_id = cast(dict[str, Any], deploy).get("id") if isinstance(deploy, dict) else None
    return str(payload.get("id") or deploy_id or "accepted")


def _json_or_empty(response: httpx.Response) -> dict[str, object]:
    if not response.content:
        return {}
    value = response.json()
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
