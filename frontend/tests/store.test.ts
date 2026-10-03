import { describe, it, expect, beforeEach } from "vitest";
import { useScannerStore } from "@/lib/store";
import { MeasurementEvent } from "@/lib/types";

describe("useScannerStore", () => {
  beforeEach(() => {
    useScannerStore.getState().resetLiveState();
  });

  it("should initialize with default mode and empty targets", () => {
    const state = useScannerStore.getState();
    expect(state.mode).toBe("wifi");
    expect(state.targets).toEqual([]);
    expect(state.selectedTargetId).toBeNull();
  });

  it("should change scan mode", () => {
    useScannerStore.getState().setMode("bluetooth");
    expect(useScannerStore.getState().mode).toBe("bluetooth");

    useScannerStore.getState().setMode("radio");
    expect(useScannerStore.getState().mode).toBe("radio");
  });

  it("should process and aggregate batch measurements", () => {
    const sampleEvent: MeasurementEvent = {
      schema_version: "1.0",
      session_id: "ses_test",
      collector_id: "col_test",
      sequence: 1,
      captured_at: new Date().toISOString(),
      mode: "wifi",
      target_id: "hmac:test123456",
      display_name: "Test_SSID_5G",
      signal: {
        value: -55.0,
        unit: "dBm",
        noise: -92.0,
        snr: 37.0,
      },
      radio: {
        channel: 36,
        band: "5GHz",
      },
      quality: {
        calibrated: false,
        permission_limited: false,
        throttled: false,
      },
    };

    useScannerStore.getState().addBatchMeasurements([sampleEvent]);

    const targets = useScannerStore.getState().targets;
    expect(targets.length).toBe(1);
    expect(targets[0].target_id).toBe("hmac:test123456");
    expect(targets[0].display_name).toBe("Test_SSID_5G");
    expect(targets[0].latest_signal).toBe(-55.0);
    expect(targets[0].channel).toBe(36);
    expect(targets[0].band).toBe("5GHz");
  });
});
