export type ScanState =
  | "pending"
  | "queued"
  | "scanning"
  | "cancelling"
  | "success"
  | "completed"
  | "partial"
  | "failed"
  | "timeout"
  | "timed_out"
  | "cancelled"
  | "interrupted";

export type ProfileId = "v2" | "legacy_v47" | "legacy_v75" | "comprehensive";

export type ModuleId =
  | "recon"
  | "headers"
  | "cookies"
  | "forms"
  | "parameters"
  | "header_probes"
  | "stress";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export type Confidence = "confirmed_configuration" | "suspected" | "inconclusive";

export type CheckStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "not_applicable"
  | "inconclusive";

export interface RequestBudget {
  max_concurrency: number;
  per_origin_concurrency: number;
  requests_per_second: number;
  max_requests: number;
  job_timeout_seconds: number;
}

export interface ScopeRule {
  host: string;
  ports: number[];
  path_prefixes: string[];
  allowed_cidrs: string[];
  allow_private: boolean;
  allow_loopback: boolean;
  methods: ("GET" | "POST" | "PUT")[];
  checks: string[];
}

export interface ScopeGrant {
  id: string;
  tenant_id: string;
  authorization_reference: string;
  assigned_principal_ids: string[];
  rules: ScopeRule[];
  budget: RequestBudget;
  revision: number;
  created_at: string;
  created_by: string;
  expires_at: string;
  revoked_at?: string | null;
  scope_hash: string;
  allow_tls_unverified: boolean;
  allow_geolocation: boolean;
  allow_load: boolean;
  allow_header_variants: boolean;
}

export interface LoadConfiguration {
  method: "GET" | "POST";
  concurrency: number;
  duration_seconds: number;
  delay_seconds: number;
  body_template: "none" | "benign_5k";
}

export interface ScanConfiguration {
  profile: ProfileId;
  modules: ModuleId[];
  timeout_seconds: number;
  tls_verify: boolean;
  allow_private: boolean;
  allow_loopback?: boolean;
  max_concurrency: number;
  per_origin_concurrency: number;
  requests_per_second: number;
  max_requests: number;
  job_timeout_seconds: number;
  retry_attempts: number;
  geolocation_enabled: boolean;
  user_agent_profile: "source_rotation" | "fixed";
  fixed_user_agent?: string | null;
  mutation_profile: "none" | "source_v75_approved";
  random_seed: number;
  load?: LoadConfiguration | null;
}

export interface CreateScanRequest {
  target: string;
  scope_id?: string | null;
  configuration?: ScanConfiguration | null;
  authorization_acknowledged: boolean;
}

export interface CoverageEntry {
  check_id: string;
  module: ModuleId;
  status: CheckStatus;
  reason_code?: string | null;
  planned_requests?: number | null;
  completed_requests: number;
  truncated: boolean;
}

export interface ScanError {
  id: string;
  scan_id?: string | null;
  request_id?: string | null;
  module?: ModuleId | null;
  check_id?: string | null;
  code: string;
  stage: "preflight" | "module_execution" | "result_aggregation" | "export";
  message: string;
  retryable: boolean;
  occurred_at: string;
  http_status?: number | null;
}

export interface EvidenceExcerpt {
  kind: "header" | "cookie_attribute" | "text" | "timing";
  value_redacted: string;
}

export interface Evidence {
  request_id?: string | null;
  observation_ids: string[];
  url_display: string;
  method?: "GET" | "POST" | "PUT" | null;
  status_code?: number | null;
  header_names: string[];
  excerpts: EvidenceExcerpt[];
  baseline_request_id?: string | null;
  control_request_ids: string[];
  elapsed_ms?: number | null;
  baseline_elapsed_ms?: number | null;
  body_length?: number | null;
  baseline_body_length?: number | null;
  body_truncated: boolean;
  catalog_entry_id?: string | null;
}

export interface ScanFinding {
  id: string;
  scan_id: string;
  module: ModuleId;
  check_id: string;
  category: string;
  source_category?: string | null;
  severity: Severity;
  source_severity?: Severity | null;
  severity_reason: string;
  confidence: Confidence;
  title: string;
  description: string;
  remediation: string;
  evidence: Evidence;
  fingerprint: string;
  occurrence_count: number;
  assessment_version: string;
  first_seen_at: string;
  last_seen_at: string;
}

export interface ScanObservation {
  id: string;
  scan_id: string;
  module: ModuleId;
  kind: string;
  request_id?: string | null;
  data: Record<string, any>;
  observed_at: string;
}

export interface RequestMetrics {
  attempted: number;
  completed: number;
  network_failed: number;
  http_2xx_3xx: number;
  http_4xx: number;
  http_5xx: number;
  http_other: number;
  rate_limited: number;
  bytes_received: number;
}

export interface LoadMetrics {
  attempted: number;
  duration_ms: number;
  average_rps?: number | null;
  legacy_success_lt_500: number;
  legacy_failure: number;
  legacy_evaluated: number;
  legacy_average_rps?: number | null;
}

