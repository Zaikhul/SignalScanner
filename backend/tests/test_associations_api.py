import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.db.session import init_db


@pytest_asyncio.fixture(autouse=True)
async def ensure_db():
    await init_db()


@pytest.mark.asyncio
async def test_association_lifecycle_and_zero_secret_contract():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register collector
        reg_payload = {
            "id": "col_test_assoc_01",
            "name": "Association Test Collector",
            "platform": "windows",
            "version": "1.1.0",
            "capabilities": {
                "supported_modes": ["wifi"],
                "adapters": [
                    {"id": "wlan_01", "type": "wifi", "name": "Native WiFi", "is_available": True}
                ],
                "platform": "windows",
                "version": "1.1.0",
                "can_wifi": True,
                "wifi_associate": True,
                "lan_discovery": True,
            },
        }
        res = await client.post("/api/v1/collectors/register", json=reg_payload)
        assert res.status_code == 200

        # 2. Create scan session
        sess_payload = {
            "name": "Assoc Test Session",
            "mode": "wifi",
            "collector_id": "col_test_assoc_01",
            "source_type": "collector",
        }
        res = await client.post("/api/v1/sessions", json=sess_payload)
        assert res.status_code == 201
        session_id = res.json()["id"]

        # 3. Create draft association
        draft_payload = {
            "target_id": "tgt_ap_office_01",
            "security_hint": "wpa2_personal",
            "ssid": "Office_Guest_WiFi",
            "bssid_hash": "bssid_hash_1234",
        }
        res = await client.post(f"/api/v1/sessions/{session_id}/associations", json=draft_payload)
        assert res.status_code == 201
        assoc_data = res.json()
        assoc_id = assoc_data["id"]
        assert assoc_data["state"] == "idle"
        assert assoc_data["ssid"] == "Office_Guest_WiFi"

        # 4. ZERO-SECRET CONTRACT: Body containing "password" MUST be rejected!
        bad_payload = {
            "target_id": "tgt_ap_office_01",
            "security_hint": "wpa2_personal",
            "authorized_use_confirmed": True,
            "password": "SuperSecretPassword123!",  # FORBIDDEN
        }
        res = await client.post(f"/api/v1/associations/{assoc_id}/connect", json=bad_payload)
        assert res.status_code == 422  # Pydantic validation rejected forbidden key

        # 5. AUTHORIZATION GATE: Must confirm authorized_use_confirmed
        no_auth_payload = {
            "target_id": "tgt_ap_office_01",
            "security_hint": "wpa2_personal",
            "authorized_use_confirmed": False,
        }
        res = await client.post(f"/api/v1/associations/{assoc_id}/connect", json=no_auth_payload)
        assert res.status_code == 400
        assert "AUTHORIZED_USE_REQUIRED" in res.json()["detail"]

        # 6. ENTERPRISE REJECTION: Enterprise networks must be rejected with helpful error
        ent_payload = {
            "target_id": "tgt_ap_office_01",
            "security_hint": "enterprise",
            "authorized_use_confirmed": True,
        }
        res = await client.post(f"/api/v1/associations/{assoc_id}/connect", json=ent_payload)
        assert res.status_code == 400
        assert "WIFI_ENTERPRISE_UNSUPPORTED" in res.json()["detail"]

        # 7. Valid connect request (No secret in payload!)
        connect_payload = {
            "target_id": "tgt_ap_office_01",
            "security_hint": "wpa2_personal",
            "authorized_use_confirmed": True,
            "save_profile": False,
            "timeout_seconds": 30,
        }
        res = await client.post(f"/api/v1/associations/{assoc_id}/connect", json=connect_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "associating"
        assert data["forget_profile_on_exit"] is True

        # Check that command was queued to collector without password
        res = await client.get("/api/v1/collectors/col_test_assoc_01/commands")
        cmds = res.json()
        assoc_cmd = next((c for c in cmds if c["type"] == "associate_wifi"), None)
        assert assoc_cmd is not None
        assert "password" not in str(assoc_cmd)

        # 8. Collector updates status to connected with acquired IP
        status_payload = {
            "state": "connected",
            "ipv4": "192.168.50.105",
            "prefix": "192.168.50.0/24",
            "gateway": "192.168.50.1",
            "dns": ["192.168.50.1", "1.1.1.1"],
            "dhcp_server": "192.168.50.1",
            "captive_state": "internet",
        }
        res = await client.post(f"/api/v1/associations/{assoc_id}/ingest/status", json=status_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "connected"
        assert data["ipv4"] == "192.168.50.105"
        assert data["gateway"] == "192.168.50.1"

        # 9. Ingest LAN hosts (including 1 host inside subnet and 1 illegal outside subnet)
        hosts_payload = {
            "association_id": assoc_id,
            "session_id": session_id,
            "hosts": [
                {
                    "ip": "192.168.50.105",
                    "ip_version": 4,
                    "hostname": "collector-host",
                    "mac_hash": "hash_self_mac",
                    "oui_vendor": "Intel Corp",
                    "discovery_methods": ["interface_snapshot"],
                    "reachability": "up",
                    "rtt_ms": 0.1,
                    "is_self": True,
                    "is_gateway": False,
                },
                {
                    "ip": "192.168.50.1",
                    "ip_version": 4,
                    "hostname": "router.local",
                    "mac_hash": "hash_gateway_mac",
                    "oui_vendor": "Cisco Systems",
                    "discovery_methods": ["gateway_snapshot", "arp_cache"],
                    "reachability": "up",
                    "rtt_ms": 1.2,
                    "is_self": False,
                    "is_gateway": True,
                },
                {
                    "ip": "192.168.50.45",
                    "ip_version": 4,
                    "hostname": "workstation-01",
                    "mac_hash": "hash_host_45",
                    "oui_vendor": "Dell Inc",
                    "discovery_methods": ["arp_cache", "icmp"],
                    "reachability": "up",
                    "rtt_ms": 2.5,
                    "is_self": False,
                    "is_gateway": False,
                },
                {
                    # ILLEGAL TARGET: Outside attached prefix (8.8.8.8) -> must be rejected by validator
                    "ip": "8.8.8.8",
                    "ip_version": 4,
                    "mac_hash": "hash_illegal",
                    "discovery_methods": ["unauthorized_sweep"],
                    "reachability": "up",
                    "is_self": False,
                    "is_gateway": False,
                },
            ],
        }
        res = await client.post(f"/api/v1/associations/{assoc_id}/ingest/hosts", json=hosts_payload)
        assert res.status_code == 200

        # 10. List LAN hosts & verify bound validation excluded 8.8.8.8
        res = await client.get(f"/api/v1/associations/{assoc_id}/hosts")
        assert res.status_code == 200
        host_list = res.json()
        ips = [h["ip"] for h in host_list["items"]]
        assert "192.168.50.105" in ips
        assert "192.168.50.1" in ips
        assert "192.168.50.45" in ips
        assert "8.8.8.8" not in ips  # Bound validator successfully filtered out non-attached IP!

        # 11. Export inventory as JSON
        res = await client.post(f"/api/v1/associations/{assoc_id}/exports?format=json")
        assert res.status_code == 200
        exp_data = res.json()
        assert exp_data["format"] == "json"
        assert exp_data["total_hosts"] == 3
        assert "checksum_sha256" in exp_data
        assert "password" not in exp_data["content"]

        # 12. Export inventory as CSV
        res = await client.post(f"/api/v1/associations/{assoc_id}/exports?format=csv")
        assert res.status_code == 200
        exp_csv = res.json()
        assert exp_csv["format"] == "csv"
        assert "192.168.50.1" in exp_csv["content"]

        # 13. Disconnect
        res = await client.post(f"/api/v1/associations/{assoc_id}/disconnect", json={"forget_profile": True})
        assert res.status_code == 200
        assert res.json()["state"] == "disconnecting"
