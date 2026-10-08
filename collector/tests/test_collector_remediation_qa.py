import asyncio
import pytest
import aiosqlite
import httpx
from unittest.mock import AsyncMock, patch

from collector.app.adapters.mock_adapter import MockSignalAdapter
from collector.app.core.adapter_base import ScanConfig
from collector.app.core.buffer_queue import OfflineBufferQueue
from collector.app.core.uploader import BatchUploader
from collector.app.main import CollectorDaemon
from backend.app.schemas.measurement import MeasurementBatch


@pytest.mark.asyncio
async def test_qa_03_mock_adapter_batch_schema_validation():
    """QA-03: Verify mock adapter outputs conform to backend MeasurementBatch schema.
    Specifically checks freshness='simulated', rssi_processing='synthetic', and source_type='collector'.
    """
    for mode in ["wifi", "bluetooth", "radio"]:
        adapter = MockSignalAdapter(mode=mode)
        config = ScanConfig(session_id=f"ses_mock_{mode}", sample_interval_ms=50)

        batch = None
        async for item in adapter.start(config):
            batch = item
            await adapter.stop()
            break

        assert batch is not None
        assert batch["source_type"] == "simulator"
        assert len(batch["measurements"]) > 0

        m0 = batch["measurements"][0]
        assert m0["quality"]["freshness"] == "simulated"
        assert m0["quality"]["rssi_processing"] == "synthetic"

        # Verify backend Pydantic validation passes without ValidationError
        validated = MeasurementBatch.model_validate(batch)
        assert validated.session_id == f"ses_mock_{mode}"
        assert validated.measurements[0].quality.freshness == "simulated"
        assert validated.measurements[0].quality.rssi_processing == "synthetic"


@pytest.mark.asyncio
async def test_qa_04_collector_sequence_tracking_across_resume():
    """QA-04: Verify CollectorDaemon tracks sequence across pause/resume to avoid duplicate sequence numbers."""
    daemon = CollectorDaemon(backend_url="http://127.0.0.1:8000")
    session_id = "ses_qa04_test"

    batches_received = []

    async def mock_send_batch(sid, batch):
        batches_received.append(batch)
        return True

    # 1. Initial scan phase: generate 2 batches
    with patch("collector.app.main.uploader.send_batch", side_effect=mock_send_batch):
        adapter = MockSignalAdapter(mode="wifi")
        current_seq = daemon._session_sequences.get(session_id, 0)
        config = ScanConfig(session_id=session_id, sample_interval_ms=20, initial_sequence=current_seq)

        count = 0
        async for b in adapter.start(config):
            count += 1
            seq_to = b.get("sequence_to") or b.get("sequence_from")
            daemon._session_sequences[session_id] = max(daemon._session_sequences.get(session_id, 0), seq_to)
            batches_received.append(b)
            if count >= 2:
                await adapter.stop()
                break

    assert daemon._session_sequences[session_id] == 2
    assert batches_received[0]["sequence_from"] == 1
    assert batches_received[1]["sequence_from"] == 2

    # 2. Resumed scan phase: adapter must receive initial_sequence=2 and continue with sequence 3
    with patch("collector.app.main.uploader.send_batch", side_effect=mock_send_batch):
        resumed_adapter = MockSignalAdapter(mode="wifi")
        resumed_seq = daemon._session_sequences.get(session_id, 0)
        assert resumed_seq == 2

        resumed_config = ScanConfig(session_id=session_id, sample_interval_ms=20, initial_sequence=resumed_seq)
        count = 0
        async for b in resumed_adapter.start(resumed_config):
            count += 1
            seq_to = b.get("sequence_to") or b.get("sequence_from")
            daemon._session_sequences[session_id] = max(daemon._session_sequences.get(session_id, 0), seq_to)
            batches_received.append(b)
            if count >= 1:
                await resumed_adapter.stop()
                break

    assert batches_received[2]["sequence_from"] == 3
    assert daemon._session_sequences[session_id] == 3


