import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from collector.app.core.association_base import (
    AssociateRequest,
    AssociationAdapter,
    AssociationEvent,
    HostBatch,
    InventoryBound,
    LanInventoryAdapter,
    LinkState,
)
from collector.app.core.pseudonymizer import pseudonymize_id

logger = logging.getLogger("collector.mock_associate")


class MockAssociationAdapter:
    """Mock Association Adapter for testing association state machine without physical radio."""

    def __init__(self):
        self._connected = False
        self._current_ssid: Optional[str] = None
        self._current_ip = "192.168.10.45"
        self._current_gateway = "192.168.10.1"
        self._current_prefix = "192.168.10.0/24"

    async def capabilities(self) -> Dict[str, Any]:
        return {
            "can_associate": True,
            "supported_security": ["open", "wpa2_personal", "wpa3_sae"],
            "supports_temporary_profiles": True,
            "scan_while_associated": False,
        }

    async def associate(
        self, request: AssociateRequest, password: Optional[str] = None
    ) -> AsyncIterator[AssociationEvent]:
        self._current_ssid = request.ssid or "Mock_WiFi_Network"

        yield AssociationEvent(
            state="requesting_permission",
            timestamp=datetime.now(timezone.utc),
        )
        await asyncio.sleep(0.1)

        yield AssociationEvent(
            state="associating",
            timestamp=datetime.now(timezone.utc),
        )
        await asyncio.sleep(0.1)

        yield AssociationEvent(
            state="authenticating",
            timestamp=datetime.now(timezone.utc),
        )

        # Simulation branches
        if password == "WRONG_PASSWORD":
            await asyncio.sleep(0.1)
            self._connected = False
            yield AssociationEvent(
                state="failed",
                error_code="WIFI_AUTH_FAILED",
                timestamp=datetime.now(timezone.utc),
            )
            return

        if password == "TRIGGER_TIMEOUT":
            await asyncio.sleep(0.1)
            self._connected = False
            yield AssociationEvent(
                state="failed",
                error_code="WIFI_ASSOC_TIMEOUT",
                timestamp=datetime.now(timezone.utc),
            )
            return

        await asyncio.sleep(0.1)
        yield AssociationEvent(
            state="obtaining_address",
            timestamp=datetime.now(timezone.utc),
        )
        await asyncio.sleep(0.1)

        self._connected = True
        yield AssociationEvent(
            state="connected",
            ipv4=self._current_ip,
            prefix=self._current_prefix,
            gateway=self._current_gateway,
            dns=[self._current_gateway, "1.1.1.1"],
            dhcp_server=self._current_gateway,
            captive_state="internet",
            timestamp=datetime.now(timezone.utc),
        )

    async def disconnect(self, forget_profile: bool = True) -> None:
        self._connected = False
        self._current_ssid = None

    async def current_link(self) -> LinkState:
        return LinkState(
            is_connected=self._connected,
            ssid=self._current_ssid,
            ipv4=self._current_ip if self._connected else None,
            gateway=self._current_gateway if self._connected else None,
            link_speed_mbps=300 if self._connected else 0,
            signal_quality_pct=85 if self._connected else 0,
        )


class MockLanInventoryAdapter:
    """Mock LAN Inventory Adapter simulating discovered hosts on the attached prefix."""

    def __init__(self):
        self._running = False

    async def capabilities(self) -> Dict[str, Any]:
        return {
            "methods": ["interface_snapshot", "arp_cache", "mdns", "bounded_icmp"],
            "max_hosts": 256,
        }

    async def start(self, bound: InventoryBound) -> AsyncIterator[HostBatch]:
        self._running = True
        now = datetime.now(timezone.utc)

        # Generate realistic local hosts strictly within attached_prefix
        hosts = [
            {
                "ip": "192.168.10.45",
                "ip_version": 4,
                "hostname": "collector-unit",
                "mac_hash": pseudonymize_id("00:11:22:33:44:55"),
                "oui_vendor": "Intel Corp",
                "discovery_methods": ["interface_snapshot"],
                "reachability": "up",
                "rtt_ms": 0.05,
                "is_self": True,
                "is_gateway": False,
                "quality_flags": ["self", "interface_snapshot"],
            },
            {
                "ip": bound.gateway_ip or "192.168.10.1",
                "ip_version": 4,
                "hostname": "gateway.lan",
                "mac_hash": pseudonymize_id("c0:06:c3:11:22:33"),
                "oui_vendor": "Cisco Systems",
                "discovery_methods": ["gateway_snapshot", "arp_cache"],
                "reachability": "up",
                "rtt_ms": 1.2,
                "is_self": False,
                "is_gateway": True,
                "quality_flags": ["gateway", "arp_cache"],
            },
            {
                "ip": "192.168.10.12",
                "ip_version": 4,
                "hostname": "workstation-pc",
                "mac_hash": pseudonymize_id("d4:be:d9:44:55:66"),
                "oui_vendor": "Dell Inc",
                "discovery_methods": ["arp_cache", "bounded_icmp"],
                "reachability": "up",
                "rtt_ms": 3.4,
                "is_self": False,
                "is_gateway": False,
                "quality_flags": ["arp_cache", "solicited"],
            },
            {
                "ip": "192.168.10.88",
                "ip_version": 4,
                "hostname": "hp-laserjet-pro",
                "mac_hash": pseudonymize_id("3c:52:82:77:88:99"),
                "oui_vendor": "HP Inc",
                "discovery_methods": ["arp_cache", "mdns"],
                "reachability": "up",
                "rtt_ms": 5.1,
                "is_self": False,
                "is_gateway": False,
                "quality_flags": ["arp_cache", "mdns"],
            },
            {
                "ip": "192.168.10.150",
                "ip_version": 4,
                "hostname": "iot-sensor-node",
                "mac_hash": pseudonymize_id("24:0a:c4:aa:bb:cc"),
                "oui_vendor": "Espressif Inc",
                "discovery_methods": ["mdns", "bounded_icmp"],
                "reachability": "up",
                "rtt_ms": 8.9,
                "is_self": False,
                "is_gateway": False,
                "quality_flags": ["solicited", "mdns"],
            },
        ]

        yield HostBatch(
            association_id="mock_assoc",
            session_id="mock_session",
            hosts=hosts,
            captured_at=now,
        )

    async def stop(self) -> None:
        self._running = False
