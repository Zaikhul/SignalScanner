"""
QA Regression Test Suite for Signal Scanner.
Covers verification of fixes for QA_ANALYSIS_REPORT.md findings:
- F-01: API Authentication enforcement (401 without auth, 200 with auth)
- F-06: Measurement Ingest Deduplication
- F-09: MeasurementBatch Strict Schema Validation
- F-12: Session Lifecycle State Machine & Idempotent Stop
- F-14: WiFi Profile XML Escaping
- F-20: SSID Masking Enforcement
- F-22: True Median Signal Calculation
- F-26: ISO 8601 UTC Timestamp Serialization
"""

import math
import uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from pydantic import ValidationError

from app.main import app
from app.config import settings
from app.core.security import verify_operator_auth
from app.schemas.measurement import (
    MeasurementBatch,
    NormalizedMeasurementEvent,
    SignalData,
    QualityFlags,
)
from app.schemas.common import ScanMode
from collector.app.adapters.wifi_associate_windows import WindowsWiFiAssociationAdapter


@pytest.fixture
async def regression_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_f09_measurement_batch_schema_validation():
    """F-09: Verify strict boundary and consistency checks in MeasurementBatch schema."""
    sess_id = "sess_f09_test"
    col_id = "col_f09_test"

    valid_event = NormalizedMeasurementEvent(
        session_id=sess_id,
        collector_id=col_id,
        sequence=1,
        mode=ScanMode.WIFI,
        target_id="00:11:22:33:44:55",
        signal=SignalData(value=-50.0, unit="dBm", noise=-90.0, snr=40.0),
        quality=QualityFlags(calibrated=True),
    )

    # 1. sequence_from > sequence_to must fail
    with pytest.raises(ValidationError) as exc_info:
        MeasurementBatch(
            session_id=sess_id,
            collector_id=col_id,
            sequence_from=10,
            sequence_to=5,
            measurements=[valid_event],
        )
    assert "sequence_to (5) cannot be less than sequence_from (10)" in str(exc_info.value)

    # 2. Mismatching session_id inside measurements must fail
    mismatched_sess_event = valid_event.model_copy(update={"session_id": "sess_different"})
    with pytest.raises(ValidationError) as exc_info:
        MeasurementBatch(
            session_id=sess_id,
            collector_id=col_id,
            sequence_from=1,
            sequence_to=1,
            measurements=[mismatched_sess_event],
        )
    assert "does not match batch session_id" in str(exc_info.value)

    # 3. Mismatching collector_id inside measurements must fail
    mismatched_col_event = valid_event.model_copy(update={"collector_id": "col_different"})
    with pytest.raises(ValidationError) as exc_info:
        MeasurementBatch(
            session_id=sess_id,
            collector_id=col_id,
            sequence_from=1,
            sequence_to=1,
            measurements=[mismatched_col_event],
        )
    assert "does not match batch collector_id" in str(exc_info.value)

    # 4. Out-of-bounds sequence number must fail
    oob_event = valid_event.model_copy(update={"sequence": 99})
    with pytest.raises(ValidationError) as exc_info:
        MeasurementBatch(
            session_id=sess_id,
            collector_id=col_id,
            sequence_from=1,
            sequence_to=10,
            measurements=[oob_event],
        )
    assert "out of batch range" in str(exc_info.value)

    # 5. Non-finite signal values must fail
    nan_signal_event = valid_event.model_copy(update={"signal": SignalData(value=float("nan"), unit="dBm")})
    with pytest.raises(ValidationError) as exc_info:
        MeasurementBatch(
            session_id=sess_id,
            collector_id=col_id,
            sequence_from=1,
            sequence_to=1,
            measurements=[nan_signal_event],
        )
    assert "must be a finite number" in str(exc_info.value)


@pytest.mark.asyncio
async def test_f01_auth_enforcement_when_configured():
    """F-01: Endpoints return 401 when token is missing/invalid if API_AUTH_TOKEN is set."""
    saved_override = app.dependency_overrides.pop(verify_operator_auth, None)
    orig_token = settings.API_AUTH_TOKEN
    settings.API_AUTH_TOKEN = "secret-qa-token"

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Without auth header -> 401
            r_no_auth = await client.get("/api/v1/sessions")
            assert r_no_auth.status_code == 401

            # With wrong token -> 401
            r_wrong = await client.get("/api/v1/sessions", headers={"Authorization": "Bearer wrong-token"})
            assert r_wrong.status_code == 401

            # With correct token -> 200
            r_ok = await client.get("/api/v1/sessions", headers={"Authorization": "Bearer secret-qa-token"})
            assert r_ok.status_code == 200
    finally:
        settings.API_AUTH_TOKEN = orig_token
        if saved_override:
            app.dependency_overrides[verify_operator_auth] = saved_override


