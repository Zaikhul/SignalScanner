import {
  Collector,
  MeasurementEvent,
  ScanMode,
  ScanSession,
  SessionMarker,
  SessionStatus,
  TargetSummary,
  WifiAssociation,
  LanHost,
  ChannelHealthSnapshot,
  ChannelRecommendation,
  ChannelValidationRun,
  SessionProvenanceManifest,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export const API_AUTH_TOKEN = process.env.NEXT_PUBLIC_API_AUTH_TOKEN || "";
export const LOCAL_COLLECTOR_TOKEN = process.env.NEXT_PUBLIC_LOCAL_COLLECTOR_TOKEN || "";
export const LOCAL_COLLECTOR_URL = process.env.NEXT_PUBLIC_COLLECTOR_URL || "http://127.0.0.1:8001";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
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

export const apiClient = {
  // Collectors
  async listCollectors(): Promise<Collector[]> {
    return request<Collector[]>("/api/v1/collectors");
  },

  async getCollector(id: string): Promise<Collector> {
    return request<Collector>(`/api/v1/collectors/${id}`);
  },

  async runDiagnostic(id: string, commandType: string = "check_adapters"): Promise<any> {
    return request<any>(`/api/v1/collectors/${id}/commands/diagnose`, {
      method: "POST",
      body: JSON.stringify({ collector_id: id, command_type: commandType }),
    });
  },

  // Sessions
  async createSession(payload: {
    name?: string;
    mode: ScanMode;
    collector_id: string;
    source_type?: "collector" | "simulator";
    sample_interval_ms?: number;
    duration_seconds?: number;
    radio_config?: any;
    tags?: string[];
  }): Promise<ScanSession> {
    return request<ScanSession>("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getSession(id: string): Promise<ScanSession> {
    return request<ScanSession>(`/api/v1/sessions/${id}`);
  },

  async listSessions(params: {
    mode?: ScanMode;
    status?: SessionStatus;
    page?: number;
    page_size?: number;
  } = {}): Promise<{ items: ScanSession[]; total: number; page: number; total_pages: number }> {
    const query = new URLSearchParams();
    if (params.mode) query.set("mode", params.mode);
    if (params.status) query.set("status", params.status);
    if (params.page) query.set("page", params.page.toString());
    if (params.page_size) query.set("page_size", params.page_size.toString());

    return request<{ items: ScanSession[]; total: number; page: number; total_pages: number }>(
      `/api/v1/sessions?${query.toString()}`
    );
  },

  async startSession(id: string): Promise<ScanSession> {
    return request<ScanSession>(`/api/v1/sessions/${id}/start`, { method: "POST" });
  },

  async pauseSession(id: string): Promise<ScanSession> {
    return request<ScanSession>(`/api/v1/sessions/${id}/pause`, { method: "POST" });
  },

  async resumeSession(id: string): Promise<ScanSession> {
    return request<ScanSession>(`/api/v1/sessions/${id}/resume`, { method: "POST" });
  },

  async stopSession(id: string): Promise<ScanSession> {
    return request<ScanSession>(`/api/v1/sessions/${id}/stop`, { method: "POST" });
  },

  async addMarker(sessionId: string, label: string, notes?: string): Promise<SessionMarker> {
    return request<SessionMarker>(`/api/v1/sessions/${sessionId}/markers`, {
      method: "POST",
      body: JSON.stringify({ label, notes }),
    });
  },

  // Targets
  async listTargets(sessionId: string): Promise<TargetSummary[]> {
    return request<TargetSummary[]>(`/api/v1/sessions/${sessionId}/targets`);
  },

  async togglePinTarget(sessionId: string, targetId: string): Promise<{ is_pinned: boolean }> {
    return request<{ is_pinned: boolean }>(
      `/api/v1/sessions/${sessionId}/targets/${encodeURIComponent(targetId)}/pin`,
      { method: "POST" }
    );
  },

  // Measurements
  async queryMeasurements(
    sessionId: string,
    params: { target_id?: string; after_sequence?: number; after_id?: string | number; limit?: number } = {}
  ): Promise<any[]> {
    const query = new URLSearchParams();
    if (params.target_id) query.set("target_id", params.target_id);
    if (params.after_sequence !== undefined) query.set("after_sequence", params.after_sequence.toString());
    if (params.after_id !== undefined) query.set("after_id", params.after_id.toString());
    if (params.limit) query.set("limit", params.limit.toString());

    return request<any[]>(`/api/v1/sessions/${sessionId}/measurements?${query.toString()}`);
  },

  // Exports
  async createExport(sessionId: string, format: "json" | "csv" = "json"): Promise<any> {
    return request<any>(`/api/v1/sessions/${sessionId}/exports`, {
      method: "POST",
      body: JSON.stringify({ format, include_raw_samples: true }),
    });
  },

  getDownloadUrl(exportId: string): string {
    return `${API_BASE}/api/v1/exports/${exportId}/download`;
  },

  async getSessionManifest(sessionId: string): Promise<SessionProvenanceManifest> {
    return request<SessionProvenanceManifest>(`/api/v1/sessions/${sessionId}/manifest`);
  },

  async downloadExportFile(exportId: string): Promise<void> {
    const url = `${API_BASE}/api/v1/exports/${exportId}/download`;
    const headers: Record<string, string> = {};
    if (API_AUTH_TOKEN) {
      headers["Authorization"] = `Bearer ${API_AUTH_TOKEN}`;
    }
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`Export download failed with status ${res.status}`);
    }
    const disposition = res.headers.get("Content-Disposition");
    let filename = `export_${exportId}.csv`;
    if (disposition && disposition.includes("filename=")) {
      filename = disposition.split("filename=")[1].replace(/["']/g, "").trim();
    }
    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(blobUrl);
    document.body.removeChild(a);
  },

  async downloadEvidenceBundle(sessionId: string): Promise<void> {
    const url = `${API_BASE}/api/v1/sessions/${sessionId}/evidence-bundle`;
    const headers: Record<string, string> = {};
    if (API_AUTH_TOKEN) {
      headers["Authorization"] = `Bearer ${API_AUTH_TOKEN}`;
    }
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`Evidence bundle download failed with status ${res.status}`);
    }
    const disposition = res.headers.get("Content-Disposition");
    let filename = `evidence_bundle_${sessionId}.zip`;
    if (disposition && disposition.includes("filename=")) {
      filename = disposition.split("filename=")[1].replace(/["']/g, "").trim();
    }
    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(blobUrl);
    document.body.removeChild(a);
  },

  // WiFi Association & LAN Host Inventory (PRD v1.1)
  async createAssociation(sessionId: string, payload: {
    target_id: string;
    security_hint?: string;
    ssid?: string;
    bssid_hash?: string;
  }): Promise<WifiAssociation> {
    return request<WifiAssociation>(`/api/v1/sessions/${sessionId}/associations`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async connectAssociation(associationId: string, payload: {
    target_id: string;
    security_hint: string;
    authorized_use_confirmed: boolean;
    save_profile?: boolean;
    timeout_seconds?: number;
  }): Promise<WifiAssociation> {
    // Zero-Secret Contract: NO password field is sent to backend REST API!
    return request<WifiAssociation>(`/api/v1/associations/${associationId}/connect`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async sendDirectAssociate(payload: {
    association_id: string;
    target_id: string;
    ssid?: string;
    security_type: string;
    password?: string;
    save_profile: boolean;
    timeout_seconds: number;
  }): Promise<any> {
    // Sends credentials directly to local collector agent (port 8001) in-memory
    const localUrl = `${LOCAL_COLLECTOR_URL}/api/v1/collector/associate`;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (LOCAL_COLLECTOR_TOKEN) {
      headers["X-Local-Token"] = LOCAL_COLLECTOR_TOKEN;
      headers["Authorization"] = `Bearer ${LOCAL_COLLECTOR_TOKEN}`;
    }

    const res = await fetch(localUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let errorDetail = res.statusText;
      try {
        const errJson = await res.json();
        errorDetail = errJson.detail || errorDetail;
      } catch {
        // Ignore JSON parse error
      }
      throw new Error(`Direct Associate Error [${res.status}]: ${errorDetail}`);
    }

    return await res.json();
  },

  async disconnectAssociation(associationId: string, forgetProfile: boolean = true): Promise<WifiAssociation> {
    // Also signal local collector agent directly if available
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (LOCAL_COLLECTOR_TOKEN) {
        headers["X-Local-Token"] = LOCAL_COLLECTOR_TOKEN;
        headers["Authorization"] = `Bearer ${LOCAL_COLLECTOR_TOKEN}`;
      }
      await fetch(`${LOCAL_COLLECTOR_URL}/api/v1/collector/disconnect`, {
        method: "POST",
        headers,
        body: JSON.stringify({ forget_profile: forgetProfile }),
      });
    } catch {
      // Ignore if local agent unreachable
    }

    return request<WifiAssociation>(`/api/v1/associations/${associationId}/disconnect`, {
      method: "POST",
      body: JSON.stringify({ forget_profile: forgetProfile }),
    });
  },

  async refreshInventory(associationId: string): Promise<any> {
    return request<any>(`/api/v1/associations/${associationId}/inventory/refresh`, {
      method: "POST",
    });
  },

  async getAssociation(associationId: string): Promise<WifiAssociation> {
    return request<WifiAssociation>(`/api/v1/associations/${associationId}`);
  },

  async getAssociationHosts(associationId: string, page: number = 1, pageSize: number = 100): Promise<{
    association_id: string;
    items: LanHost[];
    total: number;
  }> {
    return request<{ association_id: string; items: LanHost[]; total: number }>(
      `/api/v1/associations/${associationId}/hosts?page=${page}&page_size=${pageSize}`
    );
  },

  async exportInventory(associationId: string, format: "json" | "csv" = "json"): Promise<{
    format: string;
    checksum_sha256: string;
    content: string;
    total_hosts: number;
    generated_at: string;
  }> {
    return request<any>(`/api/v1/associations/${associationId}/exports?format=${format}`, {
      method: "POST",
    });
  },

  // Channel Health (v1.2)
  async getChannelHealth(sessionId: string, band: string = "2.4GHz"): Promise<ChannelHealthSnapshot> {
    return request<ChannelHealthSnapshot>(`/api/v1/sessions/${sessionId}/channel-health?band=${encodeURIComponent(band)}`);
  },

  async getLatestRecommendation(sessionId: string): Promise<ChannelRecommendation> {
    return request<ChannelRecommendation>(`/api/v1/sessions/${sessionId}/channel-recommendations/latest`);
  },

  async listChannelValidations(sessionId: string): Promise<ChannelValidationRun[]> {
    return request<ChannelValidationRun[]>(`/api/v1/sessions/${sessionId}/channel-validations`);
  },

  async evaluateChannelRecommendation(sessionId: string, payload: {
    band: string;
    channel_width_mhz?: number;
    observation_window_sec?: number;
    regulatory_domain?: string;
  }): Promise<ChannelRecommendation> {
    return request<ChannelRecommendation>(`/api/v1/sessions/${sessionId}/channel-recommendations/evaluate`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async triggerChannelValidation(sessionId: string, payload: {
    marker_id?: string | null;
    before_window_sec?: number;
    after_window_sec?: number;
  }): Promise<ChannelValidationRun> {
    return request<ChannelValidationRun>(`/api/v1/sessions/${sessionId}/channel-validations`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
