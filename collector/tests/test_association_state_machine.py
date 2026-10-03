import pytest
import asyncio
from collector.app.core.association_base import AssociateRequest
from collector.app.adapters.mock_associate_adapter import MockAssociationAdapter
from collector.app.core.radio_mutex import RadioMutex


@pytest.mark.asyncio
async def test_association_state_machine_success():
    adapter = MockAssociationAdapter()
    req = AssociateRequest(
        association_id="asc_test_01",
        target_id="tgt_ap_01",
        ssid="Test_Office_WiFi",
        security_type="wpa2_personal",
    )

    events = []
    async for ev in adapter.associate(req, password="ValidPassword123"):
        events.append(ev)

    states = [e.state for e in events]
    assert states == [
        "requesting_permission",
        "associating",
        "authenticating",
        "obtaining_address",
        "connected",
    ]

    last_event = events[-1]
    assert last_event.state == "connected"
    assert last_event.ipv4 == "192.168.10.45"
    assert last_event.gateway == "192.168.10.1"
    assert last_event.prefix == "192.168.10.0/24"

    link = await adapter.current_link()
    assert link.is_connected is True
    assert link.ssid == "Test_Office_WiFi"

    await adapter.disconnect()
    link_after = await adapter.current_link()
    assert link_after.is_connected is False


@pytest.mark.asyncio
async def test_association_wrong_password_failure():
    adapter = MockAssociationAdapter()
    req = AssociateRequest(
        association_id="asc_test_02",
        target_id="tgt_ap_02",
        ssid="Secured_WiFi",
        security_type="wpa2_personal",
    )

    events = []
    async for ev in adapter.associate(req, password="WRONG_PASSWORD"):
        events.append(ev)

    states = [e.state for e in events]
    assert "authenticating" in states
    assert states[-1] == "failed"
    assert events[-1].error_code == "WIFI_AUTH_FAILED"


@pytest.mark.asyncio
async def test_radio_mutex_pauses_and_resumes_scan():
    mutex = RadioMutex()
    assert mutex.state == "idle"

    # 1. Start scanning
    await mutex.notify_scan_started()
    assert mutex.state == "scanning"

    # 2. Acquire for association
    await mutex.acquire_for_association(ssid="Target_SSID")
    assert mutex.state == "associating"
    assert mutex.associated_ssid == "Target_SSID"

    # 3. Mark connected
    await mutex.mark_connected()
    assert mutex.state == "associated"
    assert mutex.is_associated is True

    # 4. Release from association (should restore scanning)
    should_resume = await mutex.release_from_association()
    assert should_resume is True
    assert mutex.state == "scanning"
    assert mutex.is_associated is False

    # 5. Stop scanning
    await mutex.notify_scan_stopped()
    assert mutex.state == "idle"
