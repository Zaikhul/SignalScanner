import asyncio
import os
import pytest
import aiosqlite
from collector.app.core.buffer_queue import OfflineBufferQueue
from collector.app.core.uploader import BatchUploader


@pytest.mark.asyncio
async def test_buffer_queue_auto_quarantine_legacy_sessions(tmp_path):
    test_db = str(tmp_path / "test_buffer.db")
    queue = OfflineBufferQueue(db_path=test_db)

    # 1. Initialize queue
    await queue.init_queue()

    # 2. Insert a legacy session batch (ses_cli_*) directly into buffered_batches
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            """
            INSERT INTO buffered_batches (session_id, sequence_from, sequence_to, payload_json)
            VALUES ('ses_cli_wifi_44040', 1, 1, '{"test": 1}')
            """
        )
        await db.execute(
            """
            INSERT INTO buffered_batches (session_id, sequence_from, sequence_to, payload_json)
            VALUES ('ses_valid_12345', 1, 1, '{"test": 2}')
            """
        )
        await db.commit()

    assert await queue.count() == 2

    # 3. Call init_queue again (simulating app startup / migration)
    await queue.init_queue()

    # 4. Legacy session should be quarantined to dead_letter_batches, leaving only valid batch
    assert await queue.count() == 1
    assert await queue.dead_letter_count() == 1

    batches = await queue.peek_batches(limit=10)
    assert len(batches) == 1
    assert batches[0]["session_id"] == "ses_valid_12345"


@pytest.mark.asyncio
async def test_uploader_dead_letter_quarantine_on_404():
    uploader = BatchUploader()
    test_batch = {
        "schema_version": "1.0",
        "session_id": "ses_non_existent_99999",
        "collector_id": "col_test",
        "source_type": "collector",
        "sequence_from": 1,
        "sequence_to": 1,
        "measurements": [],
    }

    # Mock client returning 404
    class Mock404Response:
        status_code = 404
        text = '{"detail": "Session ses_non_existent_99999 not found"}'

    class MockClient:
        is_closed = False
        async def post(self, url, json):
            return Mock404Response()

    uploader._client = MockClient()

    # Send batch with non-existent session
    success = await uploader.send_batch("ses_non_existent_99999", test_batch)
    assert success is False
