import logging
import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.measurement import MeasurementBatch
from app.services.session_manager import session_manager

logger = logging.getLogger("app.ingest")
router = APIRouter(prefix="/collector-ingest", tags=["ingest"])


@router.post("/batches")
async def ingest_measurement_batch(
    batch: MeasurementBatch, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Ingests normalized measurement batches from local or remote collectors.
    Applies smoothing, persists data, and fans out to real-time WebSockets.
    Validates source_type and collector_id binding.
    """
    try:
        return await session_manager.ingest_batch(db, batch)
    except ValueError as ve:
        await db.rollback()
        err_msg = str(ve)
        if "not found" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=err_msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )
    except Exception as e:
        await db.rollback()
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        logger.exception(
            "measurement_ingest_failed",
            extra={"request_id": request_id, "session_id": batch.session_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INGEST_INTERNAL_ERROR",
                "request_id": request_id,
                "message": "An internal server error occurred while ingesting the measurement batch.",
            },
        )
