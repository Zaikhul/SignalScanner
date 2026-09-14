from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.common import PaginatedResponse, ScanMode, SessionStatus
from app.schemas.session import (
    CreateSessionRequest,
    SessionMarkerCreate,
    SessionMarkerResponse,
    SessionResponse,
)
from app.services.session_manager import session_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest, db: AsyncSession = Depends(get_db)
):
    """Create a new scan session configuration."""
    return await session_manager.create_session(db, payload)


@router.get("", response_model=PaginatedResponse[SessionResponse])
async def list_sessions(
    mode: Optional[ScanMode] = None,
    status: Optional[SessionStatus] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search and paginate past and active scan sessions."""
    sessions, total = await session_manager.list_sessions(
        db, mode=mode, status=status, page=page, page_size=page_size
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        items=sessions,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve session metadata, aggregated metrics, and event markers."""
    try:
        return await session_manager.get_session_response(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{session_id}/start", response_model=SessionResponse)
async def start_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Start scanning for a draft or paused session."""
    try:
        return await session_manager.start_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{session_id}/pause", response_model=SessionResponse)
async def pause_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Pause an active scan session."""
    try:
        return await session_manager.pause_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{session_id}/resume", response_model=SessionResponse)
async def resume_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Resume a paused scan session."""
    try:
        return await session_manager.resume_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{session_id}/stop", response_model=SessionResponse)
async def stop_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Stop active scanning and finalize session metrics."""
    try:
        return await session_manager.stop_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{session_id}/markers", response_model=SessionMarkerResponse)
async def add_session_marker(
    session_id: str,
    payload: SessionMarkerCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a timestamped event marker to the session timeline."""
    try:
        return await session_manager.add_marker(db, session_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
