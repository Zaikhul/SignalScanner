import { describe, it, expect, beforeEach, vi } from "vitest";
import { useScannerStore } from "@/lib/store";
import { MeasurementEvent } from "@/lib/types";

describe("WebSocket Session Stream State Logic", () => {
  beforeEach(() => {
    useScannerStore.getState().resetLiveState();
    useScannerStore.getState().setConnectionState("idle");
  });

  it("should keep connectionState as connected during multiple sequential batches without resetting", () => {
    useScannerStore.getState().setConnectionState("connected");

    // Simulate batch 1
    const batch1: MeasurementEvent = {
      schema_version: "1.0",
      session_id: "ses_live_test",
      collector_id: "col_host_01",
      sequence: 1,
      captured_at: new Date().toISOString(),
      mode: "wifi",
      target_id: "hmac:ap01",
      display_name: "AP_Test_1",
      signal: { value: -50.0, unit: "dBm" },
      quality: { calibrated: false, permission_limited: false, throttled: false },
    };

    useScannerStore.getState().setLastSequence(1);
    useScannerStore.getState().addBatchMeasurements([batch1]);

    expect(useScannerStore.getState().connectionState).toBe("connected");
    expect(useScannerStore.getState().lastSequence).toBe(1);
    expect(useScannerStore.getState().targets.length).toBe(1);

    // Simulate batch 2 (sequence 2)
    const batch2: MeasurementEvent = {
      schema_version: "1.0",
      session_id: "ses_live_test",
      collector_id: "col_host_01",
      sequence: 2,
      captured_at: new Date().toISOString(),
      mode: "wifi",
      target_id: "hmac:ap01",
      display_name: "AP_Test_1",
      signal: { value: -48.0, unit: "dBm" },
      quality: { calibrated: false, permission_limited: false, throttled: false },
    };

    useScannerStore.getState().setLastSequence(2);
    useScannerStore.getState().addBatchMeasurements([batch2]);

    expect(useScannerStore.getState().connectionState).toBe("connected");
    expect(useScannerStore.getState().lastSequence).toBe(2);
    expect(useScannerStore.getState().targets[0].latest_signal).toBe(-48.0);
    expect(useScannerStore.getState().targets[0].sample_count).toBe(2);
  });
});