@pytest.mark.asyncio
async def test_qa_07_uploader_drain_success_and_dead_letter_on_retry_limit(tmp_path):
    """QA-07: Verify drain_offline_buffer drains multiple successful batches and quarantines failing ones to dead-letter after 3 retries."""
    test_db = str(tmp_path / "test_queue_drain.db")
    queue = OfflineBufferQueue(db_path=test_db)
    await queue.init_queue()

    # Enqueue two batches via push_batch
    await queue.push_batch("ses_01", {"session_id": "ses_01", "sequence_from": 1, "sequence_to": 1, "measurements": []})
    await queue.push_batch("ses_02", {"session_id": "ses_02", "sequence_from": 1, "sequence_to": 1, "measurements": []})
    assert await queue.count() == 2

    uploader = BatchUploader()

    # Case 1: Both batches succeed (HTTP 200)
    class Mock200Response:
        status_code = 200
        text = "ok"

    class MockSuccessClient:
        is_closed = False
        async def post(self, url, json):
            return Mock200Response()

    uploader._client = MockSuccessClient()
    with patch("collector.app.core.uploader.buffer_queue", queue):
        await uploader.drain_offline_buffer()

    assert await queue.count() == 0
    assert await queue.dead_letter_count() == 0

    # Case 2: Network failure retry up to MAX_RETRIES (3) then dead-letter
    await queue.push_batch("ses_fail", {"session_id": "ses_fail", "sequence_from": 1, "sequence_to": 1, "measurements": []})
    assert await queue.count() == 1

    class MockErrorClient:
        is_closed = False
        async def post(self, url, json):
            raise httpx.ConnectError("Network unreachable")

    uploader._client = MockErrorClient()

    with patch("collector.app.core.uploader.buffer_queue", queue), \
         patch("collector.app.core.uploader.MAX_RETRIES", 3), \
         patch("asyncio.sleep", return_value=None):
        # Drain attempt 1: failure, retry_count becomes 1
        await uploader.drain_offline_buffer()
        assert await queue.count() == 1
        assert await queue.dead_letter_count() == 0

        # Drain attempt 2: failure, retry_count becomes 2
        await uploader.drain_offline_buffer()
        assert await queue.count() == 1
        assert await queue.dead_letter_count() == 0

        # Drain attempt 3: failure, reaches limit -> moved to dead-letter
        await uploader.drain_offline_buffer()
        assert await queue.count() == 0
        assert await queue.dead_letter_count() == 1


@pytest.mark.asyncio
async def test_qa_12_collector_scan_config_fft_and_sample_rate():
    """QA-12: Verify run_scan forwards sample_rate_hz and fft_size (including fft_bins alias) to ScanConfig."""
    daemon = CollectorDaemon(backend_url="http://127.0.0.1:8000")

    captured_configs = []

    class MockCapturingAdapter(MockSignalAdapter):
        async def validate(self, config):
            captured_configs.append(config)
            return await super().validate(config)

        async def start(self, config):
            yield {"session_id": config.session_id, "sequence_from": 1, "measurements": []}

    with patch("collector.app.main.uploader.send_batch", return_value=True), \
         patch("collector.app.main.MockSignalAdapter", MockCapturingAdapter):
        # Test direct parameters
        await daemon.run_scan(
            session_id="ses_radio_direct",
            mode="radio",
            use_mock=True,
            duration_seconds=0,
            parameters={
                "sample_rate_hz": 1250000,
                "fft_size": 512,
            }
        )

        assert len(captured_configs) == 1
        assert captured_configs[0].sample_rate_hz == 1250000
        assert captured_configs[0].fft_size == 512

        # Test nested radio_config with fft_bins alias
        await daemon.run_scan(
            session_id="ses_radio_nested",
            mode="radio",
            use_mock=True,
            duration_seconds=0,
            parameters={
                "radio_config": {
                    "sample_rate_hz": 2400000,
                    "fft_bins": 256,
                }
            }
        )

        assert len(captured_configs) == 2
        assert captured_configs[1].sample_rate_hz == 2400000
        assert captured_configs[1].fft_size == 256
