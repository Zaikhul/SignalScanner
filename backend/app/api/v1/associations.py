from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.association import (
    AssociationResponse,
    ConnectAssociationRequest,
    CreateAssociationDraftRequest,
    DisconnectAssociationRequest,
    IngestAssociationStatusRequest,
    IngestHostBatchRequest,
    LanHostListResponse,
)
from app.services.association_service import association_service

router = APIRouter(tags=["associations"])


@router.post(
    "/sessions/{session_id}/associations",
    response_model=AssociationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_association_draft(
    session_id: str,
    payload: CreateAssociationDraftRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a draft association for an AP target within a scan session."""
    return await association_service.create_draft(db, session_id, payload)


@router.post("/associations/{association_id}/connect", response_model=AssociationResponse)
async def connect_association(
    association_id: str,
    payload: ConnectAssociationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate association to target WiFi AP after authorization gate confirmation.
    Zero-Secret guarantee: Body must NEVER contain passwords.
    """
    return await association_service.connect(db, association_id, payload)


@router.post("/associations/{association_id}/disconnect", response_model=AssociationResponse)
async def disconnect_association(
    association_id: str,
    payload: DisconnectAssociationRequest = DisconnectAssociationRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect active WiFi association and forget temporary profile by default."""
    return await association_service.disconnect(
        db, association_id, forget_profile=payload.forget_profile
    )


@router.post("/associations/{association_id}/inventory/refresh")
async def refresh_inventory(
    association_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new LAN neighbor discovery cycle on the attached prefix."""
    return await association_service.trigger_refresh(db, association_id)


@router.get("/associations/{association_id}", response_model=AssociationResponse)
async def get_association(
    association_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve association state, own IP, gateway, DNS, and captive status."""
    return await association_service.get_by_id(db, association_id)


@router.get("/associations/{association_id}/hosts", response_model=LanHostListResponse)
async def list_association_hosts(
    association_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=256),
    db: AsyncSession = Depends(get_db),
):
    """List discovered hosts on the attached local network with pagination."""
    items, total = await association_service.list_hosts(
        db, association_id, page=page, page_size=page_size
    )
    return LanHostListResponse(association_id=association_id, items=items, total=total)


@router.post("/associations/{association_id}/exports")
async def export_inventory(
    association_id: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export LAN inventory as JSON or CSV with SHA256 checksum and no secret leakage."""
    return await association_service.export_inventory(db, association_id, format=format)


@router.post("/associations/{association_id}/ingest/status", response_model=AssociationResponse)
async def ingest_association_status(
    association_id: str,
    payload: IngestAssociationStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """Collector internal callback: update association status & network addressing."""
    return await association_service.update_status_from_collector(db, association_id, payload)


@router.post("/associations/{association_id}/ingest/hosts")
async def ingest_association_hosts(
    association_id: str,
    payload: IngestHostBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Collector internal callback: ingest discovered host batch with bound verification."""
    count = await association_service.ingest_hosts(
        db, association_id, payload.session_id, payload.hosts
    )
    return {"status": "ok", "ingested_hosts": count}
