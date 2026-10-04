from datetime import datetime, timedelta, timezone
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channel_health_engine import channel_health_engine
from app.core.stream_engine import stream_engine
from app.db.models import (
    ChannelHealthSnapshotModel,
    ChannelRecommendationModel,
    ChannelValidationRunModel,
    MeasurementModel,
    ScanSessionModel,
    SessionMarkerModel,
    TargetModel,
)
from app.schemas.channel_health import (
    CandidateRecommendation,
    ChannelHealthItem,
    ChannelHealthSnapshotResponse,
    ChannelRecommendationResponse,
    ChannelValidationRequest,
    ChannelValidationResponse,
    ComponentProvenance,
    ConfidenceLevel,
    EvaluateRecommendationRequest,
    MetricDelta,
    ObservationWindowInfo,
    RegulatoryDomainInfo,
)


class ChannelHealthService:
    @staticmethod
    async def evaluate_channel_health_and_recommend(
        db: AsyncSession,
        session_id: str,
        req: Optional[EvaluateRecommendationRequest] = None,
    ) -> ChannelRecommendationResponse:
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Scan session {session_id} not found")

        band = req.band if req and req.band else "2.4GHz"
        channel_width_mhz = req.channel_width_mhz if req and req.channel_width_mhz else 20
        window_sec = req.observation_window_sec if req and req.observation_window_sec else 300
        reg_domain = req.regulatory_domain if req and req.regulatory_domain else "ID"

        # Determine observation time bounds
        now_utc = datetime.now(timezone.utc)
        window_start = now_utc - timedelta(seconds=window_sec)

        # Query measurements within the window
        m_res = await db.execute(
            select(MeasurementModel)
            .where(
                MeasurementModel.session_id == session_id,
                MeasurementModel.captured_at >= window_start,
            )
            .order_by(MeasurementModel.captured_at.asc())
        )
        measurements_db = m_res.scalars().all()
        measurement_dicts: List[Dict[str, Any]] = []
        unique_sequences = set()
        latest_meas_by_target: Dict[str, MeasurementModel] = {}
        for m in measurements_db:
            latest_meas_by_target[m.target_id] = m
            measurement_dicts.append({
                "target_id": m.target_id,
                "channel": m.channel,
                "band": m.band,
                "signal_value": m.signal_value,
                "noise_floor": m.noise_floor,
                "snr": m.snr,
                "sequence": m.sequence,
                "captured_at": m.captured_at.isoformat() if m.captured_at else None,
            })
            unique_sequences.add(m.sequence)

        # Query targets for the session and filter active ones in the observation window
        t_res = await db.execute(
            select(TargetModel).where(TargetModel.session_id == session_id)
        )
        all_targets = t_res.scalars().all()
        target_dicts: List[Dict[str, Any]] = []
        for t in all_targets:
            lm = latest_meas_by_target.get(t.target_id)
            t_last_seen = t.last_seen
            if t_last_seen and t_last_seen.tzinfo is None:
                t_last_seen = t_last_seen.replace(tzinfo=timezone.utc)
            
            # Exclude targets that have no measurements in window and last_seen is prior to window
            if not lm and (not t_last_seen or t_last_seen < window_start):
                continue

            if lm:
                rssi = lm.signal_value
                width = (lm.raw_extra or {}).get("channel_width_mhz") or (t.metadata_json or {}).get("channel_width_mhz", 20)
            else:
                rssi = (t.metadata_json or {}).get("latest_rssi", -90.0)
                width = (t.metadata_json or {}).get("channel_width_mhz", 20)

            target_dicts.append({
                "target_id": t.target_id,
                "display_name": t.display_name,
                "channel": t.channel,
                "band": t.band,
                "signal_value": rssi,
                "channel_width_mhz": width,
            })

        scan_cycles = max(len(unique_sequences), 1 if measurement_dicts else 0)

        # Evaluate channels using core engine
        channel_items, quality_flags = channel_health_engine.evaluate_channels(
            band=band,
            channel_width_mhz=channel_width_mhz,
            targets=target_dicts,
            measurements=measurement_dicts,
            regulatory_domain=reg_domain,
        )

        obs_window = ObservationWindowInfo(
            from_time=window_start.isoformat(),
            to_time=now_utc.isoformat(),
            duration_seconds=float(window_sec),
            scan_cycles=scan_cycles,
        )

        # 1. Create Immutable Input Snapshot
        snapshot_id = f"chs_{uuid.uuid4().hex[:12]}"
        snapshot_model = ChannelHealthSnapshotModel(
            id=snapshot_id,
            session_id=session_id,
            band=band,
            channel_width_mhz=channel_width_mhz,
            observation_window=obs_window.model_dump(),
            regulatory_domain={
                "value": reg_domain,
                "provenance": ComponentProvenance.CONFIGURED.value,
                "source": "organization_setting",
            },
            channels_data=[item.model_dump() for item in channel_items],
            quality_flags=quality_flags,
            created_at=now_utc,
        )
        db.add(snapshot_model)
        await db.flush()

        # 2. Generate Immutable Recommendation Decision Record
        recommendation_resp = channel_health_engine.generate_recommendation(
            session_id=session_id,
            snapshot_id=snapshot_id,
            band=band,
            channel_width_mhz=channel_width_mhz,
            channel_items=channel_items,
            observation_window=obs_window,
            quality_flags=quality_flags,
        )

        recommendation_model = ChannelRecommendationModel(
            id=recommendation_resp.recommendation_id,
            session_id=session_id,
            snapshot_id=snapshot_id,
            algorithm_version=recommendation_resp.algorithm_version,
            primary_channel=recommendation_resp.primary.model_dump(),
            alternatives=[alt.model_dump() for alt in recommendation_resp.alternatives],
            confidence=recommendation_resp.confidence.value,
            confidence_reasons=recommendation_resp.confidence_reasons,
            missing_evidence=recommendation_resp.missing_evidence,
            supporting_factors=recommendation_resp.supporting_factors,
            counter_signals=recommendation_resp.counter_signals,
            conflict_detected=recommendation_resp.conflict_detected,
            created_at=now_utc,
        )
        db.add(recommendation_model)
        await db.commit()

        # 3. Broadcast Realtime Fan-out Events
        try:
            snapshot_payload = {
                "type": "channel.health_updated",
                "schema_version": "1.2",
                "session_id": session_id,
                "snapshot_id": snapshot_id,
                "band": band,
                "channels": [item.model_dump() for item in channel_items],
                "quality_flags": quality_flags,
                "observation_window": obs_window.model_dump(),
                "timestamp": now_utc.isoformat(),
            }
            await stream_engine.publish_event(session_id, snapshot_payload)

            rec_payload = {
                "type": "channel.recommendation_updated",
                "schema_version": "1.2",
                "session_id": session_id,
                "recommendation": recommendation_resp.model_dump(mode="json"),
                "timestamp": now_utc.isoformat(),
            }
            await stream_engine.publish_event(session_id, rec_payload)
        except Exception:
            pass

        return recommendation_resp

    @staticmethod
    async def get_latest_channel_health_snapshot(
        db: AsyncSession,
        session_id: str,
        band: str = "2.4GHz",
    ) -> Optional[ChannelHealthSnapshotResponse]:
        query = (
            select(ChannelHealthSnapshotModel)
            .where(
                ChannelHealthSnapshotModel.session_id == session_id,
                ChannelHealthSnapshotModel.band == band,
            )
            .order_by(desc(ChannelHealthSnapshotModel.created_at))
            .limit(1)
        )
        res = await db.execute(query)
        snapshot = res.scalar_one_or_none()
        if not snapshot:
            return None

        channels = [ChannelHealthItem(**ch) for ch in snapshot.channels_data]
        obs = ObservationWindowInfo(**snapshot.observation_window)
        reg = RegulatoryDomainInfo(**snapshot.regulatory_domain)

        return ChannelHealthSnapshotResponse(
            schema_version="1.2",
            snapshot_id=snapshot.id,
            session_id=snapshot.session_id,
            band=snapshot.band,
            channel_width_mhz=snapshot.channel_width_mhz,
            observation_window=obs,
            regulatory_domain=reg,
            channels=channels,
            quality_flags=snapshot.quality_flags,
            created_at=snapshot.created_at.isoformat(),
        )

    @staticmethod
    async def get_latest_recommendation(
        db: AsyncSession,
        session_id: str,
    ) -> Optional[ChannelRecommendationResponse]:
        query = (
            select(ChannelRecommendationModel)
            .where(ChannelRecommendationModel.session_id == session_id)
            .order_by(desc(ChannelRecommendationModel.created_at))
            .limit(1)
        )
        res = await db.execute(query)
        rec = res.scalar_one_or_none()
        if not rec:
            return None

        # Fetch snapshot for observation window info
        snap = await db.get(ChannelHealthSnapshotModel, rec.snapshot_id)
        obs_window = ObservationWindowInfo(
            from_time=(snap.observation_window.get("from_time") if snap else rec.created_at.isoformat()),
            to_time=(snap.observation_window.get("to_time") if snap else rec.created_at.isoformat()),
            duration_seconds=(snap.observation_window.get("duration_seconds", 300.0) if snap else 300.0),
            scan_cycles=(snap.observation_window.get("scan_cycles", 1) if snap else 1),
        )

        return ChannelRecommendationResponse(
            schema_version="1.2",
            recommendation_id=rec.id,
            session_id=rec.session_id,
            input_snapshot_id=rec.snapshot_id,
            algorithm_version=rec.algorithm_version,
            band=snap.band if snap else "2.4GHz",
            channel_width_mhz=snap.channel_width_mhz if snap else 20,
            primary=CandidateRecommendation(**rec.primary_channel),
            alternatives=[CandidateRecommendation(**a) for a in rec.alternatives],
            confidence=ConfidenceLevel(rec.confidence),
            confidence_reasons=rec.confidence_reasons,
            missing_evidence=rec.missing_evidence,
            supporting_factors=rec.supporting_factors,
            counter_signals=rec.counter_signals,
            conflict_detected=rec.conflict_detected,
            observation_window=obs_window,
            freshness_status="fresh",
            created_at=rec.created_at.isoformat(),
        )

    @staticmethod
    async def get_recommendation_by_id(
        db: AsyncSession,
        recommendation_id: str,
    ) -> Optional[ChannelRecommendationResponse]:
        rec = await db.get(ChannelRecommendationModel, recommendation_id)
        if not rec:
            return None

        snap = await db.get(ChannelHealthSnapshotModel, rec.snapshot_id)
        obs_window = ObservationWindowInfo(
            from_time=(snap.observation_window.get("from_time") if snap else rec.created_at.isoformat()),
            to_time=(snap.observation_window.get("to_time") if snap else rec.created_at.isoformat()),
            duration_seconds=(snap.observation_window.get("duration_seconds", 300.0) if snap else 300.0),
            scan_cycles=(snap.observation_window.get("scan_cycles", 1) if snap else 1),
        )

        return ChannelRecommendationResponse(
            schema_version="1.2",
            recommendation_id=rec.id,
            session_id=rec.session_id,
            input_snapshot_id=rec.snapshot_id,
            algorithm_version=rec.algorithm_version,
            band=snap.band if snap else "2.4GHz",
            channel_width_mhz=snap.channel_width_mhz if snap else 20,
            primary=CandidateRecommendation(**rec.primary_channel),
            alternatives=[CandidateRecommendation(**a) for a in rec.alternatives],
            confidence=ConfidenceLevel(rec.confidence),
            confidence_reasons=rec.confidence_reasons,
            missing_evidence=rec.missing_evidence,
            supporting_factors=rec.supporting_factors,
            counter_signals=rec.counter_signals,
            conflict_detected=rec.conflict_detected,
            observation_window=obs_window,
            freshness_status="fresh",
            created_at=rec.created_at.isoformat(),
        )

    @staticmethod
    async def create_channel_validation_run(
        db: AsyncSession,
        session_id: str,
        req: ChannelValidationRequest,
    ) -> ChannelValidationResponse:
        """
        Calculates before-after metric deltas around a channel change marker or midpoint (PRD 10.4.7).
        Adheres to PRD rule: reports observed changes ('perubahan teramati') without automated causal claims.
        """
        session = await db.get(ScanSessionModel, session_id)
        if not session:
            raise ValueError(f"Scan session {session_id} not found")

        marker_label: Optional[str] = None
        ref_time: datetime = datetime.now(timezone.utc)

        if req.marker_id:
            marker = await db.get(SessionMarkerModel, req.marker_id)
            if not marker or marker.session_id != session_id:
                raise ValueError(f"Marker '{req.marker_id}' not found in session '{session_id}'")
            marker_label = marker.label
            ref_time = marker.timestamp

        before_start = ref_time - timedelta(seconds=req.before_window_sec)
        after_end = ref_time + timedelta(seconds=req.after_window_sec)

        # Query measurements for before window (strictly before ref_time to prevent boundary double-counting)
        q_before = await db.execute(
            select(MeasurementModel).where(
                MeasurementModel.session_id == session_id,
                MeasurementModel.captured_at >= before_start,
                MeasurementModel.captured_at < ref_time,
            )
        )
        m_before = q_before.scalars().all()

        # Query measurements for after window (from ref_time onward)
        q_after = await db.execute(
            select(MeasurementModel).where(
                MeasurementModel.session_id == session_id,
                MeasurementModel.captured_at >= ref_time,
                MeasurementModel.captured_at <= after_end,
            )
        )
        m_after = q_after.scalars().all()

        # Helper to summarize metrics from sample list
        def summarize_samples(samples: List[MeasurementModel]) -> Dict[str, Any]:
            if not samples:
                return {"mean_rssi": None, "rssi_std": None, "count": 0.0, "unique_targets": 0.0}
            vals = [s.signal_value for s in samples]
            mean_val = sum(vals) / len(vals)
            var = sum((v - mean_val) ** 2 for v in vals) / len(vals)
            return {
                "mean_rssi": round(mean_val, 1),
                "rssi_std": round(var ** 0.5, 2),
                "count": float(len(samples)),
                "unique_targets": float(len(set(s.target_id for s in samples))),
            }

        b_metrics = summarize_samples(m_before)
        a_metrics = summarize_samples(m_after)

        has_sufficient_data = bool(m_before and m_after)

        if not has_sufficient_data:
            deltas: Dict[str, MetricDelta] = {
                "mean_signal_rssi": MetricDelta(
                    before=b_metrics["mean_rssi"],
                    after=a_metrics["mean_rssi"],
                    delta=None,
                    improved=None,
                ),
                "signal_temporal_instability": MetricDelta(
                    before=b_metrics["rssi_std"],
                    after=a_metrics["rssi_std"],
                    delta=None,
                    improved=None,
                ),
            }
            summary = "Data tidak mencukupi (insufficient_data): Tidak ada sampel teramati pada window pengamatan sebelum atau sesudah."
        else:
            delta_rssi = round(a_metrics["mean_rssi"] - b_metrics["mean_rssi"], 1)
            delta_std = round(a_metrics["rssi_std"] - b_metrics["rssi_std"], 2)

            deltas = {
                "mean_signal_rssi": MetricDelta(
                    before=b_metrics["mean_rssi"],
                    after=a_metrics["mean_rssi"],
                    delta=delta_rssi,
                    improved=delta_rssi > 0,
                ),
                "signal_temporal_instability": MetricDelta(
                    before=b_metrics["rssi_std"],
                    after=a_metrics["rssi_std"],
                    delta=delta_std,
                    improved=delta_std < 0,
                ),
            }

            # Formulate non-causal observation statement
            observations: List[str] = []
            if delta_rssi > 0:
                observations.append(f"Kekuatan sinyal teramati meningkat {delta_rssi} dB")
            elif delta_rssi < 0:
                observations.append(f"Kekuatan sinyal teramati menurun {abs(delta_rssi)} dB")

            if delta_std < 0:
                observations.append("Variansi temporal teramati lebih stabil")
            elif delta_std > 0:
                observations.append("Variansi temporal teramati lebih berfluktuasi")

            summary = (
                "Perubahan teramati: " + ", ".join(observations)
                if observations
                else "Tidak ada perubahan signifikan teramati pada window perbandingan"
            )

        val_id = f"chv_{uuid.uuid4().hex[:12]}"
        val_model = ChannelValidationRunModel(
            id=val_id,
            session_id=session_id,
            marker_id=req.marker_id,
            before_window={
                "from": before_start.isoformat(),
                "to": ref_time.isoformat(),
                "samples": int(b_metrics["count"]),
            },
            after_window={
                "from": ref_time.isoformat(),
                "to": after_end.isoformat(),
                "samples": int(a_metrics["count"]),
            },
            metric_deltas={k: v.model_dump() for k, v in deltas.items()},
            summary_label=summary,
            created_at=datetime.now(timezone.utc),
        )
        db.add(val_model)
        await db.commit()

        return ChannelValidationResponse(
            validation_id=val_id,
            session_id=session_id,
            baseline_recommendation_id=None,
            marker_id=req.marker_id,
            marker_label=marker_label,
            before_window=val_model.before_window,
            after_window=val_model.after_window,
            metric_deltas=deltas,
            summary_label=summary,
            created_at=val_model.created_at.isoformat(),
        )

    @staticmethod
    async def list_channel_validation_runs(
        db: AsyncSession,
        session_id: str,
    ) -> List[ChannelValidationResponse]:
        query = (
            select(ChannelValidationRunModel)
            .where(ChannelValidationRunModel.session_id == session_id)
            .order_by(desc(ChannelValidationRunModel.created_at))
        )
        res = await db.execute(query)
        runs = res.scalars().all()

        out: List[ChannelValidationResponse] = []
        for r in runs:
            deltas = {k: MetricDelta(**v) for k, v in r.metric_deltas.items()}
            out.append(
                ChannelValidationResponse(
                    validation_id=r.id,
                    session_id=r.session_id,
                    baseline_recommendation_id=r.baseline_recommendation_id,
                    marker_id=r.marker_id,
                    before_window=r.before_window,
                    after_window=r.after_window,
                    metric_deltas=deltas,
                    summary_label=r.summary_label,
                    created_at=r.created_at.isoformat(),
                )
            )
        return out


channel_health_service = ChannelHealthService()
