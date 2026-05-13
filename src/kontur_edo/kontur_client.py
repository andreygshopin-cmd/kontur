from typing import Any

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


class KonturAuthError(RuntimeError):
    pass


class KonturApiError(RuntimeError):
    def __init__(self, stage: str, status_code: int, response_text: str) -> None:
        self.stage = stage
        self.status_code = status_code
        self.response_text = response_text[:500]
        super().__init__(f"{stage} failed with HTTP {status_code}: {self.response_text}")


def get_organizations(settings: Settings) -> KonturOrganizationsResponse:
    base_url, auth_header, token = _authenticate(settings)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        organizations_response = client.get(
            "/GetMyOrganizations",
            headers=_authorized_headers(auth_header, token),
        )
        _raise_for_status(organizations_response, "GetMyOrganizations")

    payload = organizations_response.json()
    return KonturOrganizationsResponse(
        organizations=[
            _normalize_organization(organization)
            for organization in payload.get("Organizations", payload.get("organizations", []))
        ]
    )


def get_current_user(settings: Settings) -> KonturUserResponse:
    base_url, auth_header, token = _authenticate(settings)

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        user_response = client.get(
            "/V2/GetMyUser",
            headers=_authorized_headers(auth_header, token),
        )
        _raise_for_status(user_response, "GetMyUser")

    return _normalize_user(user_response.json())


def _authenticate(settings: Settings) -> tuple[str, str, str]:
    if not settings.api_key or not settings.login or not settings.password:
        raise KonturAuthError(
            "KONTUR_API_KEY, KONTUR_LOGIN and KONTUR_PASSWORD must be configured."
        )

    base_url = str(settings.base_url).rstrip("/")
    auth_header = f"DiadocAuth ddauth_api_client_id={settings.api_key}"

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        auth_response = client.post(
            "/V3/Authenticate",
            params={"type": "password"},
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={"login": settings.login, "password": settings.password},
        )
        _raise_for_status(auth_response, "Authenticate")
        token = auth_response.text.strip()

    return base_url, auth_header, token


def _raise_for_status(response: httpx.Response, stage: str) -> None:
    if response.is_success:
        return

    raise KonturApiError(stage, response.status_code, response.text.strip())


def _authorized_headers(auth_header: str, token: str) -> dict[str, str]:
    return {
        "Authorization": f"{auth_header},ddauth_token={token}",
        "Accept": "application/json",
    }


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
