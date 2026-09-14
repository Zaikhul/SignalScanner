from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol


@dataclass
class AssociateRequest:
    association_id: str
    target_id: str
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    security_type: str = "wpa2_personal"  # open, wpa2_personal, wpa3_sae
    save_profile: bool = False
    timeout_seconds: int = 30


@dataclass
class AssociationEvent:
    state: str  # requesting_permission, associating, authenticating, obtaining_address, connected, disconnecting, failed
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    prefix: Optional[str] = None
    gateway: Optional[str] = None
    dns: List[str] = field(default_factory=list)
    dhcp_server: Optional[str] = None
    captive_state: str = "unknown"
    error_code: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkState:
    is_connected: bool
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    ipv4: Optional[str] = None
    gateway: Optional[str] = None
    link_speed_mbps: Optional[int] = None
    signal_quality_pct: Optional[int] = None


@dataclass
class InventoryBound:
    interface_name: str
    attached_prefix: str  # CIDR, e.g. "192.168.1.0/24"
    gateway_ip: Optional[str] = None
    dns_servers: List[str] = field(default_factory=list)
    max_hosts: int = 256
    rate_limit: int = 10
    allowed_methods: List[str] = field(
        default_factory=lambda: ["interface_snapshot", "arp_cache", "ndp_cache", "mdns", "bounded_icmp"]
    )


@dataclass
class HostBatch:
    association_id: str
    session_id: str
    hosts: List[Dict[str, Any]]
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AssociationAdapter(Protocol):
    async def capabilities(self) -> Dict[str, Any]:
        ...

    async def associate(
        self, request: AssociateRequest, password: Optional[str] = None
    ) -> AsyncIterator[AssociationEvent]:
        ...

    async def disconnect(self, forget_profile: bool = True) -> None:
        ...

    async def current_link(self) -> LinkState:
        ...


class LanInventoryAdapter(Protocol):
    async def capabilities(self) -> Dict[str, Any]:
        ...

    async def start(self, bound: InventoryBound) -> AsyncIterator[HostBatch]:
        ...

    async def stop(self) -> None:
        ...
