from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.web_scan.authorization import (
    OperatorPrincipal,
    get_current_principal,
    require_permission,
)
from app.core.web_scan.registry import CAPABILITIES_CATALOG
from app.db.session import get_db
from app.schemas.web_scan import (
    Capabilities,
    CreateScanRequest,
    Page,
    ScanFinding,
    ScanJob,
    ScanObservation,
    ScanSnapshot,
    WebScanEvent,
)
from app.services.web_scan_export_service import WebScanExportService
from app.services.web_scan_scheduler import web_scan_scheduler
from app.services.web_scan_service import WebScanService

router = APIRouter(
    prefix="/web-scans",
    tags=["web-scans"],
    dependencies=[Depends(get_current_principal)],
)


def _check_enabled():
    if not getattr(settings, "WEB_SCANNER_ENABLED", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Web Scanner feature is disabled",
        )


@router.get(
    "/capabilities",
    response_model=Capabilities,
    summary="Retrieve Web Scanner capability catalog, profiles, and hard caps",
)
async def get_capabilities(
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
):
    catalog = CAPABILITIES_CATALOG.model_copy(deep=True)
    catalog.readiness["enabled"] = getattr(settings, "WEB_SCANNER_ENABLED", False)
    return catalog


@router.post(
    "",
    response_model=ScanJob,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a new Web Scanner audit job",
)
async def create_web_scan(
    req: CreateScanRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    principal: OperatorPrincipal = Depends(require_permission("web_scan:execute")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    try:
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id=principal.tenant_id,
            principal_id=principal.principal_id,
            req=req,
            idempotency_key=idempotency_key,
        )
        # Notify background scheduler to claim pending job
        web_scan_scheduler.trigger()
        return job
    except HTTPException:
        raise
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get(
    "",
    response_model=Page,
    summary="List Web Scanner jobs with optional status filter",
)
async def list_web_scans(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    items, total = await WebScanService.list_scan_jobs(
        db=db,
        tenant_id=principal.tenant_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, total=total)


@router.get(
    "/{scan_id}",
    response_model=ScanJob,
    summary="Get Web Scanner job status and configuration",
)
async def get_web_scan(
    scan_id: str,
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    job = await WebScanService.get_scan_job(
        db=db,
        tenant_id=principal.tenant_id,
        scan_id=scan_id,
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan job {scan_id} not found",
        )
    return job


@router.post(
    "/{scan_id}/cancel",
    response_model=ScanJob,
    summary="Cancel a pending or running Web Scanner job",
)
async def cancel_web_scan(
    scan_id: str,
    principal: OperatorPrincipal = Depends(require_permission("web_scan:cancel")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    # 1. Verify existence, tenant ownership, and permission first
    job = await WebScanService.cancel_scan_job(
        db=db,
        tenant_id=principal.tenant_id,
        principal_id=principal.principal_id,
        scan_id=scan_id,
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan job {scan_id} not found",
        )

    # 2. Trigger cancellation in memory only after ownership verification succeeded
    web_scan_scheduler.request_cancel(scan_id)
    return job


@router.get(
    "/{scan_id}/snapshot",
    response_model=ScanSnapshot,
    summary="Get aggregated snapshot including summary metrics and execution state",
)
async def get_web_scan_snapshot(
    scan_id: str,
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    snapshot = await WebScanService.get_scan_snapshot(
        db=db,
        tenant_id=principal.tenant_id,
        scan_id=scan_id,
    )
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan snapshot {scan_id} not found",
        )
    return snapshot


@router.get(
    "/{scan_id}/findings",
    response_model=Page,
    summary="Get paginated list of security findings for a scan",
)
async def get_web_scan_findings(
    scan_id: str,
    severity: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    items, total = await WebScanService.list_scan_findings(
        db=db,
        tenant_id=principal.tenant_id,
        scan_id=scan_id,
        severity=severity,
        module=module,
        search=search,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, total=total)


@router.get(
    "/{scan_id}/observations",
    response_model=Page,
    summary="Get paginated list of observations recorded during scan",
)
async def get_web_scan_observations(
    scan_id: str,
    kind: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    items, total = await WebScanService.list_scan_observations(
        db=db,
        tenant_id=principal.tenant_id,
        scan_id=scan_id,
        kind=kind,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, total=total)


@router.get(
    "/{scan_id}/events",
    response_model=List[WebScanEvent],
    summary="Fetch sequential scan events for stream replay",
)
async def get_web_scan_events(
    scan_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    events = await WebScanService.list_scan_events(
        db=db,
        tenant_id=principal.tenant_id,
        scan_id=scan_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return events


@router.post(
    "/{scan_id}/stream-ticket",
    summary="Create a short-lived single-use WebSocket authorization ticket",
)
async def create_stream_ticket(
    scan_id: str,
    principal: OperatorPrincipal = Depends(require_permission("web_scan:read")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    ticket = await WebScanService.create_ws_ticket(
        db=db,
        tenant_id=principal.tenant_id,
        principal_id=principal.principal_id,
        scan_id=scan_id,
    )
    return {"ticket": ticket, "expires_in_seconds": 60}


@router.get(
    "/{scan_id}/export",
    summary="Export scan audit report in JSON, v2 compat JSON, TXT, or safe SQL",
)
async def export_web_scan(
    scan_id: str,
    format: str = Query("json", description="Format: json, v2_json, txt, sql"),
    principal: OperatorPrincipal = Depends(require_permission("web_scan:export")),
    db: AsyncSession = Depends(get_db),
):
    _check_enabled()
    try:
        content, ctype, fname, checksum = await WebScanExportService.export_scan(
            db=db,
            tenant_id=principal.tenant_id,
            principal_id=principal.principal_id,
            scan_id=scan_id,
            export_format=format,
        )
        return Response(
            content=content,
            media_type=ctype,
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "X-Checksum-SHA256": checksum,
            },
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
