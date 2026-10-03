import pytest
import uuid
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_session_manifest_lifecycle_and_checksum():
    """Verify PROV-01 session manifest creation, checksum computation, and retrieval."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = f"col_prov_{uuid.uuid4().hex[:6]}"
        
        # 1. Register collector
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "Provenance Test Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "platform": "windows"},
            },
        )

        # 2. Create session
        res_create = await client.post(
            "/api/v1/sessions",
            json={
                "name": "Provenance Manifest Test Session",
                "mode": "wifi",
                "collector_id": col_id,
                "source_type": "collector",
                "sample_interval_ms": 500,
                "tags": ["prov01", "manifest"],
            },
        )
        assert res_create.status_code == 201
        session_id = res_create.json()["id"]

        # 3. Start session
        res_start = await client.post(f"/api/v1/sessions/{session_id}/start")
        assert res_start.status_code == 200

        # 4. Stop session (triggers manifest generation & checksumming)
        res_stop = await client.post(f"/api/v1/sessions/{session_id}/stop")
        assert res_stop.status_code == 200

        # 5. Fetch manifest
        res_mnf = await client.get(f"/api/v1/sessions/{session_id}/manifest")
        assert res_mnf.status_code == 200
        manifest = res_mnf.json()
        assert manifest["session_id"] == session_id
        assert manifest["collector_id"] == col_id
        assert "manifest_checksum" in manifest
        assert len(manifest["manifest_checksum"]) == 64  # SHA256 length
        assert manifest["schema_version"] == "measurement@2.0"
        assert manifest["processing_version"] == "signal-pipeline@2.0"
