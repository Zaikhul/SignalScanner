import pytest
from app.db.session import AsyncSessionLocal
from app.schemas.web_scan import CreateScanRequest, ScanConfiguration, ScanState
from app.services.web_scan_service import WebScanService


@pytest.mark.asyncio
async def test_create_scan_and_idempotency():
    async with AsyncSessionLocal() as db:
        req = CreateScanRequest(
            target="http://idemp-test.com",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(allow_private=True),
        )

        job1 = await WebScanService.create_scan_job(
            db=db,
            tenant_id="tenant_test",
            principal_id="principal_test",
            req=req,
            idempotency_key="idemp_key_12345",
        )
        assert job1.status == ScanState.PENDING
        assert job1.target_display == "http://idemp-test.com/"

        # Second call with same idempotency key returns the same job
        job2 = await WebScanService.create_scan_job(
            db=db,
            tenant_id="tenant_test",
            principal_id="principal_test",
            req=req,
            idempotency_key="idemp_key_12345",
        )
        assert job2.id == job1.id


@pytest.mark.asyncio
async def test_cancel_scan_lifecycle():
    async with AsyncSessionLocal() as db:
        req = CreateScanRequest(
            target="http://cancel-test.com",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(allow_private=True),
        )
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id="tenant_test",
            principal_id="principal_test",
            req=req,
        )

        # Cancel pending scan -> immediately transitions to CANCELLED
        cancelled_job = await WebScanService.cancel_scan_job(
            db=db,
            tenant_id="tenant_test",
            principal_id="principal_test",
            scan_id=job.id,
        )
        assert cancelled_job is not None
        assert cancelled_job.status == ScanState.CANCELLED


@pytest.mark.asyncio
async def test_websocket_ticket_one_time_consumption():
    async with AsyncSessionLocal() as db:
        ticket = await WebScanService.create_ws_ticket(
            db=db,
            tenant_id="tenant_test",
            principal_id="principal_test",
            scan_id="scan_mock_999",
        )
        assert ticket is not None

        # First consumption succeeds
        auth_data = await WebScanService.consume_ws_ticket(db, ticket)
        assert auth_data is not None
        assert auth_data["scan_id"] == "scan_mock_999"

        # Second consumption returns None (single-use)
        auth_data_second = await WebScanService.consume_ws_ticket(db, ticket)
        assert auth_data_second is None


def test_web_scan_event_progress_payload_preservation():
    from datetime import datetime, timezone
    from app.schemas.web_scan import WebScanEvent

    progress_payload = {
        "current_module": "recon",
        "progress_percent": 25,
        "modules_completed": 1,
        "modules_total": 4,
    }
    event = WebScanEvent(
        scan_id="scan_test_fidelity",
        sequence=3,
        occurred_at=datetime.now(timezone.utc),
        type="progress",
        payload=progress_payload,
    )
    assert isinstance(event.payload, dict)
    assert event.payload["current_module"] == "recon"
    assert event.payload["progress_percent"] == 25
    assert event.payload["modules_completed"] == 1
    assert event.payload["modules_total"] == 4

    dump = event.model_dump()
    assert dump["payload"]["current_module"] == "recon"
    assert dump["payload"]["progress_percent"] == 25


@pytest.mark.asyncio
async def test_web_scan_engine_initial_sequence():
    from unittest.mock import AsyncMock
    from app.core.web_scan.engine import WebScanEngine
    from app.schemas.web_scan import ScanConfiguration

    emitted_events = []

    async def mock_event_sink(ev):
        emitted_events.append(ev)

    config = ScanConfiguration(allow_private=True, modules=[])
    engine = WebScanEngine(
        scan_id="test_seq_engine",
        target_url="http://test.internal",
        config=config,
        event_sink=mock_event_sink,
        initial_sequence=1,
    )

    await engine.run()
    # The first event emitted must have sequence = 2 (not 1)
    assert len(emitted_events) >= 1
    assert emitted_events[0].sequence == 2
    assert emitted_events[0].type == "state_changed"
    assert emitted_events[0].payload["status"] == "scanning"


@pytest.mark.asyncio
async def test_web_scan_engine_global_semaphore_support(monkeypatch):
    import asyncio
    from app.core.web_scan.engine import WebScanEngine
    from app.core.web_scan.http_client import WebScanHttpClient
    from app.schemas.web_scan import ScanConfiguration

    sem = asyncio.Semaphore(12)
    config = ScanConfiguration(allow_private=True, modules=[])
    engine = WebScanEngine(
        scan_id="test-sem-scan",
        target_url="http://127.0.0.1:8000",
        config=config,
        global_semaphore=sem,
    )
    assert engine.global_semaphore is sem

    captured_client_sem = None
    original_init = WebScanHttpClient.__init__

    def mock_http_init(self, *args, **kwargs):
        nonlocal captured_client_sem
        captured_client_sem = kwargs.get("global_semaphore")
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(WebScanHttpClient, "__init__", mock_http_init)
    await engine.run()
    assert captured_client_sem is sem


@pytest.mark.asyncio
async def test_web_scan_scheduler_datetime_json_serialization():
    import asyncio
    from app.services.web_scan_service import WebScanService
    from app.services.web_scan_scheduler import web_scan_scheduler
    from app.schemas.web_scan import CreateScanRequest, ScanConfiguration, ModuleId, ProfileId
    from app.db.web_scan_models import WebScanJobModel

    async with AsyncSessionLocal() as db:
        # Create a job with unreachable target (port 1 refuses immediately)
        req = CreateScanRequest(
            target="http://127.0.0.1:1/unreachable",
            authorization_acknowledged=True,
            configuration=ScanConfiguration(
                profile=ProfileId.V2,
                modules=[ModuleId.RECON, ModuleId.HEADERS],
                allow_private=True,
            ),
        )
        job = await WebScanService.create_scan_job(
            db=db,
            tenant_id="test_tenant",
            principal_id="test_operator",
            req=req,
        )
        job_id = job.id
    async with AsyncSessionLocal() as db:
        job_to_queue = await db.get(WebScanJobModel, job_id)
        job_to_queue.status = ScanState.QUEUED.value
        await db.commit()

    cancel_event = asyncio.Event()
    await web_scan_scheduler._execute_job_wrapper(job_id, cancel_event)

    async with AsyncSessionLocal() as db:
        job_rec = await db.get(WebScanJobModel, job_id)
        assert job_rec is not None
        # Must NOT be an Execution error: (builtins.TypeError) Object of type datetime is not JSON serializable
        assert "builtins.TypeError" not in (job_rec.status_reason or "")
        assert "not JSON serializable" not in (job_rec.status_reason or "")
        # Should have proper status_reason and summary_data saved
        assert job_rec.status in ("failed", "partial", "completed")
        assert job_rec.summary_data is not None
        assert isinstance(job_rec.summary_data, dict)
        if "errors" in job_rec.summary_data:
            assert isinstance(job_rec.summary_data["errors"], list)


