import { create } from "zustand";
import {
  CollectorDevice,
  MeasurementEvent,
  QualityFlags,
  ScanMode,
  ScanSession,
  SessionMarker,
  TargetSummary,
  WifiAssociation,
  LanHost,
  ChannelHealthSnapshot,
  ChannelRecommendation,
  ChannelHealthItem,
  ChannelValidationRun,
} from "./types";

interface ScannerStore {
  // Mode & Selection
  mode: ScanMode;
  setMode: (mode: ScanMode) => void;

  // Active Collector
  selectedCollectorId: string;
  setSelectedCollectorId: (id: string) => void;
  collectors: CollectorDevice[];
  setCollectors: (collectors: CollectorDevice[]) => void;

  // Active Session
  activeSession: ScanSession | null;
  setActiveSession: (session: ScanSession | null) => void;
  updateSessionStatus: (status: ScanSession["status"]) => void;
  addMarkerToSession: (marker: SessionMarker) => void;

  // Real-time targets & measurements
  selectedTargetId: string | null;
  setSelectedTargetId: (id: string | null) => void;
  targets: TargetSummary[];
  setTargets: (targets: TargetSummary[]) => void;
  upsertTarget: (target: TargetSummary) => void;

  // Synchronized Filter & Presentation State (PRD v1.2.1)
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  viewMode: "ssid" | "bssid";
  setViewMode: (viewMode: "ssid" | "bssid") => void;
  showExpiredHistory: boolean;
  setShowExpiredHistory: (show: boolean) => void;
  filterBand: string | null;
  setFilterBand: (band: string | null) => void;

  // Scan Activity Watchdog (PRD 13.6)
  lastActivityTimestamp: number;
  recordScanActivity: () => void;

  // Real-time measurement cache & quality telemetry
  measurementsByTarget: Record<string, MeasurementEvent[]>;
  latestFftBins: number[];
  latestFftCenterFreq: number;
  latestQuality: QualityFlags | null;
  latestTraceId: string | null;
  addBatchMeasurements: (events: MeasurementEvent[], envelopeMeta?: { trace_id?: string }) => void;

  // Real-time connection & health
  connectionState: "connected" | "reconnecting" | "disconnected" | "idle";
  setConnectionState: (state: "connected" | "reconnecting" | "disconnected" | "idle") => void;
  lastSequence: number;
  setLastSequence: (seq: number) => void;
  snapshotWatermark: number;
  setSnapshotWatermark: (seq: number) => void;
  processedMeasurementKeys: Set<string>;
  droppedFrames: number;
  incrementDroppedFrames: () => void;

  // UI modal states
  inspectorOpen: boolean;
  setInspectorOpen: (open: boolean) => void;
  markerModalOpen: boolean;
  setMarkerModalOpen: (open: boolean) => void;
  preflightModalOpen: boolean;
  setPreflightModalOpen: (open: boolean) => void;
  provenanceModalOpen: boolean;
  setProvenanceModalOpen: (open: boolean) => void;
  simulationMode: boolean;
  setSimulationMode: (sim: boolean) => void;

  // WiFi Association & LAN Host Inventory (PRD v1.1)
  activeAssociation: WifiAssociation | null;
  setActiveAssociation: (assoc: WifiAssociation | null) => void;
  updateAssociationState: (state: WifiAssociation["state"], extra?: Partial<WifiAssociation>) => void;
  lanHosts: LanHost[];
  setLanHosts: (hosts: LanHost[]) => void;
  upsertLanHost: (host: LanHost) => void;
  credentialModalOpen: boolean;
  setCredentialModalOpen: (open: boolean) => void;
  targetToAssociate: TargetSummary | null;
  setTargetToAssociate: (target: TargetSummary | null) => void;
  adapterConflictNotice: string | null;
  setAdapterConflictNotice: (notice: string | null) => void;

