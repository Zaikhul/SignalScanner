from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.channel_health import (
    ChannelHealthSnapshotResponse,
    ChannelRecommendationResponse,
    ChannelValidationRequest,
    ChannelValidationResponse,
    EvaluateRecommendationRequest,
)
from app.core.security import verify_operator_auth
from app.services.channel_health_service import channel_health_service

router = APIRouter(tags=["channel-health"], dependencies=[Depends(verify_operator_auth)])


@router.get(
    "/sessions/{session_id}/channel-health",
    response_model=ChannelHealthSnapshotResponse,
    summary="Get Channel Health matrix and component evidence",
)
async def get_session_channel_health(
    session_id: str,
    band: str = Query("2.4GHz", description="Frequency band to evaluate: 2.4GHz, 5GHz, or 6GHz"),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await channel_health_service.get_latest_channel_health_snapshot(
        db=db, session_id=session_id, band=band
    )
    if not snapshot:
        # If no snapshot exists yet, generate initial evaluation snapshot
        try:
            req = EvaluateRecommendationRequest(band=band)
            rec = await channel_health_service.evaluate_channel_health_and_recommend(
                db=db, session_id=session_id, req=req
            )
            snapshot = await channel_health_service.get_latest_channel_health_snapshot(
                db=db, session_id=session_id, band=band
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No channel health snapshot found for session {session_id}",
        )
    return snapshot


@router.post(
    "/sessions/{session_id}/channel-recommendations/evaluate",
    response_model=ChannelRecommendationResponse,
    summary="Evaluate and generate read-only channel recommendation",
)
async def evaluate_channel_recommendation(
    session_id: str,
    payload: Optional[EvaluateRecommendationRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        rec = await channel_health_service.evaluate_channel_health_and_recommend(
            db=db, session_id=session_id, req=payload
        )
        return rec
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/sessions/{session_id}/channel-recommendations/latest",
    response_model=ChannelRecommendationResponse,
    summary="Get latest channel recommendation for session",
)
async def get_latest_channel_recommendation(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    rec = await channel_health_service.get_latest_recommendation(
        db=db, session_id=session_id
    )
    if not rec:
        # Trigger evaluation if none exists
        try:
            rec = await channel_health_service.evaluate_channel_health_and_recommend(
                db=db, session_id=session_id
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No recommendations found for session {session_id}",
        )
    return rec


@router.get(
    "/channel-recommendations/{recommendation_id}",
    response_model=ChannelRecommendationResponse,
    summary="Get immutable decision record by ID",
)
async def get_channel_recommendation_by_id(
    recommendation_id: str,
    db: AsyncSession = Depends(get_db),
):
    rec = await channel_health_service.get_recommendation_by_id(
        db=db, recommendation_id=recommendation_id
    )
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel recommendation {recommendation_id} not found",
        )
    return rec


@router.post(
    "/sessions/{session_id}/channel-validations",
    response_model=ChannelValidationResponse,
    summary="Run before-after channel change comparison",
)
async def run_channel_validation(
    session_id: str,
    payload: ChannelValidationRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        val = await channel_health_service.create_channel_validation_run(
            db=db, session_id=session_id, req=payload
        )
        return val
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/sessions/{session_id}/channel-validations",
    response_model=List[ChannelValidationResponse],
    summary="List all validation runs for session",
)
async def list_channel_validations(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await channel_health_service.list_channel_validation_runs(
        db=db, session_id=session_id
    )
