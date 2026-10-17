import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
import aiosqlite
import tempfile
import os

from app.main import app
from app.db.session import init_db, AsyncSessionLocal
from app.schemas.common import SessionStatus, ScanMode
from app.services.session_manager import session_manager
from app.services.collector_service import collector_service
from app.schemas.session import CreateSessionRequest
from app.schemas.measurement import MeasurementBatch, NormalizedMeasurementEvent, SignalData, RadioMetadata
from collector.app.core.buffer_queue import OfflineBufferQueue
from collector.app.config import collector_settings


@pytest.mark.asyncio
async def test_f04_two_phase_stop_and_drain_ingest():
    """Verify that stopping status accepts in-flight batches and finalize evaluates completeness (F04)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        # 1. Create active session
        req = CreateSessionRequest(
            name="Two Phase Test",
            mode="wifi",
            collector_id="col_default",
            source_type="collector",
        )
        ses = await session_manager.create_session(db, req)
        await session_manager.start_session(db, ses.id)

        # 2. Trigger two-phase stop with drain=True
        ses_stopping = await session_manager.stop_session(db, ses.id, drain=True)
        assert ses_stopping.status == SessionStatus.STOPPING

        # 3. Ingest in-flight batch during STOPPING phase - must SUCCEED!
        batch = MeasurementBatch(
            session_id=ses.id,
            collector_id="col_default",
            source_type="collector",
            sequence_from=1,
            sequence_to=2,
            measurements=[
                NormalizedMeasurementEvent(
                    session_id=ses.id,
                    collector_id="col_default",
                    sequence=1,
                    mode=ScanMode.WIFI,
                    target_id="00:11:22:33:44:55",
                    signal=SignalData(value=-60.0),
                    radio=RadioMetadata(channel=6, band="2.4GHz"),
                ),
                NormalizedMeasurementEvent(
                    session_id=ses.id,
                    collector_id="col_default",
                    sequence=2,
                    mode=ScanMode.WIFI,
                    target_id="00:11:22:33:44:55",
                    signal=SignalData(value=-62.0),
                    radio=RadioMetadata(channel=6, band="2.4GHz"),
                ),
            ],
        )
        ingest_res = await session_manager.ingest_batch(db, batch)
        assert ingest_res["ingested_count"] == 2

        # 4. Finalize session - no gaps, so must be COMPLETED
        final_res = await session_manager.finalize_session(db, ses.id)
        assert final_res.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_f04_sequence_gap_results_in_incomplete_status():
    """Verify that finalize with missing sequence ranges marks session as INCOMPLETE (F04)."""
    await init_db()
    async with AsyncSessionLocal() as db:
        req = CreateSessionRequest(
            name="Gap Test",
            mode="wifi",
            collector_id="col_default",
            source_type="collector",
        )
        ses = await session_manager.create_session(db, req)
        await session_manager.start_session(db, ses.id)

        # Ingest sequence 1 and sequence 5 (gap between 2 and 4)
        for seq in (1, 5):
            batch = MeasurementBatch(
                session_id=ses.id,
                collector_id="col_default",
                source_type="collector",
                sequence_from=seq,
                sequence_to=seq,
                measurements=[
                    NormalizedMeasurementEvent(
                        session_id=ses.id,
                        collector_id="col_default",
                        sequence=seq,
                        mode=ScanMode.WIFI,
                        target_id="00:11:22:33:44:55",
                        signal=SignalData(value=-70.0),
                        radio=RadioMetadata(channel=1, band="2.4GHz"),
                    )
                ],
            )
            await session_manager.ingest_batch(db, batch)

        final_res = await session_manager.finalize_session(db, ses.id)
        assert final_res.status == SessionStatus.INCOMPLETE


@pytest.mark.asyncio
async def test_f04_buffer_loss_ledger_and_atomic_dlq():
    """Verify that buffer overflow writes to loss ledger and DLQ transition is atomic (F04)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_buffer.db")
        bq = OfflineBufferQueue(db_path=db_path)
        await bq.init_queue()

        # 1. Test atomic dead-letter move
        batch_id = await bq.push_batch("ses_01", {"data": "test_batch", "sequence_from": 1, "sequence_to": 1})
        success = await bq.move_to_dead_letter_atomic(batch_id, status_code=400, reason_code="PERMANENT_ERROR")
        assert success is True

        # Verify it is in DLQ and no longer in buffered_batches
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM buffered_batches WHERE id = ?", (batch_id,))
            assert (await cursor.fetchone())[0] == 0
            cursor = await db.execute("SELECT status_code, error_reason FROM dead_letter_batches WHERE session_id = 'ses_01'")
            row = await cursor.fetchone()
            assert row[0] == 400
            assert row[1] == "PERMANENT_ERROR"

        # 2. Test loss ledger on buffer overflow
        orig_max = collector_settings.MAX_BUFFER_RECORDS
        collector_settings.MAX_BUFFER_RECORDS = 5
        try:
            for i in range(7):
                await bq.push_batch("ses_overflow", {"seq": i})

            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute("SELECT COUNT(*) FROM buffer_loss_ledger WHERE session_id = 'ses_overflow'")
                assert (await cursor.fetchone())[0] >= 1
        finally:
            collector_settings.MAX_BUFFER_RECORDS = orig_max


@pytest.mark.asyncio
async def test_f05_readyz_readiness_probe():
    """Verify that /readyz validates database connectivity and returns dialect (F05)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/readyz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert "dialect" in data


@pytest.mark.asyncio
async def test_f06_collector_command_status_lifecycle():
    """Verify that command lifecycle status progresses from pending to running to completed (F06)."""
    cmd = collector_service.queue_command(
        collector_id="col_cmd_test_01",
        type="test_lifecycle",
    )
    assert cmd.status == "pending"

    # Acknowledge
    assert collector_service.acknowledge_command("col_cmd_test_01", cmd.command_id) is True
    # Progress to running
    assert collector_service.update_command_status("col_cmd_test_01", cmd.command_id, "running") is True
    # Progress to completed
    assert collector_service.update_command_status("col_cmd_test_01", cmd.command_id, "completed") is True
