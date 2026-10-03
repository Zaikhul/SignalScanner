import io
import pytest
import uuid
import zipfile
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_evidence_bundle_zip_and_audit():
    """Verify EVID-01 evidence bundle ZIP export and checksum verification."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = f"col_evid_{uuid.uuid4().hex[:6]}"

        # 1. Register & Create session
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "Evidence Test Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "platform": "windows"},
            },
        )

        res_create = await client.post(
            "/api/v1/sessions",
            json={
                "name": "Evidence Bundle Test",
                "mode": "wifi",
                "collector_id": col_id,
                "source_type": "collector",
                "sample_interval_ms": 500,
                "tags": ["evidence", "bundle"],
            },
        )
        session_id = res_create.json()["id"]
        await client.post(f"/api/v1/sessions/{session_id}/start")
        await client.post(f"/api/v1/sessions/{session_id}/stop")

        # 2. Download evidence bundle
        res_evid = await client.get(f"/api/v1/sessions/{session_id}/evidence-bundle")
        assert res_evid.status_code == 200
        assert res_evid.headers["content-type"] == "application/zip"

        # 3. Inspect ZIP contents
        zip_buf = io.BytesIO(res_evid.content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            file_names = zf.namelist()
            assert "manifest.json" in file_names
            assert "observations.json" in file_names
            assert "channel_metrics.json" in file_names
            assert "checksums.sha256" in file_names

            checksums_txt = zf.read("checksums.sha256").decode("utf-8")
            assert "manifest.json" in checksums_txt
            assert "observations.json" in checksums_txt
