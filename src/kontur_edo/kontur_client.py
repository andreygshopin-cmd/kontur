from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from kontur_edo.settings import Settings


class KonturBox(BaseModel):
    box_id: str
    title: str | None = None


class KonturOrganization(BaseModel):
    org_id: str | None = None
    name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    boxes: list[KonturBox]


class KonturOrganizationsResponse(BaseModel):
    organizations: list[KonturOrganization]


class KonturUserResponse(BaseModel):
    user_id: str | None = None
    login: str | None = None
    email: str | None = None
    last_name: str | None = None
    first_name: str | None = None
    middle_name: str | None = None


class KonturTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None


class KonturAuthError(RuntimeError):
    pass


class KonturApiError(RuntimeError):
    def __init__(self, stage: str, status_code: int, response_text: str) -> None:
        self.stage = stage
        self.status_code = status_code
        self.response_text = response_text[:500]
        super().__init__(f"{stage} failed with HTTP {status_code}: {self.response_text}")


def build_authorization_url(
    settings: Settings,
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
) -> str:
    client_id = _client_id(settings)
    if not client_id:
        raise KonturAuthError("KONTUR_CLIENT_ID must be configured.")

    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "scope": settings.scope,
            "redirect_uri": redirect_uri,
            "nonce": nonce,
            "state": state,
        }
    )
    return f"{str(settings.auth_base_url).rstrip('/')}/connect/authorize?{query}"


def exchange_authorization_code(
    settings: Settings,
    *,
    code: str,
    redirect_uri: str,
) -> KonturTokenResponse:
    client_id = _client_id(settings)
    client_secret = _client_secret(settings)
    if not client_id or not client_secret:
        raise KonturAuthError("KONTUR_CLIENT_ID and KONTUR_CLIENT_SECRET must be configured.")

    with httpx.Client(base_url=str(settings.auth_base_url).rstrip("/"), timeout=30.0) as client:
        response = client.post(
            "/connect/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        )
        _raise_for_status(response, "Token")

    return KonturTokenResponse.model_validate(response.json())


def get_organizations(settings: Settings, access_token: str) -> KonturOrganizationsResponse:
    with httpx.Client(base_url=str(settings.base_url).rstrip("/"), timeout=30.0) as client:
        organizations_response = client.get(
            "/GetMyOrganizations",
            headers=_bearer_headers(access_token),
        )
        _raise_for_status(organizations_response, "GetMyOrganizations")

    payload = organizations_response.json()
    return KonturOrganizationsResponse(
        organizations=[
            _normalize_organization(organization)
            for organization in payload.get("Organizations", payload.get("organizations", []))
        ]
    )


def get_current_user(settings: Settings, access_token: str) -> KonturUserResponse:
    with httpx.Client(base_url=str(settings.base_url).rstrip("/"), timeout=30.0) as client:
        user_response = client.get(
            "/V2/GetMyUser",
            headers=_bearer_headers(access_token),
        )
        _raise_for_status(user_response, "GetMyUser")

    return _normalize_user(user_response.json())


def _raise_for_status(response: httpx.Response, stage: str) -> None:
    if response.is_success:
        return

    raise KonturApiError(stage, response.status_code, response.text.strip())


def _bearer_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def _client_id(settings: Settings) -> str | None:
    return settings.client_id or settings.app_name


def _client_secret(settings: Settings) -> str | None:
    return settings.client_secret or settings.api_key


def _normalize_organization(organization: dict[str, Any]) -> KonturOrganization:
    boxes = organization.get("Boxes", organization.get("boxes", []))

    return KonturOrganization(
        org_id=organization.get("OrgId") or organization.get("orgId"),
        name=organization.get("FullName")
        or organization.get("ShortName")
        or organization.get("Name")
        or organization.get("name"),
        inn=organization.get("Inn") or organization.get("inn"),
        kpp=organization.get("Kpp") or organization.get("kpp"),
        boxes=[
            KonturBox(
                box_id=box.get("BoxId") or box.get("boxId") or "",
                title=box.get("Title") or box.get("title"),
            )
            for box in boxes
            if box.get("BoxId") or box.get("boxId")
        ],
    )


def _normalize_user(user: dict[str, Any]) -> KonturUserResponse:
    return KonturUserResponse(
        user_id=user.get("Id") or user.get("UserId") or user.get("id") or user.get("userId"),
        login=user.get("Login") or user.get("login"),
        email=user.get("Email") or user.get("email"),
        last_name=user.get("LastName") or user.get("lastName"),
        first_name=user.get("FirstName") or user.get("firstName"),
        middle_name=user.get("MiddleName") or user.get("middleName"),
    )
