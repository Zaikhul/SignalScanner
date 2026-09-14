from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TargetModel
from app.db.session import get_db
from app.schemas.measurement import TargetSummary
from app.services.session_manager import session_manager

router = APIRouter(prefix="/sessions/{session_id}/targets", tags=["targets"])


@router.get("", response_model=List[TargetSummary])
async def list_session_targets(
    session_id: str, db: AsyncSession = Depends(get_db)
):
    """Retrieve all discovered target beacons/networks for a session."""
    return await session_manager.list_targets(db, session_id)


@router.post("/{target_id}/pin")
async def toggle_pin_target(
    session_id: str, target_id: str, db: AsyncSession = Depends(get_db)
):
    """Toggle pinned status for a target."""
    result = await db.execute(
        select(TargetModel).where(
            TargetModel.session_id == session_id,
            TargetModel.target_id == target_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Target not found"
        )
    target.is_pinned = not target.is_pinned
    await db.commit()
    return {"target_id": target_id, "is_pinned": target.is_pinned}
