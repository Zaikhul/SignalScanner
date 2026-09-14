from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.export import ExportRequest, ExportResponse
from app.services.export_service import export_service

router = APIRouter(tags=["exports"])


@router.post("/sessions/{session_id}/exports", response_model=ExportResponse)
async def create_session_export(
    session_id: str,
    payload: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a downloadable CSV or JSON export for a scan session."""
    try:
        return await export_service.generate_export(db, session_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str, db: AsyncSession = Depends(get_db)):
    """Download generated export file directly."""
    result = await export_service.get_export_file(db, export_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export not found"
        )
    content, mime, filename = result
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
