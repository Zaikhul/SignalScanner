from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScanState(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    SCANNING = "scanning"
    CANCELLING = "cancelling"
    SUCCESS = "success"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ProfileId(str, enum.Enum):
    V2 = "v2"
    LEGACY_V47 = "legacy_v47"
    LEGACY_V75 = "legacy_v75"
    COMPREHENSIVE = "comprehensive"


class ModuleId(str, enum.Enum):
    RECON = "recon"
    HEADERS = "headers"
    COOKIES = "cookies"
    FORMS = "forms"
    PARAMETERS = "parameters"
    HEADER_PROBES = "header_probes"
    STRESS = "stress"
    LOAD = "stress"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(str, enum.Enum):
    CONFIRMED_CONFIG = "confirmed_configuration"
    SUSPECTED = "suspected"
    INCONCLUSIVE = "inconclusive"


class CheckStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"
    INCONCLUSIVE = "inconclusive"


class ErrorStage(str, enum.Enum):
    VALIDATION = "validation"
    AUTHORIZATION = "authorization"
    QUEUE = "queue"
    DNS = "dns"
    CONNECT = "connect"
    TLS = "tls"
    REQUEST = "request"
    RESPONSE = "response"
    PARSE = "parse"
    MODULE = "module"
    MODULE_EXECUTION = "module_execution"
    STORAGE = "storage"
    STREAM = "stream"
    EXPORT = "export"


class RequestBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrency: int = Field(default=100000, ge=1, le=100000)
    per_origin_concurrency: int = Field(default=50000, ge=1, le=50000)
    requests_per_second: float = Field(default=10000.0, ge=0.5, le=10000.0)
    max_requests: int = Field(default=10000000, ge=10, le=10000000)
    job_timeout_seconds: int = Field(default=600, ge=30, le=3600)


class ScopeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(..., min_length=1, max_length=253)
    ports: List[int] = Field(default_factory=lambda: [80, 443])
    path_prefixes: List[str] = Field(default_factory=lambda: ["/"])
    allowed_cidrs: List[str] = Field(default_factory=list)
    allow_private: bool = False
    allow_loopback: bool = False
    methods: List[Literal["GET", "POST", "PUT"]] = Field(default_factory=lambda: ["GET", "POST"])
    checks: List[str] = Field(default_factory=lambda: ["all"])


class CreateScopeGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_reference: str = Field(..., min_length=3, max_length=128)
    assigned_principal_ids: List[str] = Field(default_factory=lambda: ["*"])
    rules: List[ScopeRule] = Field(..., min_length=1)
    expires_at: datetime
    budget: RequestBudget = Field(default_factory=RequestBudget)
    allow_tls_unverified: bool = False
    allow_geolocation: bool = False
    allow_load: bool = False
    allow_header_variants: bool = False


class ScopeGrant(CreateScopeGrant):
    id: str
    tenant_id: str
    revision: int = 1
    created_at: datetime
    created_by: str
    revoked_at: Optional[datetime] = None
    scope_hash: str


class LoadConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST"] = "GET"
    concurrency: int = Field(default=100000, ge=1, le=100000)
    duration_seconds: int = Field(default=600, ge=1, le=3600)
    delay_seconds: float = Field(default=0.05, ge=0.01, le=5.0)
    body_template: Literal["none", "benign_5k"] = "none"


class ScanConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: ProfileId = ProfileId.V2
    modules: Optional[List[ModuleId]] = None
    timeout_seconds: float = Field(default=600.0, ge=1.0, le=3600.0)
    tls_verify: bool = True
    allow_private: bool = False
    allow_loopback: bool = False
    max_concurrency: int = Field(default=100000, ge=1, le=100000)
    per_origin_concurrency: int = Field(default=50000, ge=1, le=50000)
    requests_per_second: float = Field(default=10000.0, ge=0.5, le=10000.0)
    max_requests: int = Field(default=10000000, ge=10, le=10000000)
    job_timeout_seconds: int = Field(default=600, ge=30, le=3600)
    retry_attempts: int = Field(default=0, ge=0, le=0)
    geolocation_enabled: bool = False
    user_agent_profile: Literal["source_rotation", "fixed"] = "source_rotation"
    fixed_user_agent: Optional[str] = None
    mutation_profile: Literal["none", "source_v75_approved"] = "none"
    random_seed: int = Field(default=310, ge=0)
    load: Optional[LoadConfiguration] = None

    @model_validator(mode="after")
    def populate_default_modules(self) -> "ScanConfiguration":
        if self.modules is None:
            if self.profile == ProfileId.LEGACY_V47:
                self.modules = [
                    ModuleId.RECON,
                    ModuleId.FORMS,
                    ModuleId.PARAMETERS,
                    ModuleId.STRESS,
                ]
            elif self.profile == ProfileId.LEGACY_V75:
                self.modules = [
                    ModuleId.RECON,
                    ModuleId.FORMS,
                    ModuleId.PARAMETERS,
                    ModuleId.HEADER_PROBES,
                    ModuleId.STRESS,
                ]
            elif self.profile == ProfileId.COMPREHENSIVE:
                self.modules = [
                    ModuleId.RECON,
                    ModuleId.HEADERS,
                    ModuleId.COOKIES,
                    ModuleId.FORMS,
                    ModuleId.PARAMETERS,
                    ModuleId.HEADER_PROBES,
                    ModuleId.STRESS,
                ]
            else:
                self.modules = [
                    ModuleId.RECON,
                    ModuleId.HEADERS,
                    ModuleId.COOKIES,
                    ModuleId.HEADER_PROBES,
                ]

        if self.modules and (ModuleId.STRESS in self.modules or ModuleId.LOAD in self.modules):
            if self.load is None:
                self.load = LoadConfiguration()
        return self


class CreateScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., min_length=3, max_length=2048)
    scope_id: Optional[str] = None
    configuration: Optional[ScanConfiguration] = None
    authorization_acknowledged: bool = Field(..., description="Must acknowledge authorization to scan target")

    @field_validator("authorization_acknowledged")
    @classmethod
    def must_be_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("authorization_acknowledged must be True")
        return v


