import {
  Capabilities,
  CreateScanRequest,
  Page,
  ScanFinding,
  ScanJob,
  ScanObservation,
  ScanSnapshot,
  WebScanEvent,
} from "./webScanTypes";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export const API_AUTH_TOKEN = process.env.NEXT_PUBLIC_API_AUTH_TOKEN || "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (API_AUTH_TOKEN && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${API_AUTH_TOKEN}`;
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errorDetail = res.statusText;
    try {
      const errJson = await res.json();
      errorDetail = errJson.detail || errorDetail;
    } catch {
      // Ignore JSON parse error
    }
    throw new Error(`API Error [${res.status}]: ${errorDetail}`);
  }

  return res.json();
}

export const webScanApiClient = {
  async getCapabilities(): Promise<Capabilities> {
    return request<Capabilities>("/api/v1/web-scans/capabilities");
  },

  async createScan(req: CreateScanRequest, idempotencyKey?: string): Promise<ScanJob> {
    const headers: Record<string, string> = {};
    if (idempotencyKey) {
      headers["Idempotency-Key"] = idempotencyKey;
    }
    return request<ScanJob>("/api/v1/web-scans", {
      method: "POST",
      headers,
      body: JSON.stringify(req),
    });
  },

  async listScans(
    status?: string,
    limit: number = 50,
    offset: number = 0
  ): Promise<Page<ScanJob>> {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    params.append("limit", String(limit));
    params.append("offset", String(offset));
    return request<Page<ScanJob>>(`/api/v1/web-scans?${params.toString()}`);
  },

  async getScan(scanId: string): Promise<ScanJob> {
    return request<ScanJob>(`/api/v1/web-scans/${scanId}`);
  },

  async cancelScan(scanId: string): Promise<ScanJob> {
    return request<ScanJob>(`/api/v1/web-scans/${scanId}/cancel`, {
      method: "POST",
    });
  },

  async getSnapshot(scanId: string): Promise<ScanSnapshot> {
    return request<ScanSnapshot>(`/api/v1/web-scans/${scanId}/snapshot`);
  },

  async listFindings(
    scanId: string,
    params: {
      severity?: string;
      module?: string;
      search?: string;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<Page<ScanFinding>> {
    const query = new URLSearchParams();
    if (params.severity) query.append("severity", params.severity);
    if (params.module) query.append("module", params.module);
    if (params.search) query.append("search", params.search);
    query.append("limit", String(params.limit || 50));
    query.append("offset", String(params.offset || 0));
    return request<Page<ScanFinding>>(`/api/v1/web-scans/${scanId}/findings?${query.toString()}`);
  },

  async listObservations(
    scanId: string,
    params: { kind?: string; limit?: number; offset?: number } = {}
  ): Promise<Page<ScanObservation>> {
    const query = new URLSearchParams();
    if (params.kind) query.append("kind", params.kind);
    query.append("limit", String(params.limit || 50));
    query.append("offset", String(params.offset || 0));
    return request<Page<ScanObservation>>(`/api/v1/web-scans/${scanId}/observations?${query.toString()}`);
  },

  async getEvents(
    scanId: string,
    afterSequence: number = 0,
    limit: number = 200
  ): Promise<WebScanEvent[]> {
    return request<WebScanEvent[]>(
      `/api/v1/web-scans/${scanId}/events?after_sequence=${afterSequence}&limit=${limit}`
    );
  },

  async createStreamTicket(scanId: string): Promise<{ ticket: string; expires_in_seconds: number }> {
    return request<{ ticket: string; expires_in_seconds: number }>(
      `/api/v1/web-scans/${scanId}/stream-ticket`,
      { method: "POST" }
    );
  },

  async downloadExport(
    scanId: string,
    format: "json" | "v2_json" | "txt" | "sql"
  ): Promise<{ blob: Blob; filename: string; checksum: string }> {
    const url = `${API_BASE}/api/v1/web-scans/${scanId}/export?format=${format}`;
    const headers: Record<string, string> = {};
    if (API_AUTH_TOKEN) {
      headers["Authorization"] = `Bearer ${API_AUTH_TOKEN}`;
    }

    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`Export failed with HTTP ${res.status}`);
    }

    const disp = res.headers.get("Content-Disposition") || "";
    let filename = `scan_report_${scanId.slice(0, 8)}.${format === "v2_json" ? "json" : format}`;
    const match = disp.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
    const checksum = res.headers.get("X-Checksum-SHA256") || "";
    const blob = await res.blob();
    return { blob, filename, checksum };
  },
};
