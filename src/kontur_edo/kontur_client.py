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


class KonturAuthError(RuntimeError):
    pass


def get_organizations(settings: Settings) -> KonturOrganizationsResponse:
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
        auth_response.raise_for_status()
        token = auth_response.text.strip()

        organizations_response = client.get(
            "/GetMyOrganizations",
            headers={
                "Authorization": f"{auth_header},ddauth_token={token}",
                "Accept": "application/json",
            },
        )
        organizations_response.raise_for_status()

    payload = organizations_response.json()
    return KonturOrganizationsResponse(
        organizations=[
            _normalize_organization(organization)
            for organization in payload.get("Organizations", payload.get("organizations", []))
        ]
    )


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
