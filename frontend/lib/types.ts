export type ScanMode = "wifi" | "bluetooth" | "radio";

export type SessionStatus =
  | "draft"
  | "starting"
  | "active"
  | "paused"
  | "completed"
  | "stopped"
  | "failed"
  | "interrupted";

export type CollectorStatus =
  | "ready"
  | "busy"
  | "scanning"
  | "starting"
  | "permission_denied"
  | "adapter_off"
  | "offline"
  | "error";

export type FreshnessState = "fresh" | "stale" | "expired" | "unknown";
export type SourceMethod =
  | "windows_native_wifi"
  | "windows_netsh_fallback"
  | "linux_nl80211"
  | "bleak_ble"
  | "soapysdr_rx"
  | "virtual_simulator"
  | "unknown";
export type RssiProcessing = "raw" | "os_filtered" | "app_smoothed" | "unknown";
export type ChannelMetricEvidence = "measured" | "advertised" | "inferred" | "unknown";
export type DiagnosticStatus = "READY" | "DEGRADED" | "BLOCKED" | "UNSUPPORTED";

export interface SignalData {
  value: number; // dBm or dBFS
  unit: "dBm" | "dBFS";
  noise?: number | null;
  snr?: number | null;
  smoothed_value?: number | null;
}

export interface RadioMetadata {
  frequency_hz?: number | null;
  channel?: number | null;
  band?: string | null; // "2.4GHz" | "5GHz" | "6GHz"
  channel_width_mhz?: number | null;
  center_frequency_hz?: number | null;
  span_hz?: number | null;
  fft_size?: number | null;
  fft_bins?: number[] | null;
}

export interface QualityFlags {
  calibrated: boolean;
  permission_limited: boolean;
  throttled: boolean;
  scan_id?: string | null;
  scan_requested_at?: string | null;
  scan_completed_at?: string | null;
  observed_at?: string | null;
  collector_received_at?: string | null;
  age_ms?: number | null;
  actual_interval_ms?: number | null;
  source_method?: SourceMethod;
  freshness?: FreshnessState;
  cache_possible?: boolean;
  rssi_processing?: RssiProcessing;
  quality_flags?: string[];
  fields_unavailable?: string[];
}

export interface BleIdentityObservation {
  address_type: "public" | "random_static" | "resolvable_private" | "non_resolvable_private" | "unknown";
  identity_scope: "global" | "session" | "ephemeral";
  identity_confidence: number;
  name_source?: string | null;
  rotation_suspected: boolean;
  presence_state: "candidate" | "present" | "fading" | "lost";
}

export interface ChannelMetric {
  channel: number;
  metric_type: string;
  value: number;
  unit: string;
  evidence: ChannelMetricEvidence;
  method: string;
  window_ms: number;
  uncertainty?: number | null;
}

export interface MeasurementEvent {
  schema_version: string;
  trace_id?: string | null;
  scan_id?: string | null;
  session_id: string;
  collector_id: string;
  source_type?: string;
  sequence: number;
  captured_at: string;
  mode: ScanMode;
  target_id: string;
  display_name?: string | null;
  signal: SignalData;
  radio?: RadioMetadata | null;
  quality: QualityFlags;
  ble_identity?: BleIdentityObservation | null;
  extra_metadata?: Record<string, any> | null;
}

export interface TargetSummary {
  target_id: string;
  display_name?: string | null;
  mode: ScanMode;
  first_seen: string;
  last_seen: string;
  observed_at?: string | null;
  sample_count: number;
  latest_signal: number;
  previous_signal?: number | null;
  delta_signal?: number | null; // Delta in dB from previous observation
  unit: string;
  min_signal: number;
  max_signal: number;
  median_signal: number;
  avg_snr?: number | null;
  channel?: number | null;
  band?: string | null;
  freshness?: FreshnessState;
  computed_freshness?: FreshnessState;
  source_method?: SourceMethod;
  is_pinned: boolean;
  is_stale?: boolean;
  is_expired?: boolean;
  out_of_scale?: "low" | "high" | null;
  reason_unplottable?: string | null;
  children_bssids?: TargetSummary[];
  extra?: Record<string, any> | null;
}

export interface SessionMarker {
  id: string;
  session_id: string;
  label: string;
  timestamp: string;
  notes?: string | null;
}

export interface SessionSummary {
  total_samples: number;
  unique_targets: number;
  min_signal?: number | null;
  max_signal?: number | null;
  median_signal?: number | null;
  noise_floor_estimate?: number | null;
  duration_seconds: number;
}

export interface ScanSession {
  id: string;
  name: string;
  mode: ScanMode;
  collector_id: string;
  source_type?: "collector" | "simulator";
  status: SessionStatus;
  config?: Record<string, any>;
  tags?: string[];
  started_at?: string | null;
  ended_at?: string | null;
  created_at: string;
  summary: SessionSummary;
  markers: SessionMarker[];
}

export interface SessionProvenanceManifest {
  manifest_version: string;
  session_id: string;
  collector_id: string;
  collector_version: string;
  os: Record<string, any>;
  adapter: Record<string, any>;
  scan_config: Record<string, any>;
  processing_version: string;
  processing_config_hash: string;
  calibration_profile_id?: string | null;
  clock: {
    offset_ms: number;
    uncertainty_ms: number;
    source: string;
  };
  privacy_policy_id: string;
  schema_version: string;
  sequence_summary: {
    first_sequence: number;
    last_sequence: number;
    total_received: number;
    missing_ranges: number[][];
  };
  created_at: string;
  manifest_checksum: string;
}