class CoverageEntry(BaseModel):
    check_id: str
    module: ModuleId
    status: CheckStatus
    reason_code: Optional[str] = None
    planned_requests: Optional[int] = None
    completed_requests: int = 0
    truncated: bool = False


class ScanError(BaseModel):
    id: str
    scan_id: Optional[str] = None
    request_id: Optional[str] = None
    module: Optional[ModuleId] = None
    check_id: Optional[str] = None
    code: str
    stage: ErrorStage
    message: str
    retryable: bool = False
    occurred_at: datetime
    http_status: Optional[int] = None


class EvidenceExcerpt(BaseModel):
    kind: Literal["header", "cookie_attribute", "text", "timing"]
    value_redacted: str


class Evidence(BaseModel):
    request_id: Optional[str] = None
    observation_ids: List[str] = Field(default_factory=list)
    url_display: str
    method: Optional[Literal["GET", "POST", "PUT"]] = None
    status_code: Optional[int] = None
    header_names: List[str] = Field(default_factory=list)
    excerpts: List[EvidenceExcerpt] = Field(default_factory=list)
    baseline_request_id: Optional[str] = None
    control_request_ids: List[str] = Field(default_factory=list)
    elapsed_ms: Optional[float] = None
    baseline_elapsed_ms: Optional[float] = None
    body_length: Optional[int] = None
    baseline_body_length: Optional[int] = None
    body_truncated: bool = False
    catalog_entry_id: Optional[str] = None

    @field_validator("url_display", mode="before")
    @classmethod
    def sanitize_display_url(cls, v: Any) -> str:
        if isinstance(v, str):
            from app.core.web_scan.network_policy import redact_url_query_params
            return redact_url_query_params(v)
        return ""


class ScanFinding(BaseModel):
    id: str
    scan_id: str
    module: ModuleId
    check_id: str
    category: str
    source_category: Optional[str] = None
    severity: Severity
    source_severity: Optional[Severity] = None
    severity_reason: str
    confidence: Confidence
    title: str
    description: str
    remediation: str
    evidence: Evidence
    fingerprint: str
    occurrence_count: int = 1
    first_seen_at: datetime
    last_seen_at: datetime
    assessment_version: str = "web_scan.v1"


class ScanObservation(BaseModel):
    id: str
    scan_id: str
    module: ModuleId
    observed_at: datetime
    request_id: Optional[str] = None
    kind: Literal[
        "http_response", "redirect", "dns", "subdomain", "path",
        "technology", "form", "cookie", "comparison", "load", "geolocation"
    ]
    data: Dict[str, Any]


