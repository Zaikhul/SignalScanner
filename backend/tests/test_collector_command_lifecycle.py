import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.schemas.collector import CollectorRegistration, CollectorCapabilities, CollectorHeartbeat
from app.schemas.common import ScanMode, CollectorStatus, SessionStatus
from app.services.collector_service import collector_service


@pytest.mark.asyncio
async def test_collector_command_queue_and_heartbeat_dispatch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        collector_id = "col_test_dispatch_01"

        # 1. Register collector
        reg_payload = {
            "id": collector_id,
            "name": "Command Dispatch Collector",
            "platform": "windows",
            "version": "1.0.0",
            "capabilities": {
                "supported_modes": ["wifi"],
                "adapters": [],
                "platform": "windows",
            },
        }
        res_reg = await ac.post("/api/v1/collectors/register", json=reg_payload)
        assert res_reg.status_code == 200

        # 2. Create a session bound to this collector
        session_payload = {
            "name": "Command Dispatch Session Test",
            "mode": "wifi",
            "collector_id": collector_id,
            "source_type": "collector",
            "sample_interval_ms": 500,
            "tags": ["test"],
        }
        res_ses = await ac.post("/api/v1/sessions", json=session_payload)
        assert res_ses.status_code == 201
        session_id = res_ses.json()["id"]

        # 3. Start session -> Backend should queue start_scan command for the collector
        res_start = await ac.post(f"/api/v1/sessions/{session_id}/start")
        assert res_start.status_code == 200

        # 4. Collector sends heartbeat -> Heartbeat response should contain pending start_scan command
        hb_res = await ac.post(
            "/api/v1/collectors/heartbeat",
            json={"collector_id": collector_id, "status": "ready"},
        )
        assert hb_res.status_code == 200
        hb_data = hb_res.json()
        assert "pending_commands" in hb_data
        cmds = hb_data["pending_commands"]
        assert len(cmds) >= 1
        cmd = cmds[0]
        assert cmd["type"] == "start_scan"
        assert cmd["session_id"] == session_id
        assert cmd["collector_id"] == collector_id

        # 5. Collector acknowledges the command
        cmd_id = cmd["command_id"]
        ack_res = await ac.post(f"/api/v1/collectors/{collector_id}/commands/{cmd_id}/ack")
        assert ack_res.status_code == 200
        assert ack_res.json()["status"] == "acknowledged"

        # 6. Stop session -> Backend should queue stop_scan command
        res_stop = await ac.post(f"/api/v1/sessions/{session_id}/stop")
        assert res_stop.status_code == 200

        # 7. Check pending commands via GET endpoint
        cmd_list_res = await ac.get(f"/api/v1/collectors/{collector_id}/commands")
        assert cmd_list_res.status_code == 200
        stop_cmds = cmd_list_res.json()
        assert any(c["type"] == "stop_scan" and c["session_id"] == session_id for c in stop_cmds)


@pytest.mark.asyncio
async def test_ingest_batch_strict_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        collector_id = "col_test_validation_01"

        # Register collector
        await ac.post(
            "/api/v1/collectors/register",
            json={
                "id": collector_id,
                "name": "Validation Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi", "bluetooth"], "adapters": [], "platform": "windows"},
            },
        )

        # Create session in DRAFT state (not started yet)
        res_ses = await ac.post(
            "/api/v1/sessions",
            json={
                "name": "Draft Ingest Validation Test",
                "mode": "wifi",
                "collector_id": collector_id,
                "source_type": "collector",
            },
        )
        assert res_ses.status_code == 201
        session_id = res_ses.json()["id"]

        valid_measurement = {
            "schema_version": "1.0",
            "session_id": session_id,
            "collector_id": collector_id,
            "sequence": 1,
            "captured_at": "2026-08-25T03:00:00Z",
            "mode": "wifi",
            "target_id": "00:11:22:33:44:55",
            "display_name": "TestAP",
            "signal": {"value": -50.0, "unit": "dBm"},
            "quality": {"calibrated": True, "permission_limited": False, "throttled": False},
        }

        # 1. Ingest into DRAFT session should fail with 400 (SESSION_NOT_ACTIVE)
        res_draft_ingest = await ac.post(
            "/api/v1/collector-ingest/batches",
            json={
                "schema_version": "1.0",
                "session_id": session_id,
                "collector_id": collector_id,
                "source_type": "collector",
                "sequence_from": 1,
                "sequence_to": 1,
                "measurements": [valid_measurement],
            },
        )
        assert res_draft_ingest.status_code == 400
        assert "SESSION_NOT_ACTIVE" in res_draft_ingest.text

        # 2. Start session
        await ac.post(f"/api/v1/sessions/{session_id}/start")

        # 3. Mode mismatch (e.g. bluetooth measurement in wifi session) should fail with 400
        ble_measurement = dict(valid_measurement, mode="bluetooth")
        res_mode_mismatch = await ac.post(
            "/api/v1/collector-ingest/batches",
            json={
                "schema_version": "1.0",
                "session_id": session_id,
                "collector_id": collector_id,
                "source_type": "collector",
                "sequence_from": 1,
                "sequence_to": 1,
                "measurements": [ble_measurement],
            },
        )
        assert res_mode_mismatch.status_code == 400
        assert "MODE_MISMATCH" in res_mode_mismatch.text

        # 4. Valid batch should succeed with 200
        res_valid = await ac.post(
            "/api/v1/collector-ingest/batches",
            json={
                "schema_version": "1.0",
                "session_id": session_id,
                "collector_id": collector_id,
                "source_type": "collector",
                "sequence_from": 1,
                "sequence_to": 1,
                "measurements": [valid_measurement],
            },
        )
        assert res_valid.status_code == 200
        assert res_valid.json()["status"] == "ok"
