import os
from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.main import app
from app.config import Settings
from app.core.lan_port_scanner import (
    LanPortScanner,
    validate_lan_target,
)
from app.core.channel_health_engine import ChannelHealthEngine
from app.services.association_service import association_service
from app.schemas.association import AssociationState, IngestAssociationStatusRequest
from app.schemas.common import SessionStatus


def test_ss01_configuration_production_validation():
    """SS-01: In production mode, weak or default secrets must be rejected at startup."""
    # Production with default dev key should fail validation
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="secret",
            TENANT_SALT="strong_salt_1234567890",
            API_AUTH_TOKEN="strong_auth_token_12345",
            LOCAL_AGENT_TOKEN="strong_agent_token_12345",
        )

    # Production with default salt should fail validation
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="strong_secret_key_1234567890",
            TENANT_SALT="salt",
            API_AUTH_TOKEN="strong_auth_token_12345",
            LOCAL_AGENT_TOKEN="strong_agent_token_12345",
        )

    # Valid production settings should pass
    prod_valid = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="strong_secret_key_1234567890",
        TENANT_SALT="strong_tenant_salt_1234567890",
        API_AUTH_TOKEN="strong_auth_token_12345",
        LOCAL_AGENT_TOKEN="strong_agent_token_12345",
        COLLECTOR_API_KEY="strong_collector_key_12345",
    )
    assert prod_valid.ENVIRONMENT == "production"


def test_ss02_lan_scope_strict_validation():
    """SS-02: Target validation must strictly enforce RFC 1918 LAN boundaries."""
    prefix = "192.168.1.0/24"

    # Valid in-scope LAN host
    valid_ip = validate_lan_target("192.168.1.50", attached_prefix=prefix)
    assert str(valid_ip) == "192.168.1.50"

    # Rejection of loopback
    with pytest.raises(ValueError, match="TARGET_LOOPBACK_REJECTED"):
        validate_lan_target("127.0.0.1", attached_prefix=prefix)

    # Rejection of link-local
    with pytest.raises(ValueError, match="TARGET_LINK_LOCAL_REJECTED"):
        validate_lan_target("169.254.1.1", attached_prefix=prefix)

    # Rejection of cloud metadata
    with pytest.raises(ValueError, match="TARGET_FORBIDDEN"):
        validate_lan_target("169.254.169.254", attached_prefix=prefix)

    # Rejection of public WAN IP
    with pytest.raises(ValueError, match="TARGET_OUT_OF_SCOPE"):
        validate_lan_target("8.8.8.8", attached_prefix=prefix)

    # Rejection of out-of-scope RFC 1918 IP
    with pytest.raises(ValueError, match="TARGET_OUT_OF_SUBNET"):
        validate_lan_target("10.0.0.5", attached_prefix=prefix)

    # Rejection of subnet boundary addresses
    with pytest.raises(ValueError, match="TARGET_SUBNET_BOUNDARY"):
        validate_lan_target("192.168.1.0", attached_prefix=prefix)
    with pytest.raises(ValueError, match="TARGET_SUBNET_BOUNDARY"):
        validate_lan_target("192.168.1.255", attached_prefix=prefix)


