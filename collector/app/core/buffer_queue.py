import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import aiosqlite
from collector.app.config import collector_settings


class OfflineBufferQueue:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or collector_settings.BUFFER_DB_PATH

    async def init_queue(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS buffered_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sequence_from INTEGER NOT NULL,
                    sequence_to INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letter_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    status_code INTEGER,
                    error_reason TEXT,
                    payload_json TEXT NOT NULL,
                    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Check if retry_count column exists in buffered_batches
            cursor = await db.execute("PRAGMA table_info(buffered_batches)")
            cols = [row[1] for row in await cursor.fetchall()]
            if "retry_count" not in cols:
                await db.execute("ALTER TABLE buffered_batches ADD COLUMN retry_count INTEGER DEFAULT 0")

            # 1. Auto-quarantine legacy local session IDs (ses_cli_*)
            await db.execute(
                """
                INSERT INTO dead_letter_batches (session_id, status_code, error_reason, payload_json)
                SELECT session_id, 404, 'QUARANTINED_LEGACY_LOCAL_SESSION', payload_json
                FROM buffered_batches WHERE session_id LIKE 'ses_cli_%'
                """
            )
            await db.execute("DELETE FROM buffered_batches WHERE session_id LIKE 'ses_cli_%'")

            # 2. Archive legacy completed session batches (ses_62a41a1c2e08)
            await db.execute(
                """
                INSERT INTO dead_letter_batches (session_id, status_code, error_reason, payload_json)
                SELECT session_id, 400, 'SESSION_ALREADY_COMPLETED_ARCHIVE', payload_json
                FROM buffered_batches WHERE session_id = 'ses_62a41a1c2e08'
                """
            )
            await db.execute("DELETE FROM buffered_batches WHERE session_id = 'ses_62a41a1c2e08'")

            await db.commit()

    async def push_batch(self, session_id: str, batch: Dict[str, Any], retry_count: int = 0) -> int:
        seq_from = batch.get("sequence_from", 0)
        seq_to = batch.get("sequence_to", 0)
        payload = json.dumps(batch)

        async with aiosqlite.connect(self.db_path) as db:
            # Check size limit
            cursor = await db.execute("SELECT COUNT(*) FROM buffered_batches")
            count_row = await cursor.fetchone()
            count = count_row[0] if count_row else 0

            if count >= collector_settings.MAX_BUFFER_RECORDS:
                # Drop oldest batch to prevent disk overflow
                await db.execute(
                    "DELETE FROM buffered_batches WHERE id IN (SELECT id FROM buffered_batches ORDER BY id ASC LIMIT 50)"
                )

            cursor = await db.execute(
                """
                INSERT INTO buffered_batches (session_id, sequence_from, sequence_to, payload_json, retry_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, seq_from, seq_to, payload, retry_count),
            )
            await db.commit()
            return cursor.lastrowid

    async def increment_retry(self, db_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE buffered_batches SET retry_count = retry_count + 1 WHERE id = ?",
                (db_id,),
            )
            cursor = await db.execute("SELECT retry_count FROM buffered_batches WHERE id = ?", (db_id,))
            row = await cursor.fetchone()
            await db.commit()
            return row[0] if row else 1

    async def push_dead_letter(
        self,
        session_id: str,
        status_code: Optional[int],
        error_reason: str,
        batch: Dict[str, Any],
    ) -> int:
        payload = json.dumps(batch)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO dead_letter_batches (session_id, status_code, error_reason, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, status_code, error_reason, payload),
            )
            await db.commit()
            return cursor.lastrowid

    async def peek_batches(self, limit: int = 10) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, session_id, payload_json, retry_count FROM buffered_batches ORDER BY id ASC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "db_id": row["id"],
                    "session_id": row["session_id"],
                    "retry_count": row["retry_count"] if "retry_count" in row.keys() else 0,
                    "batch": json.loads(row["payload_json"]),
                }
                for row in rows
            ]

    async def remove_batch(self, db_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM buffered_batches WHERE id = ?", (db_id,))
            await db.commit()

    async def count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM buffered_batches")
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def dead_letter_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM dead_letter_batches")
            row = await cursor.fetchone()
            return row[0] if row else 0


buffer_queue = OfflineBufferQueue()
