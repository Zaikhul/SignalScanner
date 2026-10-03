import os
import pytest
from collector.app.core.buffer_queue import OfflineBufferQueue


@pytest.mark.asyncio
async def test_buffer_queue_fifo(tmp_path):
    db_file = str(tmp_path / "test_buffer.db")
    queue = OfflineBufferQueue(db_path=db_file)
    await queue.init_queue()

    # Push 3 batches
    b1 = {"sequence_from": 1, "sequence_to": 1, "data": "batch_1"}
    b2 = {"sequence_from": 2, "sequence_to": 2, "data": "batch_2"}
    b3 = {"sequence_from": 3, "sequence_to": 3, "data": "batch_3"}

    await queue.push_batch("ses_01", b1)
    await queue.push_batch("ses_01", b2)
    await queue.push_batch("ses_01", b3)

    assert await queue.count() == 3

    # Peek first 2
    peeked = await queue.peek_batches(limit=2)
    assert len(peeked) == 2
    assert peeked[0]["batch"]["data"] == "batch_1"
    assert peeked[1]["batch"]["data"] == "batch_2"

    # Remove first item
    await queue.remove_batch(peeked[0]["db_id"])
    assert await queue.count() == 2

    # Remaining first item should now be batch_2
    remaining = await queue.peek_batches(limit=10)
    assert len(remaining) == 2
    assert remaining[0]["batch"]["data"] == "batch_2"
    assert remaining[1]["batch"]["data"] == "batch_3"
