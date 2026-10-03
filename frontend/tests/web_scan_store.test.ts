import { describe, it, expect, beforeEach } from "vitest";
import { useWebScanStore } from "@/lib/webScanStore";
import { ScanFinding, ScanJob } from "@/lib/webScanTypes";

describe("useWebScanStore", () => {
  beforeEach(() => {
    useWebScanStore.getState().reset();
  });

  it("should initialize with default empty state", () => {
    const state = useWebScanStore.getState();
    expect(state.activeJob).toBeNull();
    expect(state.snapshot).toBeNull();
    expect(state.findings).toEqual([]);
    expect(state.isScanning).toBe(false);
    expect(state.progressPercent).toBe(0);
  });

  it("should activate job and set scanning flag", () => {
    const sampleJob: ScanJob = {
      id: "scan_123",
      schema_version: "web_scan.v1",
      tenant_id: "test_tenant",
      created_by: "tester",
      target_display: "https://example.com",
      requested_configuration: {} as any,
      effective_configuration: {} as any,
      status: "scanning",
      version: 1,
      created_at: new Date().toISOString(),
      snapshot_sequence: 0,
      scope_hash: "hash_123",
      scope_revision: 1,
    };

    useWebScanStore.getState().setActiveJob(sampleJob);
    expect(useWebScanStore.getState().activeJob?.id).toBe("scan_123");
    expect(useWebScanStore.getState().isScanning).toBe(true);

    useWebScanStore.getState().setProgress(45, "security_headers");
    expect(useWebScanStore.getState().progressPercent).toBe(45);
    expect(useWebScanStore.getState().currentModule).toBe("security_headers");
  });

  it("should upsert findings and deduplicate by fingerprint", () => {
    const finding1: ScanFinding = {
      id: "f_1",
      scan_id: "scan_123",
      module: "headers",
      check_id: "headers.csp",
      category: "security_headers",
      severity: "high",
      severity_reason: "Missing CSP",
      confidence: "confirmed_configuration",
      title: "Missing Content-Security-Policy Header",
      description: "CSP missing",
      remediation: "Add CSP",
      evidence: {
        url_display: "https://example.com",
        observation_ids: [],
        header_names: [],
        excerpts: [],
        control_request_ids: [],
        body_truncated: false,
      },
      fingerprint: "headers:csp:example.com",
      occurrence_count: 1,
      assessment_version: "web_scan.v1",
      first_seen_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(),
    };

    useWebScanStore.getState().upsertFinding(finding1);
    expect(useWebScanStore.getState().findings.length).toBe(1);

    // Upsert duplicate with same fingerprint but higher count
    const finding1Updated: ScanFinding = {
      ...finding1,
      occurrence_count: 2,
    };

    useWebScanStore.getState().upsertFinding(finding1Updated);
    expect(useWebScanStore.getState().findings.length).toBe(1);
    expect(useWebScanStore.getState().findings[0].occurrence_count).toBe(2);
  });

  it("should safely handle jobs with undefined or missing status", () => {
    // Malformed job without status
    const malformedJob = {
      id: "scan_malformed",
      target_display: "https://example.com",
    } as any;

    expect(() => {
      useWebScanStore.getState().setActiveJob(malformedJob);
    }).not.toThrow();

    expect(useWebScanStore.getState().isScanning).toBe(false);
    expect(useWebScanStore.getState().activeJob?.id).toBe("scan_malformed");

    // Malformed snapshot without status
    const malformedSnapshot = {
      job: malformedJob,
      result: {} as any,
      errors: [],
    } as any;

    expect(() => {
      useWebScanStore.getState().setSnapshot(malformedSnapshot);
    }).not.toThrow();

    expect(useWebScanStore.getState().isScanning).toBe(false);
  });

  it("should set progressPercent to 100 on completed status and sanitize progress", () => {
    const store = useWebScanStore.getState();
    store.setProgress(NaN as any, "recon");
    expect(useWebScanStore.getState().progressPercent).toBe(0);

    store.setProgress(50, "recon");
    expect(useWebScanStore.getState().progressPercent).toBe(50);

    const completedJob: ScanJob = {
      id: "scan_done",
      schema_version: "web_scan.v1",
      tenant_id: "test",
      created_by: "tester",
      target_display: "https://example.com",
      requested_configuration: {} as any,
      effective_configuration: {} as any,
      status: "completed",
      version: 2,
      created_at: new Date().toISOString(),
      snapshot_sequence: 10,
      scope_hash: "hash",
      scope_revision: 1,
    };

    store.setActiveJob(completedJob);
    expect(useWebScanStore.getState().isScanning).toBe(false);
    expect(useWebScanStore.getState().progressPercent).toBe(100);
  });

  it("should accurately track findings by module including recon and stress", () => {
    const store = useWebScanStore.getState();

    const reconFinding: ScanFinding = {
      id: "f_recon",
      scan_id: "scan_v47",
      module: "recon",
      check_id: "recon.server_banner",
      category: "information_disclosure",
      severity: "info",
      severity_reason: "Banner disclosed",
      confidence: "confirmed_configuration",
      title: "Server Banner Disclosed",
      description: "Server header",
      remediation: "Mask header",
      evidence: { url_display: "https://example.com", body_truncated: false } as any,
      fingerprint: "recon:banner:example.com",
      occurrence_count: 1,
      assessment_version: "web_scan.v1",
      first_seen_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(),
    };

    const stressFinding: ScanFinding = {
      id: "f_stress",
      scan_id: "scan_v47",
      module: "stress",
      check_id: "stress.bounded_load_test",
      category: "service_resilience",
      severity: "info",
      severity_reason: "Target stable under load",
      confidence: "confirmed_configuration",
      title: "Bounded Load Resilience Benchmark: Target Stable",
      description: "Target sustained load",
      remediation: "None required",
      evidence: { url_display: "https://example.com", body_truncated: false } as any,
      fingerprint: "stress:stable:example.com",
      occurrence_count: 1,
      assessment_version: "web_scan.v1",
      first_seen_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(),
    };

    store.upsertFinding(reconFinding);
    store.upsertFinding(stressFinding);

    const findings = useWebScanStore.getState().findings;
    expect(findings.length).toBe(2);

    const byModule: Record<string, number> = {};
    for (const f of findings) {
      byModule[f.module] = (byModule[f.module] || 0) + 1;
    }

    expect(byModule["recon"]).toBe(1);
    expect(byModule["stress"]).toBe(1);
  });
});