@pytest.mark.asyncio
async def test_ss03_provenance_separation_rejects_simulated_in_collector_session():
    """SS-03: Measurements with simulated provenance must be rejected for collector sessions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss03_test"
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS03 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
            },
        )

        r_ses = await client.post(
            "/api/v1/sessions",
            json={
                "name": "SS03 Collector Session",
                "mode": "wifi",
                "collector_id": col_id,
                "source_type": "collector",
            },
        )
        assert r_ses.status_code == 201
        session_id = r_ses.json()["id"]
        await client.post(f"/api/v1/sessions/{session_id}/start")

        # Ingesting simulated freshness batch into collector session must be rejected with 400
        sim_batch = {
            "schema_version": "2.0",
            "session_id": session_id,
            "collector_id": col_id,
            "source_type": "collector",
            "sequence_from": 1,
            "sequence_to": 1,
            "measurements": [
                {
                    "schema_version": "2.0",
                    "session_id": session_id,
                    "collector_id": col_id,
                    "sequence": 1,
                    "mode": "wifi",
                    "target_id": "00:11:22:33:44:55",
                    "display_name": "SimulatedAP",
                    "signal": {"value": -55.0, "unit": "dBm"},
                    "quality": {"freshness": "simulated", "rssi_processing": "synthetic"},
                }
            ],
        }
        res_ingest = await client.post("/api/v1/collector-ingest/batches", json=sim_batch)
        assert res_ingest.status_code == 400
        assert "SIMULATED_DATA_REJECTED" in res_ingest.text


@pytest.mark.asyncio
async def test_ss04_collector_active_session_superseding():
    """SS-04: Starting a new session on a collector atomically supersedes older active sessions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss04_test"
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS04 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
            },
        )

        # Create and start session 1
        r_s1 = await client.post(
            "/api/v1/sessions",
            json={"name": "S1", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
        )
        s1_id = r_s1.json()["id"]
        await client.post(f"/api/v1/sessions/{s1_id}/start")

        # Create and start session 2 on the same collector
        r_s2 = await client.post(
            "/api/v1/sessions",
            json={"name": "S2", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
        )
        s2_id = r_s2.json()["id"]
        await client.post(f"/api/v1/sessions/{s2_id}/start")

        # Check session 1 status: must be STOPPED with superseded reason
        r_chk1 = await client.get(f"/api/v1/sessions/{s1_id}")
        assert r_chk1.status_code == 200
        s1_data = r_chk1.json()
        assert s1_data["status"] == "stopped"

        # Check session 2 status: must be ACTIVE
        r_chk2 = await client.get(f"/api/v1/sessions/{s2_id}")
        assert r_chk2.status_code == 200
        assert r_chk2.json()["status"] == "active"


@pytest.mark.asyncio
async def test_ss05_late_batch_does_not_regress_target_live_state():
    """SS-05: Out-of-order late batch updates measurement logs but does not regress live target last_seen or latest_rssi."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss05_test"
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS05 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
            },
        )

        r_ses = await client.post(
            "/api/v1/sessions",
            json={"name": "SS05 Session", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
        )
        s_id = r_ses.json()["id"]
        await client.post(f"/api/v1/sessions/{s_id}/start")

        t2_newer = datetime.now(timezone.utc)
        t1_older = t2_newer - timedelta(seconds=10)

        # 1. Ingest newer measurement first (seq=2, rssi=-45, t2)
        batch2 = {
            "schema_version": "2.0",
            "session_id": s_id,
            "collector_id": col_id,
            "sequence_from": 2,
            "sequence_to": 2,
            "measurements": [
                {
                    "schema_version": "2.0",
                    "session_id": s_id,
                    "collector_id": col_id,
                    "sequence": 2,
                    "captured_at": t2_newer.isoformat(),
                    "mode": "wifi",
                    "target_id": "AA:BB:CC:DD:EE:01",
                    "display_name": "Target-Alpha",
                    "signal": {"value": -45.0, "unit": "dBm"},
                    "quality": {"freshness": "fresh", "rssi_processing": "raw"},
                }
            ],
        }
        r2 = await client.post("/api/v1/collector-ingest/batches", json=batch2)
        assert r2.status_code == 200

        # Check target state
        r_targets = await client.get(f"/api/v1/sessions/{s_id}/targets")
        targets = r_targets.json()
        assert len(targets) == 1
        assert targets[0]["latest_signal"] == -45.0

        # 2. Ingest older measurement arriving late (seq=1, rssi=-85, t1)
        batch1 = {
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
                    "captured_at": t1_older.isoformat(),
                    "mode": "wifi",
                    "target_id": "AA:BB:CC:DD:EE:01",
                    "display_name": "Target-Alpha",
                    "signal": {"value": -85.0, "unit": "dBm"},
                    "quality": {"freshness": "fresh", "rssi_processing": "raw"},
                }
            ],
        }
        r1 = await client.post("/api/v1/collector-ingest/batches", json=batch1)
        assert r1.status_code == 200

        # Verify live target state was NOT regressed to older sample's RSSI (-85.0)
        r_targets_after = await client.get(f"/api/v1/sessions/{s_id}/targets")
        targets_after = r_targets_after.json()
        assert targets_after[0]["latest_signal"] == -45.0

        # Both measurements are persisted
        r_meas = await client.get(f"/api/v1/sessions/{s_id}/measurements")
        assert len(r_meas.json()) == 2


@pytest.mark.asyncio
async def test_ss07_fail_session_endpoint():
    """SS-07: Calling fail session updates session status to FAILED with error detail."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss07_test"
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS07 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
            },
        )

        r_ses = await client.post(
            "/api/v1/sessions",
            json={"name": "SS07 Session", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
        )
        s_id = r_ses.json()["id"]

        r_fail = await client.post(
            f"/api/v1/sessions/{s_id}/fail",
            json={"error_message": "Hardware adapter disconnected during initialization"},
        )
        assert r_fail.status_code == 200
        data = r_fail.json()
        assert data["status"] == "failed"


@pytest.mark.asyncio
async def test_ss08_idempotent_batch_retry_deduplication():
    """SS-08: Batch retransmission must be strictly idempotent and return duplicate counts."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss08_test"
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS08 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
            },
        )

        r_ses = await client.post(
            "/api/v1/sessions",
            json={"name": "SS08 Session", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
        )
        s_id = r_ses.json()["id"]
        await client.post(f"/api/v1/sessions/{s_id}/start")

        batch = {
            "schema_version": "2.0",
            "session_id": s_id,
            "collector_id": col_id,
            "sequence_from": 10,
            "sequence_to": 10,
            "measurements": [
                {
                    "schema_version": "2.0",
                    "session_id": s_id,
                    "collector_id": col_id,
                    "sequence": 10,
                    "mode": "wifi",
                    "target_id": "00:11:22:33:44:99",
                    "display_name": "IdempotentAP",
                    "signal": {"value": -60.0, "unit": "dBm"},
                    "quality": {"freshness": "fresh", "rssi_processing": "raw"},
                }
            ],
        }

        # First post: 1 ingested, 0 duplicates
        res1 = await client.post("/api/v1/collector-ingest/batches", json=batch)
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["ingested_count"] == 1
        assert d1["duplicate_count"] == 0

        # Second post: 0 ingested, 1 duplicate
        res2 = await client.post("/api/v1/collector-ingest/batches", json=batch)
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["ingested_count"] == 0
        assert d2["duplicate_count"] == 1

        # Database measurement count remains 1
        r_meas = await client.get(f"/api/v1/sessions/{s_id}/measurements")
        assert len(r_meas.json()) == 1


@pytest.mark.asyncio
async def test_ss10_association_state_guard_monotonic(db=None):
    """SS-10: Association service must guard CONNECTED state from regressing to ASSOCIATING."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss10_test"
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS10 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
            },
        )

        r_ses = await client.post(
            "/api/v1/sessions",
            json={"name": "SS10 Session", "mode": "wifi", "collector_id": col_id, "source_type": "collector"},
        )
        s_id = r_ses.json()["id"]

        from app.db.session import AsyncSessionLocal
        from app.db.models import WifiAssociationModel

        async with AsyncSessionLocal() as session:
            # Create an association directly in CONNECTED state
            assoc = WifiAssociationModel(
                id="assoc_guard_test_01",
                session_id=s_id,
                collector_id=col_id,
                target_id="00:11:22:33:44:55",
                state=AssociationState.CONNECTED.value,
                ipv4="192.168.1.100",
                prefix="192.168.1.0/24",
            )
            session.add(assoc)
            await session.commit()

            # Late associating update arriving from collector must NOT regress CONNECTED status
            late_update = IngestAssociationStatusRequest(
                state=AssociationState.ASSOCIATING.value,
                prefix="192.168.1.0/24",
            )
            updated = await association_service.update_status_from_collector(
                session, "assoc_guard_test_01", late_update
            )
            assert updated.state == AssociationState.CONNECTED.value

            # Clean up
            await session.delete(assoc)
            await session.commit()


