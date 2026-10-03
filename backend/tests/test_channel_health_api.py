import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.db.session import init_db


@pytest.mark.asyncio
async def test_channel_health_api_full_flow():
    """Test full Channel Health and Recommendation API lifecycle (FR-CHH-01 to FR-CHH-10)."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a test collector
        col_payload = {
            "id": "col_chh_test",
            "name": "Channel Health Test Collector",
            "platform": "windows",
            "version": "1.2.0",
            "capabilities": {
                "supported_modes": ["wifi"],
                "adapters": [{"id": "ad_01", "type": "wifi", "name": "WiFi 6 AX200", "capabilities": {}, "is_available": True}],
                "platform": "windows",
                "version": "1.2.0",
                "can_wifi": True,
                "can_ble": False,
                "can_sdr": False,
            },
        }
        r_col = await client.post("/api/v1/collectors/register", json=col_payload)
        assert r_col.status_code == 200

        # 2. Create a scan session
        ses_payload = {
            "name": "Channel Health Test Session",
            "mode": "wifi",
            "collector_id": "col_chh_test",
            "sample_interval_ms": 500,
            "tags": ["channel_health_test"],
        }
        r_ses = await client.post("/api/v1/sessions", json=ses_payload)
        assert r_ses.status_code == 201
        session_id = r_ses.json()["id"]

        # 3. Start session
        r_start = await client.post(f"/api/v1/sessions/{session_id}/start")
        assert r_start.status_code == 200

        # 4. Ingest sample batch of WiFi APs
        batch_payload = {
            "schema_version": "1.0",
            "session_id": session_id,
            "collector_id": "col_chh_test",
            "source_type": "collector",
            "sequence_from": 1,
            "sequence_to": 2,
            "measurements": [
                {
                    "schema_version": "1.0",
                    "session_id": session_id,
                    "collector_id": "col_chh_test",
                    "sequence": 1,
                    "captured_at": "2026-09-07T12:00:00Z",
                    "mode": "wifi",
                    "target_id": "00:11:22:33:44:01",
                    "display_name": "Crowded_AP_1",
                    "signal": {"value": -48.0, "unit": "dBm"},
                    "radio": {"frequency_hz": 2412000000, "channel": 1, "band": "2.4GHz"},
                    "quality": {"calibrated": True, "permission_limited": False, "throttled": False},
                },
                {
                    "schema_version": "1.0",
                    "session_id": session_id,
                    "collector_id": "col_chh_test",
                    "sequence": 2,
                    "captured_at": "2026-09-07T12:00:01Z",
                    "mode": "wifi",
                    "target_id": "00:11:22:33:44:06",
                    "display_name": "Quiet_AP_6",
                    "signal": {"value": -82.0, "unit": "dBm"},
                    "radio": {"frequency_hz": 2437000000, "channel": 6, "band": "2.4GHz"},
                    "quality": {"calibrated": True, "permission_limited": False, "throttled": False},
                },
            ],
        }
        r_ingest = await client.post("/api/v1/collector-ingest/batches", json=batch_payload)
        assert r_ingest.status_code == 200

        # 5. Evaluate Channel Health & Recommendation
        eval_payload = {
            "band": "2.4GHz",
            "channel_width_mhz": 20,
            "observation_window_sec": 300,
            "regulatory_domain": "ID",
        }
        r_eval = await client.post(
            f"/api/v1/sessions/{session_id}/channel-recommendations/evaluate",
            json=eval_payload,
        )
        assert r_eval.status_code == 200
        rec_data = r_eval.json()
        assert rec_data["schema_version"] == "1.2"
        assert "recommendation_id" in rec_data
        assert "primary" in rec_data
        assert rec_data["primary"]["channel"] in [1, 6, 11]
        assert len(rec_data["supporting_factors"]) > 0
        rec_id = rec_data["recommendation_id"]

        # 6. Fetch GET /sessions/{id}/channel-health
        r_health = await client.get(f"/api/v1/sessions/{session_id}/channel-health?band=2.4GHz")
        assert r_health.status_code == 200
        health_data = r_health.json()
        assert health_data["schema_version"] == "1.2"
        assert len(health_data["channels"]) >= 11

        # 7. Fetch GET /sessions/{id}/channel-recommendations/latest
        r_latest = await client.get(f"/api/v1/sessions/{session_id}/channel-recommendations/latest")
        assert r_latest.status_code == 200
        assert r_latest.json()["recommendation_id"] == rec_id

        # 8. Fetch GET /channel-recommendations/{id}
        r_single = await client.get(f"/api/v1/channel-recommendations/{rec_id}")
        assert r_single.status_code == 200
        assert r_single.json()["recommendation_id"] == rec_id

        # 9. Create a Session Marker
        r_marker = await client.post(
            f"/api/v1/sessions/{session_id}/markers",
            json={"label": "Pindah kanal AP ke 6", "notes": "Pengujian perubahan kanal"},
        )
        assert r_marker.status_code == 200
        marker_id = r_marker.json()["id"]

        # 10. Run Channel Validation (Before-After Comparison)
        val_payload = {
            "marker_id": marker_id,
            "before_window_sec": 60,
            "after_window_sec": 60,
        }
        r_val = await client.post(
            f"/api/v1/sessions/{session_id}/channel-validations",
            json=val_payload,
        )
        assert r_val.status_code == 200
        val_data = r_val.json()
        assert "validation_id" in val_data
        assert "teramati" in val_data["summary_label"]
        assert "mean_signal_rssi" in val_data["metric_deltas"]

        # 11. List validation runs
        r_val_list = await client.get(f"/api/v1/sessions/{session_id}/channel-validations")
        assert r_val_list.status_code == 200
        assert len(r_val_list.json()) >= 1
