from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MeasurementModel
from app.db.session import get_db

router = APIRouter(prefix="/sessions/{session_id}/measurements", tags=["measurements"])


@router.get("")
async def query_measurements(
    session_id: str,
    target_id: Optional[str] = None,
    after_sequence: Optional[int] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Query downsampled or raw measurement time-series for a session or specific target."""
    query = select(MeasurementModel).where(MeasurementModel.session_id == session_id)

    if target_id:
        query = query.where(MeasurementModel.target_id == target_id)
    if after_sequence is not None:
        query = query.where(MeasurementModel.sequence > after_sequence)

    query = query.order_by(MeasurementModel.sequence.asc()).limit(limit)
    result = await db.execute(query)
    measurements = result.scalars().all()

    return [
        {
            "sequence": m.sequence,
            "captured_at": m.captured_at.isoformat(),
            "target_id": m.target_id,
            "signal_value": m.signal_value,
            "unit": m.unit,
            "noise_floor": m.noise_floor,
            "snr": m.snr,
            "channel": m.channel,
            "band": m.band,
            "frequency_hz": m.frequency_hz,
        }
        for m in measurements
    ]
