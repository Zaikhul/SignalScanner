from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class AssociationState(str, Enum):
    IDLE = "idle"
    REQUESTING_PERMISSION = "requesting_permission"
    ASSOCIATING = "associating"
    AUTHENTICATING = "authenticating"
    OBTAINING_ADDRESS = "obtaining_address"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    FAILED = "failed"


class CreateAssociationDraftRequest(BaseModel):
    target_id: str
    security_hint: Optional[str] = "wpa2_personal"
    ssid: Optional[str] = None
    bssid_hash: Optional[str] = None


class ConnectAssociationRequest(BaseModel):
    """
    Public REST Connect payload (PRD v1.1 - Section 17.1).
    STRICT PRIVACY: Passwords must NEVER be included in this request.
    """
    target_id: str
    security_hint: str = "wpa2_personal"  # open, wpa2_personal, wpa3_sae
    authorized_use_confirmed: bool = Field(..., description="Must confirm authorization gate")
    save_profile: bool = False
    timeout_seconds: int = Field(default=30, ge=10, le=60)

    @model_validator(mode="before")
    @classmethod
    def reject_passwords_or_secrets(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden = {"password", "psk", "secret", "key_material", "passphrase"}
            found = forbidden.intersection(k.lower() for k in data.keys())
            if found:
                raise ValueError(
                    f"Forbidden credential fields detected: {found}. "
                    "PRD v1.1 FR-CON-07 strictly prohibits passwords in backend REST API!"
                )
        return data


class DisconnectAssociationRequest(BaseModel):
    forget_profile: bool = True


class AssociationResponse(BaseModel):
    id: str
    session_id: str
    collector_id: str
    adapter_id: str
    target_id: str
    ssid: Optional[str] = None
    bssid_hash: Optional[str] = None
    security_type: str
    state: str
    associated_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    prefix: Optional[str] = None
    gateway: Optional[str] = None
    dns: List[str] = Field(default_factory=list)
    dhcp_server: Optional[str] = None
    captive_state: str = "unknown"
    save_profile_requested: bool = False
    forget_profile_on_exit: bool = True
    created_at: datetime


class AssociationEventResponse(BaseModel):
    id: int
    association_id: str
    from_state: str
    to_state: str
    error_code: Optional[str] = None
    actor_id: Optional[str] = "user"
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class LanHostItem(BaseModel):
    id: Optional[int] = None
    ip: str
    ip_version: int = 4
    hostname: Optional[str] = None
    mac_hash: str
    oui_vendor: Optional[str] = None
    discovery_methods: List[str] = Field(default_factory=list)
    reachability: str = "up"  # up, limited, down
    rtt_ms: Optional[float] = None
    is_self: bool = False
    is_gateway: bool = False
    quality_flags: List[str] = Field(default_factory=list)
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LanHostListResponse(BaseModel):
    association_id: str
    items: List[LanHostItem]
    total: int


class IngestAssociationStatusRequest(BaseModel):
    state: str
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    prefix: Optional[str] = None
    gateway: Optional[str] = None
    dns: Optional[List[str]] = None
    dhcp_server: Optional[str] = None
    captive_state: Optional[str] = None
    error_code: Optional[str] = None


class IngestHostBatchRequest(BaseModel):
    association_id: str
    session_id: str
    hosts: List[LanHostItem]
