import asyncio
import logging
from typing import Any, Dict, Optional
import httpx
from collector.app.config import collector_settings
from collector.app.core.buffer_queue import buffer_queue

logger = logging.getLogger("collector.uploader")

MAX_RETRIES = 5


class BatchUploader:
    def __init__(self, backend_url: Optional[str] = None):
        self.backend_url = backend_url or collector_settings.BACKEND_URL
        self._is_online = True
        self._client: Optional[httpx.AsyncClient] = None
        self._drain_lock = asyncio.Lock()

    def set_backend_url(self, backend_url: str) -> None:
        """Dynamically override backend base URL."""
        if self.backend_url != backend_url:
            self.backend_url = backend_url
            if self._client and not self._client.is_closed:
                asyncio.create_task(self._client.aclose())
            self._client = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"X-Collector-Key": collector_settings.COLLECTOR_API_KEY}
            self._client = httpx.AsyncClient(base_url=self.backend_url, timeout=5.0, headers=headers)
        return self._client

    async def send_batch(self, session_id: str, batch: Dict[str, Any]) -> bool:
        """
        Attempts to send batch immediately.
        - Transient network / 5xx / 408 / 429 errors: buffered to SQLite for retry.
        - Permanent 4xx errors (e.g. 404 session not found): quarantined to dead_letter_batches.
        - 200 OK: triggers offline buffer drainage.
        """
        client = await self.get_client()
        try:
            res = await client.post("/api/v1/collector-ingest/batches", json=batch)
            if res.status_code == 200:
                self._is_online = True
                # Trigger drain in background
                asyncio.create_task(self.drain_offline_buffer())
                return True
            elif res.status_code in (408, 429) or res.status_code >= 500:
                # Transient server / rate limit error: buffer for retry
                logger.warning(f"Backend transient error ({res.status_code}), buffering batch to retry queue")
                await buffer_queue.push_batch(session_id, batch, retry_count=0)
                return False
            else:
                # Permanent 4xx client error (e.g. 404 Session Not Found, 400 Mismatch): quarantine
                logger.error(
                    f"Backend rejected batch with permanent error {res.status_code}: {res.text}. Quarantining to dead-letter queue."
                )
                await buffer_queue.push_dead_letter(
                    session_id=session_id,
                    status_code=res.status_code,
                    error_reason=res.text[:500],
                    batch=batch,
                )
                return False
        except Exception as e:
            logger.info(f"Backend unreachable ({e}), buffering batch to offline queue")
            self._is_online = False
            await buffer_queue.push_batch(session_id, batch, retry_count=0)
            return False

    async def drain_offline_buffer(self) -> None:
        """
        Drains buffered batches FIFO to backend with exponential backoff and max retry limit.
        Permanent 4xx errors and batches that exceed MAX_RETRIES are quarantined to DLQ.
        Serialized by _drain_lock to prevent duplicate parallel drain requests.
        """
        if self._drain_lock.locked():
            return

        async with self._drain_lock:
            pending = await buffer_queue.peek_batches(limit=20)
            if not pending:
                return

            client = await self.get_client()
            for item in pending:
                db_id = item["db_id"]
                session_id = item["session_id"]
                current_retries = item.get("retry_count", 0)

                try:
                    res = await client.post("/api/v1/collector-ingest/batches", json=item["batch"])
                    if res.status_code == 200:
                        await buffer_queue.remove_batch(db_id)
                        continue
                    elif res.status_code in (408, 429) or res.status_code >= 500:
                        # Transient error: increment retry count
                        new_retries = await buffer_queue.increment_retry(db_id)
                        if new_retries >= MAX_RETRIES:
                            logger.warning(
                                f"Batch {db_id} exceeded MAX_RETRIES ({new_retries}). Moving to dead-letter queue."
                            )
                            await buffer_queue.remove_batch(db_id)
                            await buffer_queue.push_dead_letter(
                                session_id=session_id,
                                status_code=res.status_code,
                                error_reason=f"EXCEEDED_MAX_RETRIES ({new_retries}): {res.text[:200]}",
                                batch=item["batch"],
                            )
                        # Exponential backoff before stopping drain cycle
                        backoff_sec = min(0.2 * (2 ** min(new_retries, 5)), 5.0)
                        await asyncio.sleep(backoff_sec)
                        break
                    else:
                        # Permanent 4xx error: remove from active retry queue and quarantine
                        logger.warning(
                            f"Drained batch {db_id} rejected with permanent error {res.status_code}. Quarantining to dead-letter."
                        )
                        await buffer_queue.remove_batch(db_id)
                        await buffer_queue.push_dead_letter(
                            session_id=session_id,
                            status_code=res.status_code,
                            error_reason=res.text[:500],
                            batch=item["batch"],
                        )
                        # Continue draining subsequent batches
                        continue
                except Exception as e:
                    # Network unreachable: increment retry count and stop draining
                    new_retries = await buffer_queue.increment_retry(db_id)
                    if new_retries >= MAX_RETRIES:
                        logger.warning(
                            f"Batch {db_id} exceeded MAX_RETRIES on network error ({e}). Moving to dead-letter queue."
                        )
                        await buffer_queue.remove_batch(db_id)
                        await buffer_queue.push_dead_letter(
                            session_id=session_id,
                            status_code=None,
                            error_reason=f"EXCEEDED_MAX_RETRIES ({new_retries}): NetworkError {e}",
                            batch=item["batch"],
                        )
                    break

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


uploader = BatchUploader()