export interface LegacyIndices {
  v47?: { value: number; formula_version: string; source_band: string } | null;
  v75?: { value: number; formula_version: string; source_band: string } | null;
  v2?: { value: number; formula_version: string; source_band: string } | null;
}

export interface ScanResult {
  counts_by_severity: Record<Severity, number>;
  findings_total: number;
  observations_total: number;
  errors_total: number;
  requests: RequestMetrics;
  load_metrics?: LoadMetrics | null;
  legacy_indices: LegacyIndices;
  coverage: CoverageEntry[];
}

export interface ScanJob {
  id: string;
  schema_version: "web_scan.v1";
  tenant_id: string;
  created_by: string;
  scope_id?: string | null;
  scope_revision: number;
  scope_hash: string;
  target_display: string;
  requested_configuration: ScanConfiguration;
  effective_configuration: ScanConfiguration;
  status: ScanState;
  status_reason?: string | null;
  version: number;
  created_at: string;
  queued_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  cancel_requested_at?: string | null;
  snapshot_sequence: number;
}

export interface ScanSnapshot {
  job: ScanJob;
  result: ScanResult;
  errors: ScanError[];
}

export interface WebScanEvent {
  scan_id: string;
  sequence: number;
  occurred_at: string;
  type:
    | "snapshot"
    | "state_changed"
    | "progress"
    | "finding_upserted"
    | "observation_added"
    | "error_added"
    | "completed"
    | "cancelled"
    | "failed";
  payload: any;
}

export interface Page<T> {
  items: T[];
  total: number;
  next_cursor?: string | null;
}

export interface CheckCapabilityDescriptor {
  check_id: string;
  module: ModuleId;
  c_id: string;
  title: string;
  description: string;
  default_severity: Severity;
  applicability: string;
  required_permissions: string[];
  default_enabled: boolean;
  coverage_gap?: string | null;
}

export interface ProfileDescriptor {
  profile_id: ProfileId;
  name: string;
  description: string;
  modules: ModuleId[];
  default_checks: string[];
}

export interface Capabilities {
  schema_version: "web_scan.v1";
  source_commits: { signal_scanner: string; ghost_web_scanner: string };
  engine_version: string;
  profiles: ProfileDescriptor[];
  checks: CheckCapabilityDescriptor[];
  defaults: ScanConfiguration;
  hard_caps: Record<string, any>;
  readiness: Record<string, boolean>;
}

// ──────────────────────────────────────────────────────────────────────────
// Geography & Relationship Graph Types (web_scan.geo.v1)
// ──────────────────────────────────────────────────────────────────────────

export interface GeoPoint {
  latitude: number;
  longitude: number;
  city?: string | null;
  region?: string | null;
  country?: string | null;
  country_code?: string | null;
}

export type EndpointRole = "source" | "target";

export type AddressBasis =
  | "configured"
  | "dns_candidate"
  | "transport_selected"
  | "observed_connection"
  | "unresolved";

export type LocationLevel = "coordinates" | "city" | "region" | "country" | "unknown";
export type LocationBasis = "configured" | "ip_lookup_estimate" | "unknown";
export type LocationStatus = "located" | "unknown" | "unsupported" | "lookup_failed" | "disallowed";

export interface GeoEndpoint {
  id: string;
  role: EndpointRole;
  display_name: string;
  ip?: string | null;
  address_basis: AddressBasis;
  executor_id?: string | null;
  location?: GeoPoint | null;
  location_level: LocationLevel;
  location_basis: LocationBasis;
  location_status: LocationStatus;
  status_reason?: string | null;
  provider_info?: string | null;
}

export type RelationBasis = "observed_http" | "transport_attempt" | "configured_target";

export interface GeoRelation {
  id: string;
  source_endpoint_id: string;
  target_endpoint_id: string;
  direction: "source_to_target";
  relation_basis: RelationBasis;
  record_count: number;
  unit: "records";
  status_codes: number[];
  methods: string[];
  supporting_observation_ids: string[];
  linked_finding_ids: string[];
}

export interface GeoCoverage {
  observations_total: number;
  observations_stored: number;
  eligible_records: number;
  both_located_count: number;
  partial_located_count: number;
  unlocated_count: number;
  is_subset: boolean;
  storage_ceiling: number;
}

export type GeoReadinessStatus = "ready" | "processing" | "empty" | "no_locations" | "partial";

export interface WebScanGeographyResponse {
  scan_id: string;
  schema_version: "web_scan.geo.v1";
  data_revision: number;
  generated_at: string;
  readiness_status: GeoReadinessStatus;
  target_display: string;
  scan_status: string;
  coverage: GeoCoverage;
  endpoints: GeoEndpoint[];
  relations: GeoRelation[];
  time_info: Record<string, any>;
  disclaimers: Record<string, string>;
}
