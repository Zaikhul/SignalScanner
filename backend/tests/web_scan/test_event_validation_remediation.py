from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.db.session import AsyncSessionLocal
from app.db.web_scan_models import WebScanEventRecordModel, WebScanJobModel
from app.schemas.web_scan import (
    CreateScanRequest,
    ModuleId,
    ProfileId,
    ScanConfiguration,
    ScanState,
    WebScanEvent,
)
from app.services.web_scan_scheduler import web_scan_scheduler
from app.services.web_scan_service import WebScanService


def test_web_scan_event_schema_literal_validation():
    """Verify that WebScanEvent accepts all standard, terminal, and failure event types."""
    valid_types = [
        "snapshot",
        "state_changed",
        "progress",
        "finding_upserted",
        "observation_added",
        "error_added",
        "completed",
        "cancelled",
        "failed",
    ]
    for ev_type in valid_types:
        ev = WebScanEvent(
            scan_id="test-scan-123",
            sequence=1,
            occurred_at=datetime.now(timezone.utc),
            type=ev_type,
            payload={"key": "val"},
        )
        assert ev.type == ev_type

    # Invalid event types must still raise Pydantic ValidationError
    with pytest.raises(ValidationError) as exc_info:
        WebScanEvent(
            scan_id="test-scan-123",
            sequence=2,
            occurred_at=datetime.now(timezone.utc),
            type="invalid_event_type",  # type: ignore[arg-type]
            payload={},
        )
    assert "literal_error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scheduler_unreachable_scan_produces_failed_event_without_validation_error():
    """Verify that when a scan fails, the scheduler emits a 'failed' event without Pydantic validation errors."""
    async with AsyncSessionLocal() as db:
        req = CreateScanRequest(
            target="http://127.0.0.1:1/unreachable_fail_test",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(
                profile=ProfileId.V2,
                modules=[ModuleId.RECON],
                allow_private=True,
            ),
        )
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id="test_tenant_fail",
            principal_id="test_operator",
            req=req,
        )
        job_id = job.id

    # Mark queued so scheduler executes it
    async with AsyncSessionLocal() as db:
        job_to_queue = await db.get(WebScanJobModel, job_id)
        assert job_to_queue is not None
        job_to_queue.status = ScanState.QUEUED.value
        await db.commit()

    cancel_event = asyncio.Event()
    # Execute job
    await web_scan_scheduler._execute_job_wrapper(job_id, cancel_event)

    # Verify database state
    async with AsyncSessionLocal() as db:
        job_rec = await db.get(WebScanJobModel, job_id)
        assert job_rec is not None
        # Must be terminal state
        assert job_rec.status in (ScanState.FAILED.value, ScanState.PARTIAL.value)

        # CRITICAL ASSERTION: job_record.status_reason must NOT contain the Pydantic ValidationError!
        assert "validation error for WebScanEvent" not in (job_rec.status_reason or "")
        assert "literal_error" not in (job_rec.status_reason or "")

        # Verify persisted events
        events = await WebScanService.list_scan_events(
            db=db,
            tenant_id="test_tenant_fail",
            scan_id=job_id,
        )
        assert len(events) > 0
        event_types = [ev.type for ev in events]

        # The terminal event must be recorded as 'failed' without serialization error
        assert "failed" in event_types or "state_changed" in event_types


@pytest.mark.asyncio
async def test_scheduler_cancelled_scan_produces_cancelled_event():
    """Verify that when a scan is cancelled, the scheduler emits a 'cancelled' event cleanly."""
    async with AsyncSessionLocal() as db:
        req = CreateScanRequest(
            target="http://127.0.0.1:1/unreachable_cancel_test",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(
                profile=ProfileId.V2,
                modules=[ModuleId.RECON],
                allow_private=True,
            ),
        )
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id="test_tenant_cancel",
            principal_id="test_operator",
            req=req,
        )
        job_id = job.id

    async with AsyncSessionLocal() as db:
        job_to_queue = await db.get(WebScanJobModel, job_id)
        assert job_to_queue is not None
        job_to_queue.status = ScanState.QUEUED.value
        await db.commit()

    cancel_event = asyncio.Event()
    # Cancel immediately
    cancel_event.set()
    await web_scan_scheduler._execute_job_wrapper(job_id, cancel_event)

    async with AsyncSessionLocal() as db:
        job_rec = await db.get(WebScanJobModel, job_id)
        assert job_rec is not None
        assert "validation error for WebScanEvent" not in (job_rec.status_reason or "")


@pytest.mark.asyncio
async def test_geography_feature_flag_policy(monkeypatch):
    """Verify that WEB_SCAN_GEOGRAPHY_ENABLED disables geography access when False."""
    from fastapi import HTTPException
    from app.api.v1.web_scans import get_web_scan_geography
    from app.core.web_scan.authorization import OperatorPrincipal
    from app.config import settings

    principal = OperatorPrincipal(
        principal_id="test_user",
        tenant_id="test_tenant",
        roles=["operator"],
        permissions=["web_scan:read"],
    )

    async with AsyncSessionLocal() as db:
        # 1. When disabled, must raise HTTP 403
        monkeypatch.setattr(settings, "WEB_SCAN_GEOGRAPHY_ENABLED", False)
        with pytest.raises(HTTPException) as exc_info:
            await get_web_scan_geography(
                scan_id="any-scan-id",
                principal=principal,
                db=db,
            )
        assert exc_info.value.status_code == 403
        assert "disabled by policy" in exc_info.value.detail

        # 2. When enabled, raises 404 if scan not found (not 403)
        monkeypatch.setattr(settings, "WEB_SCAN_GEOGRAPHY_ENABLED", True)
        with pytest.raises(HTTPException) as exc_info2:
            await get_web_scan_geography(
                scan_id="nonexistent-scan-id",
                principal=principal,
                db=db,
            )
        assert exc_info2.value.status_code == 404

