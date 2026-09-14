import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExportJobModel, MeasurementModel, ScanSessionModel, SessionMarkerModel, TargetModel
from app.schemas.export import ExportRequest, ExportResponse


class ExportService:
    @staticmethod
    async def generate_export(
        db: AsyncSession, session_id: str, req: ExportRequest
    ) -> ExportResponse:
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Fetch markers
        markers_res = await db.execute(
            select(SessionMarkerModel).where(SessionMarkerModel.session_id == session_id).order_by(SessionMarkerModel.timestamp.asc())
        )
        markers = markers_res.scalars().all()

        # Fetch targets
        targets_res = await db.execute(
            select(TargetModel).where(TargetModel.session_id == session_id)
        )
        targets = targets_res.scalars().all()

        # Fetch measurements
        meas_res = await db.execute(
            select(MeasurementModel).where(MeasurementModel.session_id == session_id).order_by(MeasurementModel.sequence.asc())
        )
        measurements = meas_res.scalars().all()

        if req.format == "csv":
            content_str = ExportService._build_csv(session, targets, markers, measurements, req)
        else:
            content_str = ExportService._build_json(session, targets, markers, measurements, req)

        content_bytes = content_str.encode("utf-8")
        checksum = hashlib.sha256(content_bytes).hexdigest()

        job = ExportJobModel(
            session_id=session_id,
            format=req.format,
            status="completed",
            file_size_bytes=len(content_bytes),
            checksum_sha256=checksum,
            file_content=content_str,
            created_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        return ExportResponse(
            id=job.id,
            session_id=job.session_id,
            format=job.format,
            status="completed",
            file_size_bytes=job.file_size_bytes,
            checksum_sha256=job.checksum_sha256,
            download_url=f"/api/v1/exports/{job.id}/download",
            created_at=job.created_at,
        )

    @staticmethod
    def _build_json(
        session: ScanSessionModel,
        targets: list,
        markers: list,
        measurements: list,
        req: ExportRequest,
    ) -> str:
        export_dict: Dict[str, Any] = {
            "schema_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "timezone": "UTC",
            "session": {
                "id": session.id,
                "name": session.name,
                "mode": session.mode,
                "collector_id": session.collector_id,
                "status": session.status,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "config": session.config,
                "tags": session.tags,
            },
            "markers": [
                {
                    "id": m.id,
                    "label": m.label,
                    "notes": m.notes,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in markers
            ],
            "targets": [
                {
                    "target_id": t.target_id,
                    "display_name": t.display_name,
                    "mode": t.mode,
                    "channel": t.channel,
                    "band": t.band,
                    "first_seen": t.first_seen.isoformat(),
                    "last_seen": t.last_seen.isoformat(),
                    "metadata": t.metadata_json,
                }
                for t in targets
            ],
        }

        if req.include_raw_samples:
            export_dict["measurements"] = [
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
                    "quality": m.quality_flags,
                }
                for m in measurements
            ]

        return json.dumps(export_dict, indent=2)

    @staticmethod
    def _build_csv(
        session: ScanSessionModel,
        targets: list,
        markers: list,
        measurements: list,
        req: ExportRequest,
    ) -> str:
        output = io.StringIO()
        writer = csv.writer(output)

        # Header metadata comments
        writer.writerow(["# Schema Version", "1.0"])
        writer.writerow(["# Session ID", session.id])
        writer.writerow(["# Session Name", session.name])
        writer.writerow(["# Mode", session.mode])
        writer.writerow(["# Collector", session.collector_id])
        writer.writerow(["# Exported At", datetime.now(timezone.utc).isoformat()])
        writer.writerow([])

        # Table header
        writer.writerow([
            "sequence",
            "captured_at",
            "target_id",
            "signal_value",
            "unit",
            "noise_floor",
            "snr",
            "channel",
            "band",
            "frequency_hz",
        ])

        for m in measurements:
            writer.writerow([
                m.sequence,
                m.captured_at.isoformat(),
                m.target_id,
                m.signal_value,
                m.unit,
                m.noise_floor or "",
                m.snr or "",
                m.channel or "",
                m.band or "",
                m.frequency_hz or "",
            ])

        return output.getvalue()

    @staticmethod
    async def get_export_file(db: AsyncSession, export_id: str) -> Optional[Tuple[str, str, str]]:
        job = await db.get(ExportJobModel, export_id)
        if not job or not job.file_content:
            return None
        mime = "text/csv" if job.format == "csv" else "application/json"
        filename = f"signal_scan_{job.session_id}_{job.id}.{job.format}"
        return job.file_content, mime, filename


export_service = ExportService()
