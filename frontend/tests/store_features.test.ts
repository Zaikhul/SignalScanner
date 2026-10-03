import { describe, it, expect, beforeEach } from "vitest";
import { useScannerStore } from "@/lib/store";
import { MeasurementEvent, ScanSession } from "@/lib/types";

describe("Store Features & WiFi Inconsistency Defenses", () => {
  beforeEach(() => {
    useScannerStore.getState().resetLiveState();
    useScannerStore.getState().setActiveSession(null);
  });

  it("should reset targets and stream buffer when session changes to prevent data leakage", () => {
    const session1: ScanSession = {
      id: "ses_01",
      name: "Session 1",
      mode: "wifi",
      collector_id: "col_host_01",
      source_type: "collector",
      status: "active",
      config: {},
      tags: [],
      created_at: new Date().toISOString(),
      markers: [],
      summary: { total_samples: 0, unique_targets: 0, duration_seconds: 0 },
    };

    useScannerStore.getState().setActiveSession(session1);

    // Ingest data into session 1
    const event1: MeasurementEvent = {
      schema_version: "1.0",
      session_id: "ses_01",
      collector_id: "col_host_01",
      sequence: 1,
      captured_at: new Date().toISOString(),
      mode: "wifi",
      target_id: "hmac:ap01",
      display_name: "WiFi_Session_1",
      signal: { value: -50.0, unit: "dBm" },
      quality: { calibrated: false, permission_limited: false, throttled: false },
    };
    useScannerStore.getState().addBatchMeasurements([event1]);

    expect(useScannerStore.getState().targets.length).toBe(1);
    expect(useScannerStore.getState().targets[0].display_name).toBe("WiFi_Session_1");

    // Switch to session 2
    const session2: ScanSession = {
      id: "ses_02",
      name: "Session 2",
      mode: "wifi",
      collector_id: "col_host_01",
      source_type: "collector",
      status: "active",
      config: {},
      tags: [],
      created_at: new Date().toISOString(),
      markers: [],
      summary: { total_samples: 0, unique_targets: 0, duration_seconds: 0 },
    };

    useScannerStore.getState().setActiveSession(session2);

    // Targets must be immediately emptied for session 2
    expect(useScannerStore.getState().targets.length).toBe(0);
    expect(Object.keys(useScannerStore.getState().measurementsByTarget).length).toBe(0);
    expect(useScannerStore.getState().lastSequence).toBe(0);
  });

  it("should correctly distinguish multiple BSSIDs under the same SSID name", () => {
    const session: ScanSession = {
      id: "ses_dualband",
      name: "DualBand Scan",
      mode: "wifi",
      collector_id: "col_host_01",
      source_type: "collector",
      status: "active",
      config: {},
      tags: [],
      created_at: new Date().toISOString(),
      markers: [],
      summary: { total_samples: 0, unique_targets: 0, duration_seconds: 0 },
    };

    useScannerStore.getState().setActiveSession(session);

    // 2.4 GHz AP
    const bssid24: MeasurementEvent = {
      schema_version: "1.0",
      session_id: "ses_dualband",
      collector_id: "col_host_01",
      sequence: 1,
      captured_at: new Date().toISOString(),
      mode: "wifi",
      target_id: "hmac:bssid_24ghz",
      display_name: "Jaya-Network",
      signal: { value: -48.0, unit: "dBm" },
      radio: { channel: 6, band: "2.4GHz" },
      quality: { calibrated: true, permission_limited: false, throttled: false },
    };

    // 5 GHz AP (same SSID)
    const bssid50: MeasurementEvent = {
      schema_version: "1.0",
      session_id: "ses_dualband",
      collector_id: "col_host_01",
      sequence: 1,
      captured_at: new Date().toISOString(),
      mode: "wifi",
      target_id: "hmac:bssid_5ghz",
      display_name: "Jaya-Network",
      signal: { value: -58.0, unit: "dBm" },
      radio: { channel: 36, band: "5GHz" },
      quality: { calibrated: true, permission_limited: false, throttled: false },
    };

    useScannerStore.getState().addBatchMeasurements([bssid24, bssid50]);

    const targets = useScannerStore.getState().targets;
    // BSSID granularity: 2 distinct target entities stored
    expect(targets.length).toBe(2);
    expect(targets.map((t) => t.target_id)).toContain("hmac:bssid_24ghz");
    expect(targets.map((t) => t.target_id)).toContain("hmac:bssid_5ghz");
  });
});