  // Channel Health & Recommendations (v1.2)
  channelHealthSnapshot: ChannelHealthSnapshot | null;
  setChannelHealthSnapshot: (snapshot: ChannelHealthSnapshot | null) => void;
  latestRecommendation: ChannelRecommendation | null;
  setLatestRecommendation: (rec: ChannelRecommendation | null) => void;
  channelValidations: ChannelValidationRun[];
  setChannelValidations: (validations: ChannelValidationRun[]) => void;
  addChannelValidation: (val: ChannelValidationRun) => void;
  selectedObservationWindowSec: number;
  setSelectedObservationWindowSec: (sec: number) => void;
  evidenceDrawerOpen: boolean;
  setEvidenceDrawerOpen: (open: boolean) => void;
  selectedEvidenceChannel: ChannelHealthItem | null;
  setSelectedEvidenceChannel: (item: ChannelHealthItem | null) => void;
  validationModalOpen: boolean;
  setValidationModalOpen: (open: boolean) => void;

  // Reset
  resetLiveState: () => void;
}

export const useScannerStore = create<ScannerStore>((set, get) => ({
  mode: "wifi",
  setMode: (mode) => set({ mode, selectedTargetId: null }),

  selectedCollectorId: "col_default",
  setSelectedCollectorId: (selectedCollectorId) => set({ selectedCollectorId }),
  collectors: [],
  setCollectors: (collectors) => set({ collectors }),

  activeSession: null,
  setActiveSession: (activeSession) =>
    set((state) => {
      // If switching to a different session or starting fresh, clean target & stream state
      if (!activeSession || !state.activeSession || activeSession.id !== state.activeSession.id) {
        return {
          activeSession,
          targets: [],
          measurementsByTarget: {},
          latestFftBins: [],
          selectedTargetId: null,
          lastSequence: 0,
          snapshotWatermark: 0,
          processedMeasurementKeys: new Set(),
          droppedFrames: 0,
          latestQuality: null,
          latestTraceId: null,
          searchQuery: "",
          filterBand: null,
          showExpiredHistory: false,
          lastActivityTimestamp: 0,
        };
      }
      return { activeSession };
    }),
  updateSessionStatus: (status) =>
    set((state) =>
      state.activeSession
        ? { activeSession: { ...state.activeSession, status } }
        : {}
    ),
  addMarkerToSession: (marker) =>
    set((state) =>
      state.activeSession
        ? {
            activeSession: {
              ...state.activeSession,
              markers: [...state.activeSession.markers, marker],
            },
          }
        : {}
    ),

  selectedTargetId: null,
  setSelectedTargetId: (selectedTargetId) =>
    set({ selectedTargetId, inspectorOpen: selectedTargetId !== null }),
  targets: [],
  setTargets: (targets) => set({ targets }),
  upsertTarget: (target) =>
    set((state) => {
      const idx = state.targets.findIndex((t) => t.target_id === target.target_id);
      if (idx >= 0) {
        const next = [...state.targets];
        next[idx] = { ...next[idx], ...target };
        return { targets: next };
      }
      return { targets: [target, ...state.targets] };
    }),

  // Synchronized Filter & Presentation State (PRD v1.2.1)
  searchQuery: "",
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  viewMode: "ssid",
  setViewMode: (viewMode) => set({ viewMode }),
  showExpiredHistory: false,
  setShowExpiredHistory: (showExpiredHistory) => set({ showExpiredHistory }),
  filterBand: null,
  setFilterBand: (filterBand) => set({ filterBand }),

  // Scan Activity Watchdog (PRD 13.6)
  lastActivityTimestamp: 0,
  recordScanActivity: () => set({ lastActivityTimestamp: Date.now() }),

  measurementsByTarget: {},
  latestFftBins: [],
  latestFftCenterFreq: 433920000,
  latestQuality: null,
  latestTraceId: null,
  addBatchMeasurements: (events, envelopeMeta) =>
    set((state) => {
      const updated = { ...state.measurementsByTarget };
      let newFftBins = state.latestFftBins;
      let newCenterFreq = state.latestFftCenterFreq;
      let latestQ = state.latestQuality;
      const targetMap = new Map(state.targets.map((t) => [t.target_id, { ...t }]));
      const seenKeys = new Set(state.processedMeasurementKeys || []);

      for (const ev of events) {
        const key = `${ev.sequence}:${ev.target_id}`;
        if (seenKeys.has(key)) {
          continue; // Already processed this measurement in this session
        }
        seenKeys.add(key);
        if (seenKeys.size > 5000) {
          const firstKey = seenKeys.values().next().value;
          if (firstKey) seenKeys.delete(firstKey);
        }

        if (ev.quality) {
          latestQ = ev.quality;
        }
        // Update measurements by target (keep max 100 per target in memory)
        const prev = updated[ev.target_id] || [];
        const nextMeas = [...prev, ev];
        if (nextMeas.length > 100) nextMeas.shift();
        updated[ev.target_id] = nextMeas;

        // Radio FFT bins
        if (ev.radio?.fft_bins && ev.radio.fft_bins.length > 0) {
          newFftBins = ev.radio.fft_bins;
          if (ev.radio.center_frequency_hz) {
            newCenterFreq = ev.radio.center_frequency_hz;
          }
        }

        // Update target summary
        const existing = targetMap.get(ev.target_id);
        const signalVal = ev.signal.smoothed_value ?? ev.signal.value;
        const observedAt = ev.quality?.observed_at || ev.captured_at;
        const outOfScale = signalVal < -100 ? "low" : signalVal > -30 ? "high" : null;

        // Is this event already accounted for in the snapshot watermark?
        const isHistoricalToSnapshot = state.snapshotWatermark > 0 && ev.sequence <= state.snapshotWatermark;

        if (existing) {
          const prevSig = existing.latest_signal;
          if (prevSig !== undefined && prevSig !== null && Number.isFinite(prevSig)) {
            existing.previous_signal = prevSig;
            existing.delta_signal = Math.round((signalVal - prevSig) * 10) / 10;
          }
          existing.last_seen = ev.captured_at;
          existing.observed_at = observedAt;
          existing.latest_signal = signalVal;
          existing.out_of_scale = outOfScale;
          if (!isHistoricalToSnapshot) {
            existing.sample_count += 1;
            existing.min_signal = Math.min(existing.min_signal, signalVal);
            existing.max_signal = Math.max(existing.max_signal, signalVal);
          }
          if (ev.signal.snr !== undefined) existing.avg_snr = ev.signal.snr;
          if (ev.display_name) existing.display_name = ev.display_name;
          if (ev.radio?.channel) existing.channel = ev.radio.channel;
          if (ev.radio?.band) existing.band = ev.radio.band;
          if (ev.quality?.freshness) existing.freshness = ev.quality.freshness;
          if (ev.quality?.source_method) existing.source_method = ev.quality.source_method;
        } else {
          targetMap.set(ev.target_id, {
            target_id: ev.target_id,
            display_name: ev.display_name || "Unknown Target",
            mode: ev.mode,
            first_seen: ev.captured_at,
            last_seen: ev.captured_at,
            observed_at: observedAt,
            sample_count: 1,
            latest_signal: signalVal,
            previous_signal: null,
            delta_signal: null,
            out_of_scale: outOfScale,
            unit: ev.signal.unit,
            min_signal: signalVal,
            max_signal: signalVal,
            median_signal: signalVal,
            avg_snr: ev.signal.snr ?? null,
            channel: ev.radio?.channel ?? null,
            band: ev.radio?.band ?? null,
            freshness: ev.quality?.freshness || "fresh",
            source_method: ev.quality?.source_method || "unknown",
            is_pinned: false,
            extra: ev.extra_metadata,
          });
        }
      }

      return {
        measurementsByTarget: updated,
        latestFftBins: newFftBins,
        latestFftCenterFreq: newCenterFreq,
        latestQuality: latestQ,
        latestTraceId: envelopeMeta?.trace_id || state.latestTraceId,
        lastActivityTimestamp: Date.now(),
        targets: Array.from(targetMap.values()).sort(
          (a, b) => b.latest_signal - a.latest_signal
        ),
        processedMeasurementKeys: seenKeys,
      };
    }),

  connectionState: "idle",
  setConnectionState: (connectionState) => set({ connectionState }),
  lastSequence: 0,
  setLastSequence: (lastSequence) => set({ lastSequence }),
  snapshotWatermark: 0,
  setSnapshotWatermark: (snapshotWatermark) => set({ snapshotWatermark }),
  processedMeasurementKeys: new Set<string>(),
  droppedFrames: 0,
  incrementDroppedFrames: () =>
    set((state) => ({ droppedFrames: state.droppedFrames + 1 })),

  inspectorOpen: false,
  setInspectorOpen: (inspectorOpen) => set({ inspectorOpen }),
  markerModalOpen: false,
  setMarkerModalOpen: (markerModalOpen) => set({ markerModalOpen }),
  preflightModalOpen: false,
  setPreflightModalOpen: (preflightModalOpen) => set({ preflightModalOpen }),
  provenanceModalOpen: false,
  setProvenanceModalOpen: (provenanceModalOpen) => set({ provenanceModalOpen }),
  simulationMode: false,
  setSimulationMode: (simulationMode) => set({ simulationMode }),

  // WiFi Association & LAN Host Inventory
  activeAssociation: null,
  setActiveAssociation: (activeAssociation) => set({ activeAssociation }),
  updateAssociationState: (state, extra) =>
    set((s) => ({
      activeAssociation: s.activeAssociation
        ? { ...s.activeAssociation, state, ...(extra || {}) }
        : null,
    })),
  lanHosts: [],
  setLanHosts: (lanHosts) => set({ lanHosts }),
  upsertLanHost: (host) =>
    set((s) => {
      const idx = s.lanHosts.findIndex(
        (h) => (h.mac_hash && h.mac_hash === host.mac_hash) || h.ip === host.ip
      );
      if (idx >= 0) {
        const next = [...s.lanHosts];
        next[idx] = { ...next[idx], ...host };
        return { lanHosts: next };
      }
      return { lanHosts: [...s.lanHosts, host] };
    }),
  credentialModalOpen: false,
  setCredentialModalOpen: (credentialModalOpen) => set({ credentialModalOpen }),
  targetToAssociate: null,
  setTargetToAssociate: (targetToAssociate) => set({ targetToAssociate }),
  adapterConflictNotice: null,
  setAdapterConflictNotice: (adapterConflictNotice) => set({ adapterConflictNotice }),

  // Channel Health & Recommendations (v1.2)
  channelHealthSnapshot: null,
  setChannelHealthSnapshot: (channelHealthSnapshot) => set({ channelHealthSnapshot }),
  latestRecommendation: null,
  setLatestRecommendation: (latestRecommendation) => set({ latestRecommendation }),
  channelValidations: [],
  setChannelValidations: (channelValidations) => set({ channelValidations }),
  addChannelValidation: (val) =>
    set((s) => ({ channelValidations: [val, ...s.channelValidations] })),
  selectedObservationWindowSec: 300,
  setSelectedObservationWindowSec: (selectedObservationWindowSec) =>
    set({ selectedObservationWindowSec }),
  evidenceDrawerOpen: false,
  setEvidenceDrawerOpen: (evidenceDrawerOpen) => set({ evidenceDrawerOpen }),
  selectedEvidenceChannel: null,
  setSelectedEvidenceChannel: (selectedEvidenceChannel) => set({ selectedEvidenceChannel }),
  validationModalOpen: false,
  setValidationModalOpen: (validationModalOpen) => set({ validationModalOpen }),

  resetLiveState: () =>
    set({
      targets: [],
      measurementsByTarget: {},
      latestFftBins: [],
      selectedTargetId: null,
      lastSequence: 0,
      droppedFrames: 0,
      latestQuality: null,
      latestTraceId: null,
      activeAssociation: null,
      lanHosts: [],
      targetToAssociate: null,
      adapterConflictNotice: null,
      channelHealthSnapshot: null,
      latestRecommendation: null,
      evidenceDrawerOpen: false,
      selectedEvidenceChannel: null,
      searchQuery: "",
      filterBand: null,
      showExpiredHistory: false,
      lastActivityTimestamp: 0,
    }),
}));