class RequestMetrics(BaseModel):
    attempted: int = 0
    completed: int = 0
    http_2xx_3xx: int = 0
    http_4xx: int = 0
    http_5xx: int = 0
    http_other: int = 0
    network_failed: int = 0
    aborted: int = 0
    in_flight: int = 0
    rate_limited: int = 0


class LoadMetrics(BaseModel):
    attempted: int = 0
    duration_ms: float = 0.0
    average_rps: Optional[float] = None
    legacy_success_lt_500: int = 0
    legacy_failure: int = 0
    legacy_evaluated: int = 0
    legacy_average_rps: Optional[float] = None
    legacy_failure_rate_percent: Optional[float] = None
    legacy_stress_severity: Optional[Severity] = None


class LegacyIndices(BaseModel):
    v47: Optional[Dict[str, Any]] = None
    v75: Optional[Dict[str, Any]] = None
    v2: Optional[Dict[str, Any]] = None


class ScanResult(BaseModel):
    counts_by_severity: Dict[str, int] = Field(
        default_factory=lambda: {s.value: 0 for s in Severity}
    )
    findings_total: int = 0
    observations_total: int = 0
    errors_total: int = 0
    requests: RequestMetrics = Field(default_factory=RequestMetrics)
    load_metrics: Optional[LoadMetrics] = None
    legacy_indices: LegacyIndices = Field(default_factory=LegacyIndices)
    coverage: List[CoverageEntry] = Field(default_factory=list)


class SourceCommits(BaseModel):
    signal_scanner: str = "main"
    ghost_web_scanner: str = "0774b0c9e1f2eb2763a1afee6233b2f4ddab9f35"


class ScanJob(BaseModel):
    id: str
    schema_version: Literal["web_scan.v1"] = "web_scan.v1"
    tenant_id: str = "default_tenant"
    created_by: str = "operator"
    scope_id: Optional[str] = None
    scope_revision: int = 1
    scope_hash: str = "inline_scope"
    target_display: str
    requested_configuration: ScanConfiguration
    effective_configuration: ScanConfiguration
    status: ScanState = ScanState.PENDING
    status_reason: Optional[str] = None
    version: int = 1
    created_at: datetime
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    cancel_requested_at: Optional[datetime] = None
    source_commits: SourceCommits = Field(default_factory=SourceCommits)
    engine_version: str = "1.0.0"
    catalog_version: str = "v75_v2_union"
    rules_version: str = "1.0.0"
    snapshot_sequence: int = 0


class ScanSnapshot(BaseModel):
    job: ScanJob
    result: ScanResult
    errors: List[ScanError] = Field(default_factory=list)


class ScanProgress(BaseModel):
    current_module: Optional[str] = None
    progress_percent: int = 0
    modules_completed: int = 0
    modules_total: int = 0


class WebScanEvent(BaseModel):
    scan_id: str
    sequence: int
    occurred_at: datetime
    type: Literal[
        "snapshot", "state_changed", "progress", "finding_upserted",
        "observation_added", "error_added", "completed", "cancelled", "failed"
    ]
    payload: Any


class Page(BaseModel):
    items: List[Any]
    total: int
    next_cursor: Optional[str] = None


class CheckCapabilityDescriptor(BaseModel):
    check_id: str
    module: ModuleId
    c_id: str
    title: str
    description: str
    default_severity: Severity
    applicability: str
    required_permissions: List[str] = Field(default_factory=lambda: ["web_scan:execute"])
    default_enabled: bool = True
    coverage_gap: Optional[str] = None


class ProfileDescriptor(BaseModel):
    profile_id: ProfileId
    name: str
    description: str
    modules: List[ModuleId]
    default_checks: List[str]


class Capabilities(BaseModel):
    schema_version: Literal["web_scan.v1"] = "web_scan.v1"
    source_commits: SourceCommits = Field(default_factory=SourceCommits)
    engine_version: str = "1.0.0"
    profiles: List[ProfileDescriptor]
    checks: List[CheckCapabilityDescriptor]
    defaults: ScanConfiguration
    hard_caps: Dict[str, Any]
    readiness: Dict[str, bool]
