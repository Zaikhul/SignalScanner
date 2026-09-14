from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DiagnosticStatus(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"


class DiagnosticCheckItem(BaseModel):
    layer: str = Field(..., description="Architecture layer: os_permission | adapter | scan_path | backend | storage_stream | clock | sdr")
    name: str = Field(..., description="Specific diagnostic check name")
    status: DiagnosticStatus = Field(..., description="Check status: READY | DEGRADED | BLOCKED | UNSUPPORTED")
    message: str = Field(..., description="Human-readable result summary")
    technical_details: Optional[str] = Field(None, description="Detailed technical reason or platform error")
    remediation_step: Optional[str] = Field(None, description="Actionable step the user can take to fix the issue")


class PreflightDiagnosticResult(BaseModel):
    collector_id: str
    overall_status: DiagnosticStatus
    checks: List[DiagnosticCheckItem]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    platform: str = "windows"
    mode: str = "wifi"
