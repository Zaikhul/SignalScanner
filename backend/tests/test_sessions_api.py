import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.db.session import init_db


@pytest.mark.asyncio
async def test_session_lifecycle():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res = await client.get("/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"

        # 2. Register Collector
        col_payload = {
            "id": "col_test_01",
            "name": "Test Collector",
            "platform": "windows",
            "version": "1.0.0",
            "capabilities": {
                "supported_modes": ["wifi", "bluetooth", "radio"],
                "adapters": [
                    {
                        "id": "adap_wifi_01",
                        "type": "wifi",
                        "name": "Intel Wi-Fi 6 AX200",
                        "capabilities": {"bands": ["2.4GHz", "5GHz"]},
                        "is_available": True
                    }
                ],
                "platform": "windows",
                "version": "1.0.0",
                "can_wifi": True,
                "can_ble": True,
                "can_sdr": False
            }
        }
        res_col = await client.post("/api/v1/collectors/register", json=col_payload)
        assert res_col.status_code == 200
        assert res_col.json()["id"] == "col_test_01"

        # 3. Create Session
        ses_payload = {
            "name": "Lab WiFi Survey",
            "mode": "wifi",
            "collector_id": "col_test_01",
            "sample_interval_ms": 500,
            "tags": ["office", "test"]
        }
        res_ses = await client.post("/api/v1/sessions", json=ses_payload)
        assert res_ses.status_code == 201
        session_id = res_ses.json()["id"]
        assert res_ses.json()["status"] == "draft"

        # 4. Start Session
        res_start = await client.post(f"/api/v1/sessions/{session_id}/start")
        assert res_start.status_code == 200
        assert res_start.json()["status"] == "active"

        # 5. Ingest a measurement batch
        batch_payload = {
            "schema_version": "1.0",
            "session_id": session_id,
            "collector_id": "col_test_01",
            "sequence_from": 1,
            "sequence_to": 2,
            "measurements": [
                {
                    "schema_version": "1.0",
                    "session_id": session_id,
                    "collector_id": "col_test_01",
                    "sequence": 1,
                    "mode": "wifi",
                    "target_id": "aa:bb:cc:11:22:33",
                    "display_name": "Lab_Network_5G",
                    "signal": {
                        "value": -58.0,
                        "unit": "dBm",
                        "noise": -92.0
                    },
                    "radio": {
                        "frequency_hz": 5180000000,
                        "channel": 36,
                        "band": "5GHz"
                    }
                }
            ]
        }
        res_ingest = await client.post("/api/v1/collector-ingest/batches", json=batch_payload)
        assert res_ingest.status_code == 200

        # 6. Add Marker
        res_marker = await client.post(
            f"/api/v1/sessions/{session_id}/markers",
            json={"label": "Moved to Meeting Room", "notes": "Checking signal attenuation"}
        )
        assert res_marker.status_code == 200
        assert res_marker.json()["label"] == "Moved to Meeting Room"

        # 7. Check Targets
        res_targets = await client.get(f"/api/v1/sessions/{session_id}/targets")
        assert res_targets.status_code == 200
        targets = res_targets.json()
        assert len(targets) == 1
        assert targets[0]["display_name"] == "Lab_Network_5G"
        assert targets[0]["target_id"].startswith("hmac:")

        # 8. Pause and Resume Session
        res_pause = await client.post(f"/api/v1/sessions/{session_id}/pause")
        assert res_pause.status_code == 200
        assert res_pause.json()["status"] == "paused"

        res_resume = await client.post(f"/api/v1/sessions/{session_id}/resume")
        assert res_resume.status_code == 200
        assert res_resume.json()["status"] == "active"

        # 9. Stop Session
        res_stop = await client.post(f"/api/v1/sessions/{session_id}/stop")
        assert res_stop.status_code == 200
        assert res_stop.json()["status"] == "completed"

        # 10. Generate Export
        res_exp = await client.post(
            f"/api/v1/sessions/{session_id}/exports",
            json={"format": "json", "include_raw_samples": True}
        )
        assert res_exp.status_code == 200
        exp_id = res_exp.json()["id"]

        # 11. Download Export
        res_down = await client.get(f"/api/v1/exports/{exp_id}/download")
        assert res_down.status_code == 200
        assert "Lab_Network_5G" in res_down.text
