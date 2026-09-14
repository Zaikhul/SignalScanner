from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .common import CollectorStatus, ScanMode


class AdapterInfo(BaseModel):
    id: str
    type: ScanMode  # wifi, bluetooth, radio
    name: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    driver_version: Optional[str] = None
    is_available: bool = True


class CollectorCapabilities(BaseModel):
    supported_modes: List[ScanMode]
    adapters: List[AdapterInfo]
    platform: str  # "windows", "linux", "darwin"
    version: str = "1.0.0"
    can_sdr: bool = False
    can_wifi: bool = True
    can_ble: bool = True
    wifi_associate: bool = True
    lan_discovery: bool = True
    scan_while_associated: bool = False
    requires_exclusive_radio: bool = True


class CollectorRegistration(BaseModel):
    id: str
    name: str
    platform: str
    version: str
    public_key: Optional[str] = None
    capabilities: CollectorCapabilities


class CollectorHeartbeat(BaseModel):
    collector_id: str
    status: CollectorStatus
    permission_state: Dict[str, bool] = Field(default_factory=dict)
    active_sessions: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectorResponse(BaseModel):
    id: str
    name: str
    platform: str
    version: str
    status: CollectorStatus
    capabilities: CollectorCapabilities
    last_seen: Optional[datetime] = None
    created_at: datetime


class DiagnosticCommand(BaseModel):
    collector_id: str
    command_type: str = "check_adapters"  # check_adapters, check_permissions, test_radio
    parameters: Optional[Dict[str, Any]] = None


class DiagnosticResult(BaseModel):
    collector_id: str
    command_type: str
    success: bool
    details: Dict[str, Any]
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectorCommand(BaseModel):
    command_id: str
    collector_id: str
    type: str  # "start_scan", "stop_scan", "pause_scan", "resume_scan"
    session_id: Optional[str] = None
    mode: Optional[ScanMode] = None
    sample_interval_ms: Optional[int] = 500
    parameters: Optional[Dict[str, Any]] = None
    status: str = "pending"  # "pending", "acknowledged", "completed", "failed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectorHeartbeatResponse(BaseModel):
    status: str = "ok"
    pending_commands: List[CollectorCommand] = Field(default_factory=list)
