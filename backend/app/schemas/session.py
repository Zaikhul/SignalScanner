from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from .common import ScanMode, SessionStatus


class RadioConfig(BaseModel):
    center_frequency_hz: int = 433920000  # Default 433.92 MHz ISM band
    span_hz: int = 2000000  # 2 MHz span
    sample_rate_hz: int = 2048000
    gain_db: Optional[float] = 20.0
    fft_size: int = 1024
    window: str = "hann"  # hann, hamming, blackman, rectangular
    averaging: int = 1
    calibration_profile_id: Optional[str] = None


class PrivacyConfig(BaseModel):
    pseudonymize_identifiers: bool = True
    mask_ssid: bool = False
    collect_payload: bool = False  # Always False per PRD non-goals


class CreateSessionRequest(BaseModel):
    name: str = "Live Measurement Session"
    mode: ScanMode
    collector_id: str
    source_type: Literal["collector", "simulator"] = "collector"
    duration_seconds: Optional[int] = None
    sample_interval_ms: int = 500
    radio_config: Optional[RadioConfig] = None
    privacy_config: PrivacyConfig = Field(default_factory=PrivacyConfig)
    tags: List[str] = Field(default_factory=list)


class SessionMarkerCreate(BaseModel):
    label: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class SessionMarkerResponse(BaseModel):
    id: str
    session_id: str
    label: str
    timestamp: datetime
    notes: Optional[str] = None


class SessionSummary(BaseModel):
    total_samples: int = 0
    unique_targets: int = 0
    min_signal: Optional[float] = None
    max_signal: Optional[float] = None
    median_signal: Optional[float] = None
    noise_floor_estimate: Optional[float] = None
    duration_seconds: float = 0.0


class SessionResponse(BaseModel):
    id: str
    name: str
    mode: ScanMode
    collector_id: str
    source_type: Literal["collector", "simulator"] = "collector"
    status: SessionStatus
    config: Dict[str, Any]
    tags: List[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    summary: Optional[SessionSummary] = None
    markers: List[SessionMarkerResponse] = Field(default_factory=list)
