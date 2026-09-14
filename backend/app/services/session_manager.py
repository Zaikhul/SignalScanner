from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import pseudonymize_identifier
from app.core.signal_processor import signal_processor
from app.core.stream_engine import stream_engine
from app.services.collector_service import collector_service
from app.db.models import (
    ChannelMetricModel,
    CollectorModel,
    MeasurementModel,
    ScanSessionModel,
    SessionManifestModel,
    SessionMarkerModel,
    TargetModel,
)
from app.schemas.common import ScanMode, SessionStatus
from app.schemas.manifest import ClockQuality, SequenceSummary, SessionProvenanceManifest
from app.schemas.measurement import (
    MeasurementBatch,
    NormalizedMeasurementEvent,
    TargetSummary,
)
from app.schemas.session import (
    CreateSessionRequest,
    SessionMarkerCreate,
    SessionMarkerResponse,
    SessionResponse,
    SessionSummary,
)


class SessionManager:
    @staticmethod
    async def create_session(db: AsyncSession, req: CreateSessionRequest) -> SessionResponse:
        # Validate collector exists or create a default auto-collector if first run
        res_col = await db.execute(select(CollectorModel).where(CollectorModel.id == req.collector_id))
        collector = res_col.scalar_one_or_none()
        if not collector:
            # Auto-register local collector
            collector = CollectorModel(
                id=req.collector_id,
                name="Local Host Collector",
                platform="windows",
                version="1.0.0",
                status="ready",
                capabilities={
                    "supported_modes": ["wifi", "bluetooth", "radio"],
                    "adapters": [],
                    "platform": "windows",
                    "version": "1.0.0",
                    "can_sdr": True,
                    "can_wifi": True,
                    "can_ble": True,
                },
                last_seen=datetime.now(timezone.utc),
            )
            db.add(collector)
            await db.flush()

        new_session = ScanSessionModel(
            name=req.name,
            mode=req.mode.value,
            collector_id=req.collector_id,
            source_type=getattr(req, "source_type", "collector"),
            status=SessionStatus.DRAFT.value,
            config={
                "duration_seconds": req.duration_seconds,
                "sample_interval_ms": req.sample_interval_ms,
                "radio_config": req.radio_config.model_dump() if req.radio_config else None,
                "privacy_config": req.privacy_config.model_dump(),
            },
            tags=req.tags,
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)

        return await SessionManager.get_session_response(db, new_session.id)

    @staticmethod
    async def start_session(db: AsyncSession, session_id: str) -> SessionResponse:
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.status = SessionStatus.ACTIVE.value
        session.started_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(session)

        # If session is bound to a hardware collector, queue start_scan command
        if getattr(session, "source_type", "collector") == "collector" and session.collector_id:
            sample_interval = 500
            if session.config and isinstance(session.config, dict):
                sample_interval = session.config.get("sample_interval_ms", 500)
            collector_service.queue_command(
                collector_id=session.collector_id,
                type="start_scan",
                session_id=session.id,
                mode=ScanMode(session.mode) if session.mode in ScanMode._value2member_map_ else ScanMode.WIFI,
                sample_interval_ms=sample_interval,
            )

        # Notify via Stream Engine
        await stream_engine.publish_event(
            session_id,
            {
                "type": "session.state_changed",
                "schema_version": "2.0",
                "session_id": session_id,
                "status": SessionStatus.ACTIVE.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return await SessionManager.get_session_response(db, session_id)

    @staticmethod
    async def pause_session(db: AsyncSession, session_id: str) -> SessionResponse:
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.status = SessionStatus.PAUSED.value
        await db.commit()
        await db.refresh(session)

        if getattr(session, "source_type", "collector") == "collector" and session.collector_id:
            collector_service.queue_command(
                collector_id=session.collector_id,
                type="pause_scan",
                session_id=session.id,
            )

        await stream_engine.publish_event(
            session_id,
            {
                "type": "session.state_changed",
                "schema_version": "2.0",
                "session_id": session_id,
                "status": SessionStatus.PAUSED.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return await SessionManager.get_session_response(db, session_id)

    @staticmethod
    async def resume_session(db: AsyncSession, session_id: str) -> SessionResponse:
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.status = SessionStatus.ACTIVE.value
        await db.commit()
        await db.refresh(session)

        if getattr(session, "source_type", "collector") == "collector" and session.collector_id:
            sample_interval = 500
            if session.config and isinstance(session.config, dict):
                sample_interval = session.config.get("sample_interval_ms", 500)
            collector_service.queue_command(
                collector_id=session.collector_id,
                type="start_scan",
                session_id=session.id,
                mode=ScanMode(session.mode) if session.mode in ScanMode._value2member_map_ else ScanMode.WIFI,
                sample_interval_ms=sample_interval,
            )

        await stream_engine.publish_event(
            session_id,
            {
                "type": "session.state_changed",
                "schema_version": "2.0",
                "session_id": session_id,
                "status": SessionStatus.ACTIVE.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return await SessionManager.get_session_response(db, session_id)

    @staticmethod
    async def stop_session(db: AsyncSession, session_id: str) -> SessionResponse:
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.status = SessionStatus.COMPLETED.value
        session.ended_at = datetime.now(timezone.utc)

        if getattr(session, "source_type", "collector") == "collector" and session.collector_id:
            collector_service.queue_command(
                collector_id=session.collector_id,
                type="stop_scan",
                session_id=session.id,
            )

        # 1. Compute Sequence Summary & Checksum for Provenance Manifest (PROV-01)
        res_seq = await db.execute(
            select(
                func.count(MeasurementModel.id),
                func.min(MeasurementModel.sequence),
                func.max(MeasurementModel.sequence),
            ).where(MeasurementModel.session_id == session_id)
        )
        total_count, min_seq, max_seq = res_seq.one()

        res_col = await db.get(CollectorModel, session.collector_id) if session.collector_id else None

        manifest = SessionProvenanceManifest(
            manifest_version="1.0",
            session_id=session_id,
            collector_id=session.collector_id or "unknown",
            collector_version=res_col.version if res_col else "1.0.0",
            os={"platform": res_col.platform if res_col else "windows"},
            adapter={"capabilities": res_col.capabilities if res_col else {}},
            scan_config=session.config or {},
            processing_version="signal-pipeline@2.0",
            processing_config_hash=hashlib.sha256(json.dumps(session.config or {}, sort_keys=True).encode()).hexdigest(),
            clock=ClockQuality(offset_ms=0.0, uncertainty_ms=2.0, source="system_monotonic"),
            privacy_policy_id="privacy-hmac-v1",
            schema_version="measurement@2.0",
            sequence_summary=SequenceSummary(
                first_sequence=min_seq or 0,
                last_sequence=max_seq or 0,
                total_received=total_count or 0,
                missing_ranges=[],
            ),
            created_at=session.ended_at,
        )
        manifest.manifest_checksum = manifest.compute_checksum()

        # Persist immutable manifest
        manifest_model = SessionManifestModel(
            session_id=session_id,
            manifest_version=manifest.manifest_version,
            manifest_json=manifest.model_dump(mode="json"),
            checksum_sha256=manifest.manifest_checksum,
            created_at=session.ended_at,
        )
        db.add(manifest_model)

        await db.commit()
        await db.refresh(session)

        await stream_engine.publish_event(
            session_id,
            {
                "type": "session.state_changed",
                "schema_version": "2.0",
                "session_id": session_id,
                "status": SessionStatus.COMPLETED.value,
                "manifest_checksum": manifest.manifest_checksum,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return await SessionManager.get_session_response(db, session_id)

    @staticmethod
    async def add_marker(
        db: AsyncSession, session_id: str, marker_req: SessionMarkerCreate
    ) -> SessionMarkerResponse:
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        marker = SessionMarkerModel(
            session_id=session_id,
            label=marker_req.label,
            notes=marker_req.notes,
            timestamp=marker_req.timestamp,
        )
        db.add(marker)
        await db.commit()
        await db.refresh(marker)

        # Publish marker event
        await stream_engine.publish_event(
            session_id,
            {
                "type": "marker.added",
                "schema_version": "2.0",
                "session_id": session_id,
                "marker": {
                    "id": marker.id,
                    "label": marker.label,
                    "notes": marker.notes,
                    "timestamp": marker.timestamp.isoformat(),
                },
            },
        )

        return SessionMarkerResponse(
            id=marker.id,
            session_id=marker.session_id,
            label=marker.label,
            notes=marker.notes,
            timestamp=marker.timestamp,
        )

    @staticmethod
    async def ingest_batch(
        db: AsyncSession, batch: MeasurementBatch
    ) -> Dict[str, Any]:
        """
        Processes normalized measurements:
        1. Validates source_type and collector_id binding.
        2. Pseudonymizes IDs if needed.
        3. Applies EMA smoothing.
        4. Upserts Targets.
        5. Inserts Measurements with FQ-01 & OBS-01 quality telemetry.
        6. Calculates CHAN-01 bss_overlap_index channel metrics.
        7. Fanouts to WebSocket stream.
        """
        session = await db.get(ScanSessionModel, batch.session_id)
        if not session:
            raise ValueError(f"Session {batch.session_id} not found")

        # Validate session is actively accepting ingests
        if session.status not in (SessionStatus.ACTIVE.value, SessionStatus.STARTING.value):
            raise ValueError(
                f"SESSION_NOT_ACTIVE: Session '{session.id}' is in '{session.status}' status, must be active"
            )

        batch_source = getattr(batch, "source_type", "collector") or "collector"
        session_source = getattr(session, "source_type", "collector") or "collector"
        if batch_source != session_source:
            raise ValueError(
                f"SOURCE_MISMATCH: Batch source '{batch_source}' does not match session source '{session_source}'"
            )

        if session_source == "collector" and batch.collector_id != session.collector_id:
            raise ValueError(
                f"COLLECTOR_MISMATCH: Batch collector_id '{batch.collector_id}' does not match session collector_id '{session.collector_id}'"
            )

        # Validate measurement mode matches session mode
        if batch.measurements:
            for m in batch.measurements:
                m_mode = m.mode.value if hasattr(m.mode, "value") else str(m.mode)
                if m_mode != session.mode:
                    raise ValueError(
                        f"MODE_MISMATCH: Batch measurement mode '{m_mode}' does not match session mode '{session.mode}'"
                    )

        processed_events: List[Dict[str, Any]] = []
        batch_target_dicts: List[Dict[str, Any]] = []

        for m in batch.measurements:
            target_id = m.target_id
            if not target_id.startswith("hmac:"):
                target_id = pseudonymize_identifier(target_id)
                m.target_id = target_id

            # Apply EMA smoothing
            smoothed = signal_processor.calculate_ema(target_id, m.signal.value)
            m.signal.smoothed_value = smoothed

            # Calculate SNR if noise is available or compute from floor
            if m.signal.noise is not None and m.signal.snr is None:
                m.signal.snr = signal_processor.calculate_snr(m.signal.value, m.signal.noise)

            # Check or create target
            res_target = await db.execute(
                select(TargetModel).where(
                    TargetModel.session_id == batch.session_id,
                    TargetModel.target_id == target_id,
                )
            )
            target = res_target.scalar_one_or_none()
            
            chan = m.radio.channel if m.radio else None
            band = m.radio.band if m.radio else None
            freq = m.radio.frequency_hz if m.radio else None

            if not target:
                target = TargetModel(
                    id=f"tgt_{target_id[-10:]}_{batch.session_id[-6:]}",
                    session_id=batch.session_id,
                    target_id=target_id,
                    display_name=m.display_name,
                    mode=m.mode.value if hasattr(m.mode, "value") else str(m.mode),
                    channel=chan,
                    band=band,
                    first_seen=m.captured_at,
                    last_seen=m.captured_at,
                    metadata_json=m.extra_metadata or {},
                )
                db.add(target)
                await db.flush()
            else:
                target.last_seen = m.captured_at
                if m.display_name:
                    target.display_name = m.display_name
                if chan:
                    target.channel = chan
                if band:
                    target.band = band

            # Extract FQ-01 quality attributes
            q = m.quality
            scan_id = getattr(q, "scan_id", None) or getattr(batch, "scan_id", None)
            trace_id = getattr(m, "trace_id", None) or getattr(batch, "trace_id", None)
            freshness = getattr(q, "freshness", "fresh")
            source_method = getattr(q, "source_method", "unknown")
            rssi_processing = getattr(q, "rssi_processing", "unknown")

            # Create Measurement record
            meas = MeasurementModel(
                session_id=batch.session_id,
                target_id=target_id,
                target_db_id=target.id,
                sequence=m.sequence,
                captured_at=m.captured_at,
                signal_value=m.signal.value,
                unit=m.signal.unit,
                noise_floor=m.signal.noise,
                snr=m.signal.snr,
                frequency_hz=freq,
                channel=chan,
                band=band,
                scan_id=scan_id,
                trace_id=trace_id,
                freshness=freshness,
                source_method=source_method,
                rssi_processing=rssi_processing,
                quality_flags=q.model_dump(mode="json") if hasattr(q, "model_dump") else {},
                raw_extra=m.extra_metadata or {},
            )
            db.add(meas)

            event_dict = m.model_dump(mode="json")
            processed_events.append(event_dict)
            batch_target_dicts.append({
                "target_id": target_id,
                "display_name": m.display_name,
                "signal_value": m.signal.value,
                "channel": chan,
                "band": band,
            })

        # Calculate and store CHAN-01 channel metrics
        if batch_target_dicts and session.mode == "wifi":
            ch_metrics = signal_processor.calculate_channel_overlap_metrics(batch_target_dicts)
            for cm in ch_metrics:
                metric_row = ChannelMetricModel(
                    session_id=batch.session_id,
                    channel=cm["channel"],
                    metric_type=cm["metric_type"],
                    value=cm["value"],
                    unit=cm["unit"],
                    evidence=cm["evidence"],
                    method=cm["method"],
                    window_ms=cm["window_ms"],
                    uncertainty=cm["uncertainty"],
                    created_at=datetime.now(timezone.utc),
                )
                db.add(metric_row)

        await db.commit()

        # Publish WebSocket event envelope with quality & channel metadata
        envelope = {
            "type": "measurement.batch",
            "schema_version": "2.0",
            "trace_id": batch.trace_id,
            "scan_id": batch.scan_id,
            "session_id": batch.session_id,
            "collector_id": batch.collector_id,
            "sequence_from": batch.sequence_from,
            "sequence_to": batch.sequence_to,
            "sent_at": batch.sent_at.isoformat(),
            "data": processed_events,
        }
        await stream_engine.publish_event(batch.session_id, envelope)

        return {"status": "ok", "ingested_count": len(batch.measurements)}

    @staticmethod
    async def get_session_manifest(
        db: AsyncSession, session_id: str
    ) -> Optional[SessionProvenanceManifest]:
        """Retrieves and verifies the cryptographic session manifest (PROV-01)."""
        res = await db.execute(
            select(SessionManifestModel)
            .where(SessionManifestModel.session_id == session_id)
            .order_by(SessionManifestModel.created_at.desc())
        )
        row = res.scalar_one_or_none()
        if not row:
            return None
        return SessionProvenanceManifest(**row.manifest_json)

    @staticmethod
    async def get_session_response(
        db: AsyncSession, session_id: str
    ) -> SessionResponse:
        result = await db.execute(
            select(ScanSessionModel)
            .options(selectinload(ScanSessionModel.markers))
            .where(ScanSessionModel.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Compute summary
        res_meas = await db.execute(
            select(
                func.count(MeasurementModel.id),
                func.min(MeasurementModel.signal_value),
                func.max(MeasurementModel.signal_value),
                func.avg(MeasurementModel.noise_floor),
            ).where(MeasurementModel.session_id == session_id)
        )
        count, min_val, max_val, avg_noise = res_meas.one()

        res_targets = await db.execute(
            select(func.count(TargetModel.id)).where(TargetModel.session_id == session_id)
        )
        unique_targets = res_targets.scalar() or 0

        # Calculate duration
        duration = 0.0
        if session.started_at:
            start_t = session.started_at
            if start_t.tzinfo is None:
                start_t = start_t.replace(tzinfo=timezone.utc)
            end_t = session.ended_at or datetime.now(timezone.utc)
            if end_t.tzinfo is None:
                end_t = end_t.replace(tzinfo=timezone.utc)
            duration = max(0.0, (end_t - start_t).total_seconds())

        summary = SessionSummary(
            total_samples=count or 0,
            unique_targets=unique_targets,
            min_signal=round(min_val, 1) if min_val is not None else None,
            max_signal=round(max_val, 1) if max_val is not None else None,
            median_signal=None,
            noise_floor_estimate=round(avg_noise, 1) if avg_noise is not None else -95.0,
            duration_seconds=round(duration, 1),
        )

        marker_resps = [
            SessionMarkerResponse(
                id=m.id,
                session_id=m.session_id,
                label=m.label,
                notes=m.notes,
                timestamp=m.timestamp,
            )
            for m in session.markers
        ]

        return SessionResponse(
            id=session.id,
            name=session.name,
            mode=ScanMode(session.mode) if session.mode in ScanMode._value2member_map_ else ScanMode.WIFI,
            collector_id=session.collector_id,
            source_type=getattr(session, "source_type", "collector"),
            status=SessionStatus(session.status) if session.status in SessionStatus._value2member_map_ else SessionStatus.DRAFT,
            config=session.config,
            tags=session.tags,
            started_at=session.started_at,
            ended_at=session.ended_at,
            created_at=session.created_at,
            summary=summary,
            markers=marker_resps,
        )

    @staticmethod
    async def list_sessions(
        db: AsyncSession,
        mode: Optional[ScanMode] = None,
        status: Optional[SessionStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[SessionResponse], int]:
        query = select(ScanSessionModel)
        if mode:
            query = query.where(ScanSessionModel.mode == mode.value)
        if status:
            query = query.where(ScanSessionModel.status == status.value)

        # Count total
        count_q = select(func.count(ScanSessionModel.id))
        if mode:
            count_q = count_q.where(ScanSessionModel.mode == mode.value)
        if status:
            count_q = count_q.where(ScanSessionModel.status == status.value)
        total_res = await db.execute(count_q)
        total = total_res.scalar() or 0

        # Paginate
        query = (
            query.order_by(ScanSessionModel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        res = await db.execute(query)
        sessions = res.scalars().all()

        responses = []
        for s in sessions:
            resp = await SessionManager.get_session_response(db, s.id)
            responses.append(resp)

        return responses, total

    @staticmethod
    async def list_targets(
        db: AsyncSession, session_id: str
    ) -> List[TargetSummary]:
        res_targets = await db.execute(
            select(TargetModel).where(TargetModel.session_id == session_id)
        )
        targets = res_targets.scalars().all()
        summaries = []
        for t in targets:
            # Query measurement stats for this target
            res_stats = await db.execute(
                select(
                    func.count(MeasurementModel.id),
                    func.min(MeasurementModel.signal_value),
                    func.max(MeasurementModel.signal_value),
                    func.avg(MeasurementModel.signal_value),
                    func.avg(MeasurementModel.snr),
                ).where(
                    MeasurementModel.session_id == session_id,
                    MeasurementModel.target_id == t.target_id,
                )
            )
            count, min_s, max_s, avg_s, avg_snr = res_stats.one()

            # Query latest measurement
            res_latest = await db.execute(
                select(MeasurementModel)
                .where(
                    MeasurementModel.session_id == session_id,
                    MeasurementModel.target_id == t.target_id,
                )
                .order_by(MeasurementModel.captured_at.desc())
                .limit(1)
            )
            latest_m = res_latest.scalar_one_or_none()

            latest_val = latest_m.signal_value if latest_m else -80.0
            unit_val = latest_m.unit if latest_m else "dBm"
            freshness_val = latest_m.freshness if latest_m else "fresh"
            source_method_val = latest_m.source_method if latest_m else "unknown"

            summaries.append(
                TargetSummary(
                    target_id=t.target_id,
                    display_name=t.display_name,
                    mode=ScanMode(t.mode) if t.mode in ScanMode._value2member_map_ else ScanMode.WIFI,
                    first_seen=t.first_seen,
                    last_seen=t.last_seen,
                    sample_count=count or 1,
                    latest_signal=latest_val,
                    unit=unit_val,
                    min_signal=min_s if min_s is not None else latest_val,
                    max_signal=max_s if max_s is not None else latest_val,
                    median_signal=avg_s if avg_s is not None else latest_val,
                    avg_snr=round(avg_snr, 1) if avg_snr is not None else None,
                    channel=t.channel,
                    band=t.band,
                    freshness=freshness_val,
                    source_method=source_method_val,
                    is_pinned=t.is_pinned,
                    extra=t.metadata_json,
                )
            )
        return summaries


session_manager = SessionManager()
