from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.web_scan.authorization import (
    OperatorPrincipal,
    get_current_principal,
    require_permission,
)
from app.db.session import get_db
from app.schemas.web_scan import CreateScopeGrant, Page, ScopeGrant
from app.services.web_scan_service import WebScanService

router = APIRouter(
    prefix="/web-scan-scopes",
    tags=["web-scan-scopes"],
    dependencies=[Depends(get_current_principal)],
)


def _check_enabled():
    if not getattr(settings, "WEB_SCANNER_ENABLED", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Web Scanner feature is disabled",
        )


@router.post(
    "",
    response_model=ScopeGrant,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new authorized Scope Grant / Rule of Engagement",
)
async def create_scope_grant(
    req: CreateScopeGrant,
    principal: OperatorPrincipal = Depends(require_permission("web_scan:admin")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    try:
        grant = await WebScanService.create_scope_grant(
            db=db,
            tenant_id=principal.tenant_id,
            principal_id=principal.principal_id,
            req=req,
        )
        return grant
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "",
    response_model=Page,
    summary="List active and historical Scope Grants",
)
async def list_scope_grants(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    items, total = await WebScanService.list_scope_grants(
        db=db,
        tenant_id=principal.tenant_id,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, total=total)


@router.get(
    "/{scope_id}",
    response_model=ScopeGrant,
    summary="Retrieve details of a Scope Grant",
)
async def get_scope_grant(
    scope_id: str,
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    grant = await WebScanService.get_scope_grant(
        db=db,
        tenant_id=principal.tenant_id,
        scope_id=scope_id,
    )
    if not grant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope grant {scope_id} not found",
        )
    return grant


@router.post(
    "/{scope_id}/revoke",
    response_model=ScopeGrant,
    summary="Revoke an existing Scope Grant",
)
async def revoke_scope_grant(
    scope_id: str,
    principal: OperatorPrincipal = Depends(require_permission("web_scan:admin")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    grant = await WebScanService.revoke_scope_grant(
        db=db,
        tenant_id=principal.tenant_id,
        principal_id=principal.principal_id,
        scope_id=scope_id,
    )
    if not grant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope grant {scope_id} not found",
        )
    return grant
