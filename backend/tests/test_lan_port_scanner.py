import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.db.session import init_db
from app.core.lan_port_scanner import (
    validate_lan_target,
    lan_port_scanner,
    DEFAULT_LAN_PORTS,
    PORT_SERVICE_MAP,
)



def test_validate_lan_target_rfc1918_and_prefix():
    # 1. Valid RFC1918 inside prefix
    assert validate_lan_target("192.168.1.50", "192.168.1.0/24")
    assert validate_lan_target("10.0.1.5", "10.0.0.0/16")
    assert validate_lan_target("172.16.5.10", "172.16.0.0/16")

    # 2. Public IP rejection
    with pytest.raises(ValueError, match="TARGET_OUT_OF_SCOPE"):
        validate_lan_target("8.8.8.8", "8.8.8.0/24")

    with pytest.raises(ValueError, match="TARGET_OUT_OF_SCOPE"):
        validate_lan_target("1.1.1.1", "1.1.1.0/24")

    with pytest.raises(ValueError, match="TARGET_OUT_OF_SCOPE"):
        validate_lan_target("142.250.190.46", "142.250.0.0/16")

    # 3. Cloud metadata rejection
    with pytest.raises(ValueError, match="TARGET_FORBIDDEN"):
        validate_lan_target("169.254.169.254", "169.254.0.0/16")

    # 4. Target outside attached prefix
    with pytest.raises(ValueError, match="TARGET_OUT_OF_SUBNET"):
        validate_lan_target("10.1.2.3", "192.168.1.0/24")

    with pytest.raises(ValueError, match="TARGET_OUT_OF_SUBNET"):
        validate_lan_target("192.168.2.1", "192.168.1.0/24")

    # 5. Invalid format
    with pytest.raises(ValueError, match="Invalid IP address format"):
        validate_lan_target("invalid-ip-address", "192.168.1.0/24")

    # 6. SS-02: Link-local rejection (not RFC 1918)
    with pytest.raises(ValueError, match="TARGET_LINK_LOCAL_REJECTED|TARGET_NOT_RFC1918"):
        validate_lan_target("169.254.1.1", "169.254.0.0/16")

    # 7. SS-02: Loopback rejection by default
    with pytest.raises(ValueError, match="TARGET_LOOPBACK_REJECTED"):
        validate_lan_target("127.0.0.1", "127.0.0.0/8")

    # 8. SS-02: Loopback cannot scan out-of-subnet even if allowed
    with pytest.raises(ValueError, match="TARGET_OUT_OF_SUBNET"):
        validate_lan_target("127.0.0.1", "192.168.1.0/24", allow_loopback=True)

    # 9. SS-02: Malformed or missing prefix must fail safely
    with pytest.raises(ValueError, match="INVALID_ATTACHED_PREFIX"):
        validate_lan_target("192.168.1.5", "invalid-prefix")


@pytest.mark.asyncio
async def test_scan_host_ports_with_mock_server():
    # Start a mock TCP listener on 127.0.0.1 to simulate an open service
    server_port = 18883
    connected_clients = []

    async def handle_client(reader, writer):
        connected_clients.append(True)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", server_port)
    await server.start_serving()

    try:
        # Scan with attached prefix matching loopback with explicit allow_loopback=True for test
        results = await lan_port_scanner.scan_host_ports(
            ip="127.0.0.1",
            attached_prefix="127.0.0.0/8",
            ports=[server_port, 18884],  # 18883 is open, 18884 is closed
            timeout=0.3,
            concurrency=2,
            allow_loopback=True,
        )

        assert len(results) == 1
        assert results[0]["port"] == server_port
        assert results[0]["state"] == "open"
        assert results[0]["protocol"] == "tcp"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_api_scan_host_ports_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register collector & session
        col_res = await client.post(
            "/api/v1/collectors/register",
            json={
                "id": "col_port_test_01",
                "name": "Port Test Collector",
                "platform": "windows",
                "version": "1.1.0",
                "capabilities": {
                    "supported_modes": ["wifi"],
                    "adapters": [{"id": "wlan_01", "type": "wifi", "name": "WiFi", "is_available": True}],
                    "platform": "windows",
                    "version": "1.1.0",
                    "can_wifi": True,
                },
            },
        )
        assert col_res.status_code == 200

        sess_res = await client.post(
            "/api/v1/sessions",
            json={
                "name": "Port Scan Test Session",
                "mode": "wifi",
                "collector_id": "col_port_test_01",
                "source_type": "collector",
            },
        )
        assert sess_res.status_code == 201
        session_id = sess_res.json()["id"]

        # Create draft association
        assoc_res = await client.post(
            f"/api/v1/sessions/{session_id}/associations",
            json={
                "target_id": "tgt_ap_port_01",
                "security_hint": "open",
                "ssid": "Test_Network",
            },
        )
        assert assoc_res.status_code == 201
        assoc_id = assoc_res.json()["id"]

        # Ingest connected status with prefix 192.168.10.0/24
        status_res = await client.post(
            f"/api/v1/associations/{assoc_id}/ingest/status",
            json={
                "state": "connected",
                "ipv4": "192.168.10.50",
                "prefix": "192.168.10.0/24",
                "gateway": "192.168.10.1",
            },
        )
        assert status_res.status_code == 200

        # Ingest a valid LAN host
        ingest_hosts_res = await client.post(
            f"/api/v1/associations/{assoc_id}/ingest/hosts",
            json={
                "association_id": assoc_id,
                "session_id": session_id,
                "hosts": [
                    {
                        "ip": "192.168.10.20",
                        "ip_version": 4,
                        "hostname": "local-server",
                        "mac_hash": "hash_server_20",
                        "oui_vendor": "Intel Corp",
                        "discovery_methods": ["arp_cache"],
                        "reachability": "up",
                        "is_self": False,
                        "is_gateway": False,
                    }
                ],
            },
        )
        assert ingest_hosts_res.status_code == 200

        # Attempt to scan an unauthorized out-of-bounds target (8.8.8.8) -> MUST return HTTP 400
        scan_unauthorized = await client.post(
            f"/api/v1/associations/{assoc_id}/hosts/8.8.8.8/scan-ports",
            json={"ports": [80, 443]},
        )
        assert scan_unauthorized.status_code == 400
        assert "TARGET_OUT_OF_SCOPE" in scan_unauthorized.json()["detail"]

        # Attempt to scan host outside attached prefix (10.0.0.1) -> MUST return HTTP 400
        scan_out_of_prefix = await client.post(
            f"/api/v1/associations/{assoc_id}/hosts/10.0.0.1/scan-ports",
            json={"ports": [80, 443]},
        )
        assert scan_out_of_prefix.status_code == 400
        assert "TARGET_OUT_OF_SUBNET" in scan_out_of_prefix.json()["detail"]

        # Attempt to scan non-existent host in inventory -> MUST return HTTP 404
        scan_not_found = await client.post(
            f"/api/v1/associations/{assoc_id}/hosts/192.168.10.99/scan-ports",
            json={"ports": [80, 443]},
        )
        assert scan_not_found.status_code == 404

        # Scan valid registered host (timeout 0.1s to finish quickly)
        scan_valid = await client.post(
            f"/api/v1/associations/{assoc_id}/hosts/192.168.10.20/scan-ports",
            json={"ports": [80, 443], "timeout_seconds": 0.1},
        )
        assert scan_valid.status_code == 200
        host_item = scan_valid.json()
        assert host_item["ip"] == "192.168.10.20"
        assert "open_ports" in host_item
        assert isinstance(host_item["open_ports"], list)
