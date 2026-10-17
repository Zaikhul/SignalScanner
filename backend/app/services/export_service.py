import csv
import hashlib
import io
import json
from datetime import datetime, timezone, timedelta
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

        hasher = hashlib.sha256()
        chunks: list[str] = []

        def append_chunk(text: str):
            chunks.append(text)
            hasher.update(text.encode("utf-8"))

        if req.format == "csv":
            # Header metadata comments
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["# Schema Version", "1.0"])
            writer.writerow(["# Session ID", session.id])
            writer.writerow(["# Session Name", session.name])
            writer.writerow(["# Mode", session.mode])
            writer.writerow(["# Collector", session.collector_id])
            writer.writerow(["# Exported At", datetime.now(timezone.utc).isoformat()])
            writer.writerow([])
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
            append_chunk(output.getvalue())

            # Stream measurements in chunks of 500
            meas_stream = await db.stream_scalars(
                select(MeasurementModel)
                .where(MeasurementModel.session_id == session_id)
                .order_by(MeasurementModel.sequence.asc())
                .execution_options(yield_per=500)
            )
            try:
                row_buffer = io.StringIO()
                row_writer = csv.writer(row_buffer)
                batch_count = 0
                async for m in meas_stream:
                    row_writer.writerow([
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
                    batch_count += 1
                    if batch_count >= 500:
                        append_chunk(row_buffer.getvalue())
                        row_buffer = io.StringIO()
                        row_writer = csv.writer(row_buffer)
                        batch_count = 0
                if batch_count > 0:
                    append_chunk(row_buffer.getvalue())
            finally:
                await meas_stream.close()

        else:
            mask_ssid = False
            if session.config and isinstance(session.config, dict):
                priv = session.config.get("privacy_config", {})
                if isinstance(priv, dict):
                    mask_ssid = priv.get("mask_ssid", False)

            base_dict: Dict[str, Any] = {
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
                        "display_name": (
                            (f"***{t.display_name[-3:]}" if len(t.display_name) > 3 else "***")
                            if (mask_ssid and t.display_name)
                            else t.display_name
                        ),
                        "mode": t.mode,
                        "channel": t.channel,
                        "band": t.band,
                        "first_seen": t.first_seen.isoformat(),
                        "last_seen": t.last_seen.isoformat(),
                        "metadata": {
                            k: (
                                (f"***{v[-3:]}" if len(str(v)) > 3 else "***")
                                if (mask_ssid and k in ("ssid", "display_name", "raw_ssid") and v)
                                else v
                            )
                            for k, v in (t.metadata_json or {}).items()
                        },
                    }
                    for t in targets
                ],
            }

            if not req.include_raw_samples:
                append_chunk(json.dumps(base_dict, indent=2))
            else:
                base_dict["measurements"] = []
                full_json = json.dumps(base_dict, indent=2)
                # Split at measurements array to stream items without full memory instantiation
                split_token = '"measurements": []'
                parts = full_json.split(split_token)
                append_chunk(parts[0] + '"measurements": [\n')

                meas_stream = await db.stream_scalars(
                    select(MeasurementModel)
                    .where(MeasurementModel.session_id == session_id)
                    .order_by(MeasurementModel.sequence.asc())
                    .execution_options(yield_per=500)
                )
                try:
                    first = True
                    meas_batch: list[str] = []
                    async for m in meas_stream:
                        m_dict = {
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
                        item_json = json.dumps(m_dict, indent=4)
                        indented = "\n".join("    " + line for line in item_json.split("\n"))
                        if not first:
                            meas_batch.append(",\n" + indented)
                        else:
                            meas_batch.append(indented)
                            first = False

                        if len(meas_batch) >= 500:
                            append_chunk("".join(meas_batch))
                            meas_batch = []
                    if meas_batch:
                        append_chunk("".join(meas_batch))
                finally:
                    await meas_stream.close()

                append_chunk("\n  ]" + parts[1])

        content_str = "".join(chunks)
        checksum = hasher.hexdigest()
        content_bytes = content_str.encode("utf-8")

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
        mask_ssid = False
        if session.config and isinstance(session.config, dict):
            priv = session.config.get("privacy_config", {})
            if isinstance(priv, dict):
                mask_ssid = priv.get("mask_ssid", False)

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
                    "display_name": (
                        (f"***{t.display_name[-3:]}" if len(t.display_name) > 3 else "***")
                        if (mask_ssid and t.display_name)
                        else t.display_name
                    ),
                    "mode": t.mode,
                    "channel": t.channel,
                    "band": t.band,
                    "first_seen": t.first_seen.isoformat(),
                    "last_seen": t.last_seen.isoformat(),
                    "metadata": {
                        k: (
                            (f"***{v[-3:]}" if len(str(v)) > 3 else "***")
                            if (mask_ssid and k in ("ssid", "display_name", "raw_ssid") and v)
                            else v
                        )
                        for k, v in (t.metadata_json or {}).items()
                    },
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

    @staticmethod
    async def purge_expired_exports(
        db: AsyncSession, max_age_hours: int = 72
    ) -> int:
        """Purges export jobs older than max_age_hours according to retention policy (F07)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        stmt = select(ExportJobModel).where(ExportJobModel.created_at < cutoff)
        res = await db.execute(stmt)
        jobs = res.scalars().all()
        count = len(jobs)
        for job in jobs:
            await db.delete(job)
        await db.commit()
        return count


export_service = ExportService()
