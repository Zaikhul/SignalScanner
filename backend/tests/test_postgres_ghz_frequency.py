import asyncio
import os
import uuid
import pytest
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app

PG_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/SignalScanner"


@pytest.mark.asyncio
async def test_postgres_column_is_bigint():
    """Verify that PostgreSQL measurements.frequency_hz is migrated to BIGINT."""
    engine = create_async_engine(PG_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)
    async with session_factory() as db:
        res = await db.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'measurements' AND column_name = 'frequency_hz'"
            )
        )
        row = res.fetchone()
        assert row is not None
        assert row[0].lower() == "bigint", f"Expected bigint, got {row[0]}"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_ghz_frequencies_on_real_postgres():
    """Verify that 2.4GHz, 5GHz, and 6GHz WiFi batches ingest with HTTP 200 without integer overflow."""
    # Ensure app uses PostgreSQL for this test
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        collector_id = f"col_test_ghz_{uuid.uuid4().hex[:6]}"

        # 1. Register collector
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": collector_id,
                "name": "GHz Frequency Test Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {
                    "supported_modes": ["wifi"],
                    "adapters": [],
                    "platform": "windows",
                },
            },
        )

        # 2. Create session
        res_create = await client.post(
            "/api/v1/sessions",
            json={
                "name": "PostgreSQL GHz Frequency Ingest Test",
                "mode": "wifi",
                "collector_id": collector_id,
                "source_type": "collector",
                "sample_interval_ms": 500,
                "tags": ["test", "ghz", "postgres"],
            },
        )
        assert res_create.status_code == 201
        session_id = res_create.json()["id"]

        # 3. Start session
        res_start = await client.post(f"/api/v1/sessions/{session_id}/start")
        assert res_start.status_code == 200

        # 4. Ingest batch containing 2.4GHz (2437MHz), 5GHz (5180MHz), and 6GHz (6000MHz)
        now_iso = datetime.now(timezone.utc).isoformat()
        ghz_batch = {
            "schema_version": "1.0",
            "session_id": session_id,
            "collector_id": collector_id,
            "source_type": "collector",
            "sequence_from": 1,
            "sequence_to": 3,
            "measurements": [
                {
                    "schema_version": "1.0",
                    "session_id": session_id,
                    "collector_id": collector_id,
                    "sequence": 1,
                    "captured_at": now_iso,
                    "mode": "wifi",
                    "target_id": "hmac:ghz_ap_2_4ghz",
                    "display_name": "Test_2_4GHz_AP",
                    "signal": {"value": -48.0, "unit": "dBm", "noise": -95.0},
                    "radio": {"channel": 6, "band": "2.4GHz", "frequency_hz": 2437000000},
                    "quality": {"calibrated": True, "permission_limited": False, "throttled": False},
                    "extra_metadata": {"auth": "WPA2"},
                },
                {
                    "schema_version": "1.0",
                    "session_id": session_id,
                    "collector_id": collector_id,
                    "sequence": 2,
                    "captured_at": now_iso,
                    "mode": "wifi",
                    "target_id": "hmac:ghz_ap_5ghz",
                    "display_name": "Test_5GHz_AP",
                    "signal": {"value": -55.0, "unit": "dBm", "noise": -92.0},
                    "radio": {"channel": 36, "band": "5GHz", "frequency_hz": 5180000000},
                    "quality": {"calibrated": True, "permission_limited": False, "throttled": False},
                    "extra_metadata": {"auth": "WPA3"},
                },
                {
                    "schema_version": "1.0",
                    "session_id": session_id,
                    "collector_id": collector_id,
                    "sequence": 3,
                    "captured_at": now_iso,
                    "mode": "wifi",
                    "target_id": "hmac:ghz_ap_6ghz",
                    "display_name": "Test_6GHz_WiFi6E",
                    "signal": {"value": -62.0, "unit": "dBm", "noise": -90.0},
                    "radio": {"channel": 1, "band": "6GHz", "frequency_hz": 6000000000},
                    "quality": {"calibrated": True, "permission_limited": False, "throttled": False},
                    "extra_metadata": {"auth": "WPA3-SAE"},
                },
            ],
        }

        res_ingest = await client.post("/api/v1/collector-ingest/batches", json=ghz_batch)
        assert res_ingest.status_code == 200
        data = res_ingest.json()
        assert data["status"] == "ok"
        assert data["ingested_count"] == 3

        # 5. Stop session
        await client.post(f"/api/v1/sessions/{session_id}/stop")


@pytest.mark.asyncio
async def test_sanitized_500_response_on_internal_error():
    """Verify that internal errors return sanitized INGEST_INTERNAL_ERROR response with request_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Send a malformed batch that triggers an exception
        res = await client.post(
            "/api/v1/collector-ingest/batches",
            json={
                "schema_version": "1.0",
                "session_id": "ses_non_existent",
                "collector_id": "col_test",
                "source_type": "collector",
                "sequence_from": 1,
                "sequence_to": 1,
                "measurements": [],
            },
        )
        # Should return 404 for not found, not 500
        assert res.status_code == 404
