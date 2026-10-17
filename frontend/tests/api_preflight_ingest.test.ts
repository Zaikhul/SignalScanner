import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient } from "@/lib/apiClient";

describe("apiClient Preflight and Ingest Methods", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("should send POST request with Authorization header on runPreflight", async () => {
    const mockResponse = {
      overall_status: "READY",
      collector_id: "col_default",
      mode: "wifi",
      timestamp: "2026-10-08T12:00:00Z",
      checks: [
        { layer: "collector", name: "collector_heartbeat_liveness", status: "READY", message: "OK" },
      ],
      remediation_actions: [],
    };

    let capturedUrl = "";
    let capturedOptions: any = null;

    global.fetch = vi.fn().mockImplementation(async (url: string, options: any) => {
      capturedUrl = url;
      capturedOptions = options;
      return {
        ok: true,
        status: 200,
        json: async () => mockResponse,
      };
    });

    const res = await apiClient.runPreflight("col_default", "wifi");

    expect(capturedUrl).toContain("/api/v1/collectors/col_default/preflight?mode=wifi");
    expect(capturedOptions.method).toBe("POST");
    expect(capturedOptions.headers["Authorization"]).toContain("Bearer");
    expect(res.overall_status).toBe("READY");
  });

  it("should send POST request with Authorization header on ingestBatch", async () => {
    const mockBatchPayload = {
      schema_version: "1.0",
      session_id: "ses_123",
      collector_id: "col_default",
      source_type: "simulator",
      sequence_from: 1,
      sequence_to: 1,
      measurements: [],
    };

    let capturedUrl = "";
    let capturedOptions: any = null;

    global.fetch = vi.fn().mockImplementation(async (url: string, options: any) => {
      capturedUrl = url;
      capturedOptions = options;
      return {
        ok: true,
        status: 200,
        json: async () => ({ ingested_count: 0, rejected_count: 0 }),
      };
    });

    const res = await apiClient.ingestBatch(mockBatchPayload);

    expect(capturedUrl).toContain("/api/v1/collector-ingest/batches");
    expect(capturedOptions.method).toBe("POST");
    expect(capturedOptions.headers["Authorization"]).toContain("Bearer");
    expect(capturedOptions.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(capturedOptions.body)).toEqual(mockBatchPayload);
    expect(res.ingested_count).toBe(0);
  });
});