def test_ss11_recommendation_ids_collision_resistant():
    """SS-11: Recommendation IDs must remain unique even with identical timestamps and channels."""
    engine = ChannelHealthEngine()
    session_id = "ses_recommendation_test_123"

    id1 = engine._generate_rec_id(session_id, 6)
    id2 = engine._generate_rec_id(session_id, 6)

    assert id1.startswith("chr_ses_reco_")
    assert id2.startswith("chr_ses_reco_")
    assert id1 != id2


@pytest.mark.asyncio
async def test_ss06_preflight_accurately_reflects_hardware_and_connectivity():
    """SS-06: Preflight diagnostics must reflect actual adapter availability, not assume READY."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss06_test"
        # 1. Register collector with an unavailable wifi adapter
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS06 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {
                    "supported_modes": ["wifi"],
                    "adapters": [
                        {
                            "id": "ad_wifi_01",
                            "type": "wifi",
                            "name": "Hardware WiFi",
                            "is_available": False,  # Hardware disabled or unplugged
                        }
                    ],
                    "platform": "windows",
                },
            },
        )

        res_preflight = await client.post(f"/api/v1/collectors/{col_id}/preflight?mode=wifi")
        assert res_preflight.status_code == 200
        data = res_preflight.json()
        assert data["overall_status"] == "BLOCKED"
        adapter_check = next((c for c in data["checks"] if c["layer"] == "adapter"), None)
        assert adapter_check is not None
        assert adapter_check["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_ss13_spawn_daemon_fails_safe_on_missing_module(monkeypatch):
    """SS-13: spawn-daemon must check collector module file existence before spawning and return 501 if missing."""
    import app.api.v1.collectors as collectors_mod
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        col_id = "col_ss13_test"
        await client.post(
            "/api/v1/collectors/register",
            json={
                "id": col_id,
                "name": "SS13 Collector",
                "platform": "windows",
                "version": "1.0.0",
                "capabilities": {"supported_modes": ["wifi"], "adapters": [], "platform": "windows"},
            },
        )

        # Simulate missing collector file by monkeypatching os.path.isfile
        orig_isfile = os.path.isfile
        monkeypatch.setattr(os.path, "isfile", lambda p: False if "collector" in str(p) else orig_isfile(p))

        res_spawn = await client.post(f"/api/v1/collectors/{col_id}/spawn-daemon?mode=wifi")
        assert res_spawn.status_code == 501
        assert "tidak ditemukan" in res_spawn.text
