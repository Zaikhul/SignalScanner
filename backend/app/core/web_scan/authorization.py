from __future__ import annotations

import hmac
from typing import List, Optional
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.config import settings


class OperatorPrincipal(BaseModel):
    principal_id: str
    tenant_id: str
    permissions: List[str]


async def get_current_principal(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> OperatorPrincipal:
    """Authenticates operator calling Web Scanner API using Bearer token or API Key."""
    auth_str = authorization if isinstance(authorization, str) else None
    api_key_str = x_api_key if isinstance(x_api_key, str) else None

    token = None
    if auth_str:
        parts = auth_str.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]
    elif api_key_str:
        token = api_key_str

    # In dev or production, compare with settings.API_AUTH_TOKEN
    if not token or not hmac.compare_digest(token, settings.API_AUTH_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED: Missing or invalid web scanner credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant_id = (
        x_tenant_id
        if isinstance(x_tenant_id, str) and x_tenant_id
        else settings.WEB_SCAN_DEFAULT_TENANT
    )
    # Default operator possesses standard web scanner permissions
    return OperatorPrincipal(
        principal_id="operator_principal",
        tenant_id=tenant_id,
        permissions=[
            "web_scan:read",
            "web_scan:execute",
            "web_scan:cancel",
            "web_scan:admin",
            "web_scan:export",
        ],
    )


def require_permission(permission: str):
    """Dependency factory checking required web scanner permission on principal."""
    async def _checker(principal: OperatorPrincipal = Depends(get_current_principal)) -> OperatorPrincipal:
        if permission not in principal.permissions and "web_scan:admin" not in principal.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"FORBIDDEN: Missing required permission '{permission}'",
            )
        return principal
    return _checker
