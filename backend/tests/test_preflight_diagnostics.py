import pytest
import uuid
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_preflight_diagnostics_flow():
    """Verify DIAG-01 preflight checks across layers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = f"col_diag_{uuid.uuid4().hex[:6]}"

        # 1. Register collector
        res_reg = await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "Diagnostic Test Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {
                    "supported_modes": ["wifi", "bluetooth"],
                    "adapters": [],
                    "platform": "windows",
                },
            },
        )
        assert res_reg.status_code == 200

        # 2. Run preflight diagnostics
        res = await client.post(f"/api/v1/collectors/{col_id}/preflight?mode=wifi")
        assert res.status_code == 200
        data = res.json()
        assert data["collector_id"] == col_id
        assert data["overall_status"] in ("READY", "DEGRADED", "BLOCKED")
        assert len(data["checks"]) >= 2

        layers = [c["layer"] for c in data["checks"]]
        assert "collector" in layers
        assert "storage_stream" in layers
