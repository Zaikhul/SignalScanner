import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ChannelMetricModel,
    ExportAuditLogModel,
    MeasurementModel,
    ScanSessionModel,
    SessionManifestModel,
)
from app.core.security import verify_operator_auth
from app.db.session import get_db
from app.schemas.manifest import SessionProvenanceManifest
from app.services.session_manager import session_manager

router = APIRouter(prefix="/sessions", tags=["provenance-manifests"], dependencies=[Depends(verify_operator_auth)])


@router.get("/{session_id}/manifest", response_model=SessionProvenanceManifest)
async def get_session_manifest(
    session_id: str, db: AsyncSession = Depends(get_db)
):
    """Retrieve immutable cryptographic provenance manifest for a session (PROV-01)."""
    manifest = await session_manager.get_session_manifest(db, session_id)
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provenance manifest not found for session '{session_id}'. Complete the session first.",
        )
    return manifest


@router.get("/{session_id}/evidence-bundle")
async def download_evidence_bundle(
    session_id: str, db: AsyncSession = Depends(get_db)
):
    """
    Downloads an immutable cryptographically verified ZIP Evidence Bundle (EVID-01).
    Contents:
    - manifest.json (PROV-01 Provenance Manifest)
    - observations.json (Normalized measurements with FQ-01 quality telemetry)
    - channel_metrics.json (CHAN-01 Inferred vs Measured channel metrics)
    - checksums.sha256 (SHA256 of all files inside the bundle)
    """
    session = await db.get(ScanSessionModel, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    manifest = await session_manager.get_session_manifest(db, session_id)
    manifest_data = manifest.model_dump(mode="json") if manifest else {"session_id": session_id, "status": session.status}

    # Fetch measurements
    res_m = await db.execute(
        select(MeasurementModel)
        .where(MeasurementModel.session_id == session_id)
        .order_by(MeasurementModel.sequence.asc())
    )
    measurements = [
        {
            "sequence": m.sequence,
            "captured_at": m.captured_at.isoformat() if m.captured_at else None,
            "target_id": m.target_id,
            "signal_value": m.signal_value,
            "unit": m.unit,
            "noise_floor": m.noise_floor,
            "snr": m.snr,
            "frequency_hz": m.frequency_hz,
            "channel": m.channel,
            "band": m.band,
            "scan_id": m.scan_id,
            "freshness": m.freshness,
            "source_method": m.source_method,
            "rssi_processing": m.rssi_processing,
            "quality_flags": m.quality_flags,
        }
        for m in res_m.scalars().all()
    ]

    # Fetch channel metrics
    res_cm = await db.execute(
        select(ChannelMetricModel)
        .where(ChannelMetricModel.session_id == session_id)
        .order_by(ChannelMetricModel.created_at.asc())
    )
    channel_metrics = [
        {
            "channel": cm.channel,
            "metric_type": cm.metric_type,
            "value": cm.value,
            "unit": cm.unit,
            "evidence": cm.evidence,
            "method": cm.method,
            "window_ms": cm.window_ms,
            "uncertainty": cm.uncertainty,
            "created_at": cm.created_at.isoformat() if cm.created_at else None,
        }
        for cm in res_cm.scalars().all()
    ]

    # Prepare JSON bytes
    manifest_bytes = json.dumps(manifest_data, indent=2, sort_keys=True).encode("utf-8")
    obs_bytes = json.dumps(measurements, indent=2, sort_keys=True).encode("utf-8")
    cm_bytes = json.dumps(channel_metrics, indent=2, sort_keys=True).encode("utf-8")

    # Compute individual checksums
    h_man = hashlib.sha256(manifest_bytes).hexdigest()
    h_obs = hashlib.sha256(obs_bytes).hexdigest()
    h_cm = hashlib.sha256(cm_bytes).hexdigest()

    checksum_lines = (
        f"{h_man}  manifest.json\n"
        f"{h_obs}  observations.json\n"
        f"{h_cm}  channel_metrics.json\n"
    )
    checksum_bytes = checksum_lines.encode("utf-8")

    # Build ZIP archive in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("observations.json", obs_bytes)
        zf.writestr("channel_metrics.json", cm_bytes)
        zf.writestr("checksums.sha256", checksum_bytes)

    zip_bytes = zip_buffer.getvalue()
    bundle_checksum = hashlib.sha256(zip_bytes).hexdigest()

    # Log export in export_audit_logs (PRIV-01 & EVID-01)
    audit_log = ExportAuditLogModel(
        session_id=session_id,
        format="zip_evidence_bundle",
        scope="full_session_evidence",
        checksum_sha256=bundle_checksum,
        exported_by="authorized_operator",
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit_log)
    await db.commit()

    filename = f"evidence_bundle_{session_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
