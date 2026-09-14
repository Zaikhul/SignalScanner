from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ComponentProvenance(str, Enum):
    MEASURED = "measured"
    REPORTED = "reported"
    CONFIGURED = "configured"
    DERIVED = "derived"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HealthLabel(str, Enum):
    SEHAT = "Sehat"
    LAYAK = "Layak"
    PADAT = "Padat"
    BURUK = "Buruk"


class ChannelHealthComponentValue(BaseModel):
    value: Optional[float] = None
    provenance: ComponentProvenance = ComponentProvenance.UNAVAILABLE
    details: Optional[Dict[str, Any]] = None


class ChannelHealthComponents(BaseModel):
    utilization: ChannelHealthComponentValue
    overlap_interference: ChannelHealthComponentValue
    retry: ChannelHealthComponentValue
    noise: ChannelHealthComponentValue
    temporal_instability: ChannelHealthComponentValue


class ChannelHealthItem(BaseModel):
    channel: int
    band: str = "2.4GHz"
    width_mhz: int = 20
    health_score: int = Field(..., ge=0, le=100)
    health_label: str
    cci_power_mw: float = 0.0
    aci_power_mw: float = 0.0
    ap_count: int = 0
    max_rssi: float = -100.0
    is_dfs: bool = False
    is_candidate: bool = True
    exclusion_reasons: List[str] = Field(default_factory=list)
    components: ChannelHealthComponents


class ObservationWindowInfo(BaseModel):
    from_time: str
    to_time: str
    duration_seconds: float
    scan_cycles: int


class RegulatoryDomainInfo(BaseModel):
    value: str
    provenance: ComponentProvenance = ComponentProvenance.CONFIGURED
    source: str = "organization_setting"


class ChannelHealthSnapshotResponse(BaseModel):
    schema_version: str = "1.2"
    snapshot_id: str
    session_id: str
    band: str = "2.4GHz"
    channel_width_mhz: int = 20
    observation_window: ObservationWindowInfo
    regulatory_domain: RegulatoryDomainInfo
    channels: List[ChannelHealthItem]
    quality_flags: List[str] = Field(default_factory=list)
    created_at: str


class CandidateRecommendation(BaseModel):
    channel: int
    band: str
    width_mhz: int
    score: int
    health_label: str
    confidence: str
    is_dfs: bool = False
    cta_label: str


class ChannelRecommendationResponse(BaseModel):
    schema_version: str = "1.2"
    recommendation_id: str
    session_id: str
    input_snapshot_id: str
    algorithm_version: str = "channel-health-1.0.0"
    band: str = "2.4GHz"
    channel_width_mhz: int = 20
    primary: CandidateRecommendation
    alternatives: List[CandidateRecommendation] = Field(default_factory=list)
    confidence: ConfidenceLevel
    confidence_reasons: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    supporting_factors: List[str] = Field(default_factory=list)
    counter_signals: List[str] = Field(default_factory=list)
    conflict_detected: bool = False
    observation_window: ObservationWindowInfo
    freshness_status: str = "fresh"
    created_at: str


class EvaluateRecommendationRequest(BaseModel):
    band: Optional[str] = "2.4GHz"
    channel_width_mhz: Optional[int] = 20
    observation_window_sec: Optional[int] = 300
    regulatory_domain: Optional[str] = "ID"


class ChannelValidationRequest(BaseModel):
    marker_id: Optional[str] = None
    before_window_sec: int = 120
    after_window_sec: int = 120


class MetricDelta(BaseModel):
    before: Optional[float] = None
    after: Optional[float] = None
    delta: Optional[float] = None
    improved: Optional[bool] = None


class ChannelValidationResponse(BaseModel):
    validation_id: str
    session_id: str
    baseline_recommendation_id: Optional[str] = None
    marker_id: Optional[str] = None
    marker_label: Optional[str] = None
    before_window: Dict[str, Any] = Field(default_factory=dict)
    after_window: Dict[str, Any] = Field(default_factory=dict)
    metric_deltas: Dict[str, MetricDelta] = Field(default_factory=dict)
    summary_label: str
    created_at: str
