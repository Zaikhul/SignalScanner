import pytest
from collector.app.core.association_base import InventoryBound
from collector.app.adapters.mock_associate_adapter import MockLanInventoryAdapter
from collector.app.core.lan_inventory import LanInventoryEngine, lookup_oui


def test_oui_lookup():
    assert lookup_oui("00:1f:3b:aa:bb:cc") == "Intel Corp"
    assert lookup_oui("c0:06:c3:12:34:56") == "Cisco Systems"
    assert lookup_oui("24:0a:c4:00:11:22") == "Espressif Systems"
    assert lookup_oui("ff:ee:dd:11:22:33") == "Unknown Manufacturer"


@pytest.mark.asyncio
async def test_mock_lan_inventory_generates_hosts_within_prefix():
    adapter = MockLanInventoryAdapter()
    bound = InventoryBound(
        interface_name="Wi-Fi",
        attached_prefix="192.168.10.0/24",
        gateway_ip="192.168.10.1",
    )

    batches = []
    async for batch in adapter.start(bound):
        batches.append(batch)

    assert len(batches) == 1
    hosts = batches[0].hosts
    assert len(hosts) == 5

    # Check self host
    self_host = next((h for h in hosts if h["is_self"]), None)
    assert self_host is not None
    assert self_host["ip"] == "192.168.10.45"
    assert self_host["oui_vendor"] == "Intel Corp"

    # Check gateway host
    gw_host = next((h for h in hosts if h["is_gateway"]), None)
    assert gw_host is not None
    assert gw_host["ip"] == "192.168.10.1"
    assert gw_host["oui_vendor"] == "Cisco Systems"

    # Verify MAC is pseudonymized (starts with "hmac:" or is a hash string)
    for h in hosts:
        assert h["mac_hash"]
        assert len(h["mac_hash"]) > 8
        assert "pass" not in h
        assert "secret" not in h


@pytest.mark.asyncio
async def test_lan_inventory_engine_prefix_bound_enforcement():
    engine = LanInventoryEngine()

    # Prefix wider than /16 must be rejected with 0 batches
    wide_bound = InventoryBound(
        interface_name="Wi-Fi",
        attached_prefix="10.0.0.0/8",  # /8 is wider than /16
        gateway_ip="10.0.0.1",
    )

    batches = []
    async for batch in engine.start(wide_bound):
        batches.append(batch)

    assert len(batches) == 0  # Successfully rejected!
