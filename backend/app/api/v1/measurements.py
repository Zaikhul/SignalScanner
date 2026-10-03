from datetime import timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_operator_auth
from app.db.models import MeasurementModel
from app.db.session import get_db

router = APIRouter(
    prefix="/sessions/{session_id}/measurements",
    tags=["measurements"],
    dependencies=[Depends(verify_operator_auth)],
)


@router.get("")
async def query_measurements(
    session_id: str,
    target_id: Optional[str] = None,
    after_sequence: Optional[int] = None,
    after_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Query downsampled or raw measurement time-series for a session or specific target."""
    query = select(MeasurementModel).where(MeasurementModel.session_id == session_id)

    if target_id:
        query = query.where(MeasurementModel.target_id == target_id)
    if after_sequence is not None:
        if after_id is not None:
            query = query.where(
                or_(
                    MeasurementModel.sequence > after_sequence,
                    (MeasurementModel.sequence == after_sequence) & (MeasurementModel.id > after_id),
                )
            )
        else:
            query = query.where(MeasurementModel.sequence > after_sequence)

    query = query.order_by(MeasurementModel.sequence.asc(), MeasurementModel.id.asc()).limit(limit)
    result = await db.execute(query)
    measurements = result.scalars().all()

    res = []
    for m in measurements:
        dt = m.captured_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        iso_str = dt_utc.isoformat().replace("+00:00", "Z")

        res.append({
            "id": m.id,
            "sequence": m.sequence,
            "captured_at": iso_str,
            "target_id": m.target_id,
            "signal_value": m.signal_value,
            "unit": m.unit,
            "noise_floor": m.noise_floor,
            "snr": m.snr,
            "channel": m.channel,
            "band": m.band,
            "frequency_hz": m.frequency_hz,
        })
    return res
