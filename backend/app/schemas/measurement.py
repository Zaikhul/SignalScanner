import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
from .common import ScanMode

FreshnessState = Literal["fresh", "stale", "expired", "unknown"]
SourceMethod = Literal[
    "windows_native_wifi",
    "windows_netsh_fallback",
    "linux_nl80211",
    "bleak_ble",
    "soapysdr_rx",
    "virtual_simulator",
    "unknown",
]
RssiProcessing = Literal["raw", "os_filtered", "app_smoothed", "unknown"]

ChannelMetricType = Literal[
    "bss_overlap_index",
    "advertised_channel_load",
    "measured_airtime_utilization",
    "energy_occupancy",
    "unknown",
]
ChannelMetricEvidence = Literal["measured", "advertised", "inferred", "unknown"]


class SignalData(BaseModel):
    value: float = Field(..., description="Signal strength or power (dBm or dBFS)")
    unit: Literal["dBm", "dBFS"] = "dBm"
    noise: Optional[float] = Field(None, description="Noise floor estimate")
    snr: Optional[float] = Field(None, description="Signal-to-Noise Ratio (dB)")
    smoothed_value: Optional[float] = Field(None, description="EMA smoothed signal value")


class RadioMetadata(BaseModel):
    frequency_hz: Optional[int] = None
    channel: Optional[int] = None
    band: Optional[str] = None  # "2.4GHz", "5GHz", "6GHz"
    channel_width_mhz: Optional[int] = None
    center_frequency_hz: Optional[int] = None
    span_hz: Optional[int] = None
    fft_size: Optional[int] = None
    fft_bins: Optional[List[float]] = None  # List of bin powers in dBFS for spectrum/waterfall


class QualityFlags(BaseModel):
    """Backward-compatible quality flags and Measurement Quality contract (FQ-01)."""
    calibrated: bool = False
    permission_limited: bool = False
    throttled: bool = False

    # Enhanced FQ-01 Measurement Quality contract
    scan_id: Optional[str] = None
    scan_requested_at: Optional[datetime] = None
    scan_completed_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    collector_received_at: Optional[datetime] = None
    age_ms: Optional[int] = None
    actual_interval_ms: Optional[int] = None
    source_method: SourceMethod = "unknown"
    freshness: FreshnessState = "fresh"
    cache_possible: bool = False
    rssi_processing: RssiProcessing = "unknown"
    quality_flags: List[str] = Field(default_factory=list)
    fields_unavailable: List[str] = Field(default_factory=list)


MeasurementQuality = QualityFlags


class BleIdentityObservation(BaseModel):
    """BLE identity and presence state observation (BLEID-01)."""
    address_type: Literal["public", "random_static", "resolvable_private", "non_resolvable_private", "unknown"] = "unknown"
    identity_scope: Literal["global", "session", "ephemeral"] = "session"
    identity_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    name_source: Optional[str] = None
    rotation_suspected: bool = False
    presence_state: Literal["candidate", "present", "fading", "lost"] = "present"


class ChannelMetric(BaseModel):
    """Channel metric with unambiguous taxonomy and evidence classification (CHAN-01)."""
    channel: int
    metric_type: ChannelMetricType
    value: float = Field(..., description="Metric value (ratio, percentage, dBm, etc.)")
    unit: str = Field(default="ratio", description="Unit of the value (ratio, percentage, dBm, dBFS)")
    evidence: ChannelMetricEvidence = Field(default="inferred", description="measured | advertised | inferred | unknown")
    method: str = Field(default="weighted_bssid_overlap_v2", description="Calculation or measurement algorithm version")
    window_ms: int = Field(default=10000, description="Sliding window duration in ms")
    uncertainty: Optional[float] = Field(None, description="Uncertainty or confidence interval")


class NormalizedMeasurementEvent(BaseModel):
    schema_version: str = "2.0"
    trace_id: Optional[str] = None
    scan_id: Optional[str] = None
    session_id: str
    collector_id: str
    sequence: int
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: ScanMode
    target_id: str = Field(..., description="HMAC pseudonymized identifier")
    display_name: Optional[str] = None
    signal: SignalData
    radio: Optional[RadioMetadata] = None
    quality: QualityFlags = Field(default_factory=QualityFlags)
    ble_identity: Optional[BleIdentityObservation] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class MeasurementBatch(BaseModel):
    schema_version: str = "2.0"
    trace_id: Optional[str] = None
    scan_id: Optional[str] = None
    session_id: str
    collector_id: str
    source_type: str = "collector"
    sequence_from: int
    sequence_to: int
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    measurements: List[NormalizedMeasurementEvent]

    @model_validator(mode="after")
    def validate_batch_envelope(self) -> "MeasurementBatch":
        if self.sequence_from < 0:
            raise ValueError(f"sequence_from must be >= 0, got {self.sequence_from}")
        if self.sequence_to < self.sequence_from:
            raise ValueError(f"sequence_to ({self.sequence_to}) cannot be less than sequence_from ({self.sequence_from})")

        for m in self.measurements:
            if m.session_id != self.session_id:
                raise ValueError(
                    f"Measurement session_id '{m.session_id}' does not match batch session_id '{self.session_id}'"
                )
            if m.collector_id != self.collector_id:
                raise ValueError(
                    f"Measurement collector_id '{m.collector_id}' does not match batch collector_id '{self.collector_id}'"
                )
            if not (self.sequence_from <= m.sequence <= self.sequence_to):
                raise ValueError(
                    f"Measurement sequence {m.sequence} out of batch range [{self.sequence_from}, {self.sequence_to}]"
                )
            if not math.isfinite(m.signal.value):
                raise ValueError(f"Signal value must be a finite number, got {m.signal.value}")
            if m.signal.noise is not None and not math.isfinite(m.signal.noise):
                raise ValueError(f"Signal noise must be a finite number, got {m.signal.noise}")
            if m.signal.snr is not None and not math.isfinite(m.signal.snr):
                raise ValueError(f"Signal snr must be a finite number, got {m.signal.snr}")
            if m.signal.smoothed_value is not None and not math.isfinite(m.signal.smoothed_value):
                raise ValueError(f"Signal smoothed_value must be a finite number, got {m.signal.smoothed_value}")

        return self


class TargetSummary(BaseModel):
    target_id: str
    display_name: Optional[str] = None
    mode: ScanMode
    first_seen: datetime
    last_seen: datetime
    sample_count: int
    latest_signal: float
    unit: str
    min_signal: float
    max_signal: float
    median_signal: float
    avg_snr: Optional[float] = None
    channel: Optional[int] = None
    band: Optional[str] = None
    freshness: FreshnessState = "fresh"
    source_method: SourceMethod = "unknown"
    is_pinned: bool = False
    extra: Optional[Dict[str, Any]] = None