export interface DiagnosticCheckItem {
  layer: string;
  name: string;
  status: DiagnosticStatus;
  message: string;
  technical_details?: string | null;
  remediation_step?: string | null;
}

export interface PreflightDiagnosticResult {
  collector_id: string;
  overall_status: DiagnosticStatus;
  checks: DiagnosticCheckItem[];
  timestamp: string;
  platform: string;
  mode: string;
}

export interface CollectorCapability {
  supported_modes: ScanMode[];
  adapters: {
    id: string;
    type: string;
    name: string;
    is_available: boolean;
  }[];
  platform: string;
  version: string;
  can_wifi?: boolean;
  can_ble?: boolean;
  can_sdr?: boolean;
}

export interface CollectorDevice {
  id: string;
  name: string;
  platform: string;
  version: string;
  status: CollectorStatus;
  capabilities: CollectorCapability;
  last_seen: string;
  created_at: string;
}

export type Collector = CollectorDevice;

export type AssociationState =
  | "idle"
  | "requesting_permission"
  | "associating"
  | "authenticating"
  | "obtaining_address"
  | "connected"
  | "disconnecting"
  | "failed";

export interface WifiAssociation {
  id: string;
  session_id: string;
  collector_id: string;
  adapter_id: string;
  target_id: string;
  ssid?: string | null;
  bssid_hash?: string | null;
  security_type: string;
  state: AssociationState;
  associated_at?: string | null;
  disconnected_at?: string | null;
  ipv4?: string | null;
  ipv6?: string | null;
  prefix?: string | null;
  gateway?: string | null;
  dns?: string[];
  dhcp_server?: string | null;
  captive_state?: string;
  save_profile_requested?: boolean;
  forget_profile_on_exit?: boolean;
  created_at: string;
}

export interface PortInfo {
  port: number;
  service: string;
  state: "open" | "filtered" | "closed";
}

export interface LanHost {
  id?: number;
  ip: string;
  ip_version: number;
  hostname?: string | null;
  mac_hash: string;
  oui_vendor?: string | null;
  discovery_methods: string[];
  reachability: "up" | "limited" | "down";
  rtt_ms?: number | null;
  is_self: boolean;
  is_gateway: boolean;
  quality_flags: string[];
  open_ports?: PortInfo[];
  last_seen: string;
}

export interface AssociationEvent {
  id: number;
  association_id: string;
  from_state: string;
  to_state: string;
  error_code?: string | null;
  actor_id?: string | null;
  metadata_json?: Record<string, any>;
  timestamp: string;
}

// --- CHANNEL HEALTH & RECOMMENDATION ENGINE v1.2 TYPES (PRD Section 17.4, 17.5, 19) ---

export type ComponentProvenance =
  | "measured"
  | "reported"
  | "configured"
  | "derived"
  | "inferred"
  | "unavailable";

export type ConfidenceLevel = "high" | "medium" | "low";

export interface ChannelHealthComponentValue {
  value?: number | null;
  provenance: ComponentProvenance;
  details?: Record<string, any> | null;
}

export interface ChannelHealthComponents {
  utilization: ChannelHealthComponentValue;
  overlap_interference: ChannelHealthComponentValue;
  retry: ChannelHealthComponentValue;
  noise: ChannelHealthComponentValue;
  temporal_instability: ChannelHealthComponentValue;
}

export interface ChannelHealthItem {
  channel: number;
  band: string;
  width_mhz: number;
  health_score: number;
  health_label: string;
  cci_power_mw: number;
  aci_power_mw: number;
  ap_count: number;
  max_rssi: number;
  is_dfs: boolean;
  is_candidate: boolean;
  exclusion_reasons: string[];
  components: ChannelHealthComponents;
}

export interface ObservationWindowInfo {
  from_time: string;
  to_time: string;
  duration_seconds: number;
  scan_cycles: number;
}

export interface RegulatoryDomainInfo {
  value: string;
  provenance: ComponentProvenance;
  source: string;
}

export interface ChannelHealthSnapshot {
  schema_version: string;
  snapshot_id: string;
  session_id: string;
  band: string;
  channel_width_mhz: number;
  observation_window: ObservationWindowInfo;
  regulatory_domain: RegulatoryDomainInfo;
  channels: ChannelHealthItem[];
  quality_flags: string[];
  created_at: string;
}

export interface CandidateRecommendation {
  channel: number;
  band: string;
  width_mhz: number;
  score: number;
  health_label: string;
  confidence: string;
  is_dfs: boolean;
  cta_label: string;
}

export interface ChannelRecommendation {
  schema_version: string;
  recommendation_id: string;
  session_id: string;
  input_snapshot_id: string;
  algorithm_version: string;
  band: string;
  channel_width_mhz: number;
  primary: CandidateRecommendation;
  alternatives: CandidateRecommendation[];
  confidence: ConfidenceLevel;
  confidence_reasons: string[];
  missing_evidence: string[];
  supporting_factors: string[];
  counter_signals: string[];
  conflict_detected: boolean;
  observation_window: ObservationWindowInfo;
  freshness_status: string;
  created_at: string;
}

export interface MetricDelta {
  before?: number | null;
  after?: number | null;
  delta?: number | null;
  improved?: boolean | null;
}

export interface ChannelValidationRun {
  validation_id: string;
  session_id: string;
  baseline_recommendation_id?: string | null;
  marker_id?: string | null;
  marker_label?: string | null;
  before_window: Record<string, any>;
  after_window: Record<string, any>;
  metric_deltas: Record<string, MetricDelta>;
  summary_label: string;
  created_at: string;
}
