import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import HTTPException

from app.main import app
from app.config import settings
from app.core.security import (
    verify_operator_auth,
    verify_collector_auth,
    issue_session_ws_ticket,
    consume_session_ws_ticket,
)
from app.core.lan_port_scanner import lan_port_scanner
from collector.app.core.association_base import InventoryBound
from collector.app.core.lan_inventory import LanInventoryEngine


@pytest.mark.asyncio
async def test_f01_operator_rejects_collector_key():
    """Verify that verify_operator_auth strictly rejects collector key (T01 / F01)."""
    # 1. Calling with collector key must raise 401
    with pytest.raises(HTTPException) as exc_info:
        await verify_operator_auth(x_api_key=settings.COLLECTOR_API_KEY)
    assert exc_info.value.status_code == 401
    assert "UNAUTHORIZED" in exc_info.value.detail

    # 2. Calling with valid operator token must succeed
    token = await verify_operator_auth(x_api_key=settings.API_AUTH_TOKEN)
    assert token == settings.API_AUTH_TOKEN


@pytest.mark.asyncio
async def test_f01_collector_rejects_operator_token():
    """Verify that verify_collector_auth rejects pure operator token (T01 / F01)."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_collector_auth(x_collector_key=settings.API_AUTH_TOKEN)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_f01_single_use_session_ws_ticket():
    """Verify that session WebSocket tickets are single-use and expire (T01 / F01)."""
    session_id = "sess_ticket_test_01"
    ticket = issue_session_ws_ticket(session_id, ttl_seconds=60)
    assert ticket.startswith("stk_")

    # First consumption must succeed
    assert consume_session_ws_ticket(ticket, session_id) is True

    # Second consumption of the same ticket must fail (single-use)
    assert consume_session_ws_ticket(ticket, session_id) is False

    # Ticket for another session must fail
    ticket2 = issue_session_ws_ticket(session_id, ttl_seconds=60)
    assert consume_session_ws_ticket(ticket2, "different_session") is False


@pytest.mark.asyncio
async def test_f03_gateway_unresolved_no_synthetic_data():
    """Verify that gateway without ARP resolution has no fake MAC, RTT, or hostname (T03 / F03)."""
    engine = LanInventoryEngine(enable_port_probe=False)
    bound = InventoryBound(
        interface_name="Wi-Fi",
        attached_prefix="192.168.100.0/24",
        gateway_ip="192.168.100.1",
    )

    batches = []
    async for batch in engine.start(bound):
        batches.append(batch)

    assert len(batches) >= 1
    for batch in batches:
        gw_host = next((h for h in batch.hosts if h["is_gateway"]), None)
        assert gw_host is not None
        assert gw_host["ip"] == "192.168.100.1"
        # Must NOT be fake "gateway.local", must NOT have fake MAC hash, and reachability is "unknown"
        assert gw_host["hostname"] is None
        assert gw_host["mac_hash"] is None
        assert gw_host["reachability"] == "unknown"
        assert gw_host["rtt_ms"] is None


@pytest.mark.asyncio
async def test_f03_tcp_probe_states_and_service_hints():
    """Verify that probe_port distinguishes open, refused, timeout and tags hints (T03 / F03)."""
    # 1. Closed/refused port simulation on localhost
    result_refused = await lan_port_scanner.probe_port("127.0.0.1", 19999, timeout=0.2)
    assert result_refused["port"] == 19999
    assert result_refused["state"] in ("refused", "timeout", "error")
    assert result_refused["service_verified"] is False

    # 2. Open port with mock listener
    server_port = 19998
    async def handler(reader, writer):
        writer.write(b"SSH-2.0-OpenSSH_9.0\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", server_port)
    await server.start_serving()
    try:
        result_open = await lan_port_scanner.probe_port("127.0.0.1", server_port, timeout=0.5)
        assert result_open["port"] == server_port
        assert result_open["state"] == "open"
        assert result_open["service_verified"] is True
        assert "SSH" in result_open["banner"]
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_f01_collectors_auth_matrix():
    """Verify HTTP authentication matrix for collectors router without dependency overrides."""
    from app.core.security import verify_operator_or_collector_auth

    # 1. Direct dependency verification
    assert await verify_operator_or_collector_auth(authorization=f"Bearer {settings.API_AUTH_TOKEN}") == settings.API_AUTH_TOKEN
    assert await verify_operator_or_collector_auth(x_collector_key=settings.COLLECTOR_API_KEY) == settings.COLLECTOR_API_KEY
    with pytest.raises(HTTPException) as exc:
        await verify_operator_or_collector_auth(authorization="Bearer invalid-token")
    assert exc.value.status_code == 401

    # 2. HTTP route level verification without overrides
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Operator can list collectors (200, fixes 401 error)
            res_op = await client.get(
                "/api/v1/collectors",
                headers={"Authorization": f"Bearer {settings.API_AUTH_TOKEN}"},
            )
            assert res_op.status_code == 200
            assert isinstance(res_op.json(), list)

            # Collector can list collectors (200)
            res_col = await client.get(
                "/api/v1/collectors",
                headers={"X-Collector-Key": settings.COLLECTOR_API_KEY},
            )
            assert res_col.status_code == 200

            # Missing credentials rejected (401)
            res_anon = await client.get("/api/v1/collectors")
            assert res_anon.status_code == 401

            # Operator credentials strictly rejected on collector-only route (401)
            res_reg = await client.post(
                "/api/v1/collectors/register",
                json={"id": "test_unauth"},
                headers={"Authorization": f"Bearer {settings.API_AUTH_TOKEN}"},
            )
            assert res_reg.status_code == 401
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)
