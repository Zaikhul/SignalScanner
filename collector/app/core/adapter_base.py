from abc import abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol
from pydantic import BaseModel, Field


class AdapterCapabilities(BaseModel):
    adapter_id: str
    mode: str  # "wifi", "bluetooth", "radio"
    name: str
    is_available: bool = True
    driver_version: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ScanConfig(BaseModel):
    session_id: str
    sample_interval_ms: int = 500
    duration_seconds: Optional[int] = None
    # Radio specific
    center_frequency_hz: Optional[int] = 433920000
    span_hz: Optional[int] = 2000000
    sample_rate_hz: Optional[int] = 2048000
    gain_db: Optional[float] = 20.0
    fft_size: Optional[int] = 1024
    # WiFi / BLE filter
    band_filter: Optional[str] = None  # "2.4GHz", "5GHz", "all"
    rssi_min_filter: Optional[float] = None


class ValidationResult(BaseModel):
    is_valid: bool
    error_message: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class SignalAdapter(Protocol):
    """
    Standard protocol for all hardware and virtual signal adapters.
    """
    async def capabilities(self) -> AdapterCapabilities:
        ...

    async def validate(self, config: ScanConfig) -> ValidationResult:
        ...

    async def start(self, config: ScanConfig) -> AsyncIterator[Dict[str, Any]]:
        ...

    async def stop(self) -> None:
        ...