@pytest.mark.asyncio
async def test_f12_session_state_machine_and_idempotency(regression_client: AsyncClient):
    """F-12: Invalid transitions raise 409, and stopping an ended session is idempotent (200)."""
    col_id = "col_f12_test"
    await regression_client.post(
        "/api/v1/collectors/register",
        json={
            "id": col_id,
            "name": "State Machine Collector",
            "platform": "windows",
            "version": "1.0.0",
            "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
        },
    )

    # 1. Create session -> status is "draft"
    r_create = await regression_client.post(
        "/api/v1/sessions",
        json={"name": "State Machine Test", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
    )
    assert r_create.status_code == 201
    s_id = r_create.json()["id"]
    assert r_create.json()["status"] == "draft"

    # 2. Resuming a "draft" session is invalid -> 409
    r_bad_resume = await regression_client.post(f"/api/v1/sessions/{s_id}/resume")
    assert r_bad_resume.status_code == 409
    assert "Must be paused" in r_bad_resume.json()["detail"]

    # 3. Start session -> status becomes "active"
    r_start = await regression_client.post(f"/api/v1/sessions/{s_id}/start")
    assert r_start.status_code == 200
    assert r_start.json()["status"] == "active"

    # 4. Stop session -> status becomes "completed"
    r_stop1 = await regression_client.post(f"/api/v1/sessions/{s_id}/stop")
    assert r_stop1.status_code == 200
    assert r_stop1.json()["status"] == "completed"

    # 5. Starting a completed session is invalid -> 409
    r_bad_start = await regression_client.post(f"/api/v1/sessions/{s_id}/start")
    assert r_bad_start.status_code == 409
    assert "Completed sessions cannot be reopened" in r_bad_start.json()["detail"]

    # 6. Stopping an already completed session must be idempotent -> returns 200
    r_stop2 = await regression_client.post(f"/api/v1/sessions/{s_id}/stop")
    assert r_stop2.status_code == 200
    assert r_stop2.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_f06_ingest_deduplication(regression_client: AsyncClient):
    """F-06: Duplicate ingest of same (sequence, target_id) must not duplicate measurements."""
    col_id = "col_dedup_test"
    await regression_client.post(
        "/api/v1/collectors/register",
        json={
            "id": col_id,
            "name": "Dedup Collector",
            "platform": "windows",
            "version": "1.0.0",
            "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
        },
    )

    r_sess = await regression_client.post(
        "/api/v1/sessions",
        json={"name": "Dedup Session", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
    )
    s_id = r_sess.json()["id"]
    await regression_client.post(f"/api/v1/sessions/{s_id}/start")

    # Ingest batch with sequence 1
    batch_payload = {
        "schema_version": "2.0",
        "session_id": s_id,
        "collector_id": col_id,
        "sequence_from": 1,
        "sequence_to": 1,
        "measurements": [
            {
                "schema_version": "2.0",
                "session_id": s_id,
                "collector_id": col_id,
                "sequence": 1,
                "mode": "wifi",
                "target_id": "AA:BB:CC:DD:EE:01",
                "display_name": "TestAP",
                "signal": {"value": -55.0, "unit": "dBm"},
                "quality": {"calibrated": True},
            }
        ],
    }

    r_ingest1 = await regression_client.post("/api/v1/collector-ingest/batches", json=batch_payload)
    assert r_ingest1.status_code == 200

    # Ingest the exact same sequence again (e.g., collector retry on connection blip)
    r_ingest2 = await regression_client.post("/api/v1/collector-ingest/batches", json=batch_payload)
    assert r_ingest2.status_code == 200

    # Query measurements: should only contain 1 record
    r_query = await regression_client.get(f"/api/v1/sessions/{s_id}/measurements")
    assert r_query.status_code == 200
    measurements = r_query.json()
    assert len(measurements) == 1
    assert measurements[0]["sequence"] == 1


@pytest.mark.asyncio
async def test_f20_and_f22_mask_ssid_and_median_signal(regression_client: AsyncClient):
    """F-20: mask_ssid hides raw SSID. F-22: median_signal is true statistical median."""
    col_id = "col_stats_test"
    await regression_client.post(
        "/api/v1/collectors/register",
        json={
            "id": col_id,
            "name": "Stats Collector",
            "platform": "windows",
            "version": "1.0.0",
            "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
        },
    )

    # Session with mask_ssid=True via privacy_config
    r_sess = await regression_client.post(
        "/api/v1/sessions",
        json={
            "name": "Mask & Median Session",
            "mode": "wifi",
            "collector_id": col_id,
            "source_type": "collector",
            "privacy_config": {"mask_ssid": True},
        },
    )
    s_id = r_sess.json()["id"]
    await regression_client.post(f"/api/v1/sessions/{s_id}/start")

    # Ingest 3 measurements for target with varying RSSI: -80, -40, -60
    # True median of [-80, -60, -40] is -60.0
    rssi_values = [-80.0, -40.0, -60.0]
    for seq, rssi in enumerate(rssi_values, start=1):
        batch = {
            "schema_version": "2.0",
            "session_id": s_id,
            "collector_id": col_id,
            "sequence_from": seq,
            "sequence_to": seq,
            "measurements": [
                {
                    "schema_version": "2.0",
                    "session_id": s_id,
                    "collector_id": col_id,
                    "sequence": seq,
                    "mode": "wifi",
                    "target_id": "11:22:33:44:55:66",
                    "display_name": "Corporate-Secret-WiFi",
                    "signal": {"value": rssi, "unit": "dBm"},
                    "quality": {"calibrated": True},
                }
            ],
        }
        r = await regression_client.post("/api/v1/collector-ingest/batches", json=batch)
        assert r.status_code == 200

    # Check targets summary
    r_targets = await regression_client.get(f"/api/v1/sessions/{s_id}/targets")
    assert r_targets.status_code == 200
    targets = r_targets.json()
    assert len(targets) == 1
    t = targets[0]

    # F-20: SSID/display_name must be masked
    assert t["display_name"].startswith("***")
    assert "Secret" not in t["display_name"]

    # F-22: Median signal must be -60.0 (true median of -80, -60, -40)
    assert t["median_signal"] == -60.0

    # Ingest 4th measurement with -50.0: [-80, -60, -50, -40] -> median should be (-60 + -50)/2 = -55.0
    batch4 = {
        "schema_version": "2.0",
        "session_id": s_id,
        "collector_id": col_id,
        "sequence_from": 4,
        "sequence_to": 4,
        "measurements": [
            {
                "schema_version": "2.0",
                "session_id": s_id,
                "collector_id": col_id,
                "sequence": 4,
                "mode": "wifi",
                "target_id": "11:22:33:44:55:66",
                "display_name": "Corporate-Secret-WiFi",
                "signal": {"value": -50.0, "unit": "dBm"},
                "quality": {"calibrated": True},
            }
        ],
    }
    await regression_client.post("/api/v1/collector-ingest/batches", json=batch4)

    r_targets2 = await regression_client.get(f"/api/v1/sessions/{s_id}/targets")
    t2 = r_targets2.json()[0]
    assert t2["median_signal"] == -55.0


@pytest.mark.asyncio
async def test_f26_utc_timestamp_serialization(regression_client: AsyncClient):
    """F-26: Target and session timestamps must include explicit timezone offset (Z or +00:00)."""
    col_id = "col_time_test"
    await regression_client.post(
        "/api/v1/collectors/register",
        json={
            "id": col_id,
            "name": "Time Collector",
            "platform": "windows",
            "version": "1.0.0",
            "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
        },
    )

    r_sess = await regression_client.post(
        "/api/v1/sessions",
        json={"name": "Timestamp Test", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
    )
    assert r_sess.status_code == 201
    s_data = r_sess.json()
    assert s_data["created_at"].endswith("Z") or "+00:00" in s_data["created_at"]


def test_f14_wifi_profile_xml_escaping():
    """F-14: XML special characters in SSID or password must be properly escaped."""
    xml = WindowsWiFiAssociationAdapter._build_profile_xml(
        profile_name="Special & Profile",
        ssid="WiFi <Test> & 'Secure' \"Net\"",
        sec="wpa2",
        password="P@ss<word>&123\"'",
    )
    # Ensure unescaped raw characters are NOT in XML
    assert "<Test>" not in xml
    assert "& 'Secure'" not in xml
    # Ensure escaped entities ARE in XML
    assert "&lt;Test&gt;" in xml
    assert "&amp;" in xml
    assert "&apos;Secure&apos;" in xml
    assert "&quot;Net&quot;" in xml
    assert "P@ss&lt;word&gt;&amp;123&quot;&apos;" in xml
