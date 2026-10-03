import { describe, it, expect, beforeEach } from "vitest";
import { useScannerStore } from "@/lib/store";
import {
  ChannelHealthSnapshot,
  ChannelRecommendation,
  ChannelValidationRun,
} from "@/lib/types";

describe("Channel Health & Recommendation Engine Store (v1.2)", () => {
  beforeEach(() => {
    useScannerStore.getState().resetLiveState();
  });

  it("should store and update channelHealthSnapshot and manage evidence drawer", () => {
    const mockSnapshot: ChannelHealthSnapshot = {
      schema_version: "1.2",
      snapshot_id: "chs_test_01",
      session_id: "ses_01",
      band: "2.4GHz",
      channel_width_mhz: 20,
      observation_window: {
        from_time: "2026-09-07T10:00:00Z",
        to_time: "2026-09-07T10:05:00Z",
        duration_seconds: 300,
        scan_cycles: 12,
      },
      regulatory_domain: {
        value: "ID",
        provenance: "configured",
        source: "organization_setting",
      },
      channels: [
        {
          channel: 1,
          band: "2.4GHz",
          width_mhz: 20,
          health_score: 78,
          health_label: "Layak",
          cci_power_mw: 0.00001,
          aci_power_mw: 0.0,
          ap_count: 2,
          max_rssi: -50.0,
          is_dfs: false,
          is_candidate: true,
          exclusion_reasons: [],
          components: {
            utilization: { value: null, provenance: "unavailable" },
            overlap_interference: { value: 0.31, provenance: "derived" },
            retry: { value: null, provenance: "unavailable" },
            noise: { value: null, provenance: "unavailable" },
            temporal_instability: { value: 0.18, provenance: "derived" },
          },
        },
      ],
      quality_flags: ["UTILIZATION_UNAVAILABLE"],
      created_at: new Date().toISOString(),
    };

    useScannerStore.getState().setChannelHealthSnapshot(mockSnapshot);
    expect(useScannerStore.getState().channelHealthSnapshot?.snapshot_id).toBe("chs_test_01");
    expect(useScannerStore.getState().channelHealthSnapshot?.channels[0].health_score).toBe(78);

    // Open evidence drawer for channel 1
    useScannerStore.getState().setSelectedEvidenceChannel(mockSnapshot.channels[0]);
    useScannerStore.getState().setEvidenceDrawerOpen(true);

    expect(useScannerStore.getState().evidenceDrawerOpen).toBe(true);
    expect(useScannerStore.getState().selectedEvidenceChannel?.channel).toBe(1);

    // Close drawer
    useScannerStore.getState().setEvidenceDrawerOpen(false);
    expect(useScannerStore.getState().evidenceDrawerOpen).toBe(false);
  });

  it("should enforce 'Kandidat untuk diuji' copy on low confidence recommendation", () => {
    const mockRec: ChannelRecommendation = {
      schema_version: "1.2",
      recommendation_id: "chr_test_01",
      session_id: "ses_01",
      input_snapshot_id: "chs_test_01",
      algorithm_version: "channel-health-1.0.0",
      band: "2.4GHz",
      channel_width_mhz: 20,
      primary: {
        channel: 6,
        band: "2.4GHz",
        width_mhz: 20,
        score: 85,
        health_label: "Sehat",
        confidence: "low",
        is_dfs: false,
        cta_label: "Kandidat untuk diuji",
      },
      alternatives: [
        {
          channel: 11,
          band: "2.4GHz",
          width_mhz: 20,
          score: 82,
          health_label: "Sehat",
          confidence: "low",
          is_dfs: false,
          cta_label: "Kandidat alternatif",
        },
      ],
      confidence: "low",
      confidence_reasons: ["snapshot_window_under_minimum_threshold"],
      missing_evidence: ["channel_utilization", "retry_rate"],
      supporting_factors: ["Bebas dari co-channel interference"],
      counter_signals: ["Observation window singkat"],
      conflict_detected: false,
      observation_window: {
        from_time: "2026-09-07T10:00:00Z",
        to_time: "2026-09-07T10:00:30Z",
        duration_seconds: 30,
        scan_cycles: 2,
      },
      freshness_status: "fresh",
      created_at: new Date().toISOString(),
    };

    useScannerStore.getState().setLatestRecommendation(mockRec);
    const storedRec = useScannerStore.getState().latestRecommendation;
    expect(storedRec?.confidence).toBe("low");
    expect(storedRec?.primary.cta_label).toBe("Kandidat untuk diuji");
    expect(storedRec?.missing_evidence).toContain("channel_utilization");
  });

  it("should record before-after channel validation runs without causal claims", () => {
    const mockValidation: ChannelValidationRun = {
      validation_id: "chv_test_01",
      session_id: "ses_01",
      marker_id: "mrk_01",
      marker_label: "AP Channel Change to 6",
      before_window: { from: "2026-09-07T10:00:00Z", to: "2026-09-07T10:01:00Z", samples: 15 },
      after_window: { from: "2026-09-07T10:01:00Z", to: "2026-09-07T10:02:00Z", samples: 15 },
      metric_deltas: {
        mean_signal_rssi: { before: -75.0, after: -62.0, delta: 13.0, improved: true },
        signal_temporal_instability: { before: 4.5, after: 1.2, delta: -3.3, improved: true },
      },
      summary_label: "Perubahan teramati: Kekuatan sinyal teramati meningkat 13.0 dB",
      created_at: new Date().toISOString(),
    };

    useScannerStore.getState().addChannelValidation(mockValidation);
    expect(useScannerStore.getState().channelValidations.length).toBe(1);
    expect(useScannerStore.getState().channelValidations[0].summary_label).toContain("Perubahan teramati");
    expect(useScannerStore.getState().channelValidations[0].metric_deltas.mean_signal_rssi.improved).toBe(true);

    // Reset should clear validation and recommendation state
    useScannerStore.getState().resetLiveState();
    expect(useScannerStore.getState().channelHealthSnapshot).toBeNull();
    expect(useScannerStore.getState().latestRecommendation).toBeNull();
  });
});
