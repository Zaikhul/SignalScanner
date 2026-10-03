import { FreshnessState, ScanMode, TargetSummary } from "./types";

export const RSSI_MIN_SCALE = -100;
export const RSSI_MAX_SCALE = -30;
export const ANNULUS_INNER_PERCENT = 8;
export const ANNULUS_OUTER_PERCENT = 86;

/**
 * Algoritma hash31-v1 deterministik untuk menghitung sudut polar (0 - 359 derajat).
 * Sesuai PRD Bagian 13.5 B:
 * - h = 0
 * - iterasi unit kode UTF-16: h = int32(31 * h + codeUnit)
 * - theta = abs(h) mod 360
 * Posisi 0° berada di atas (jam 12) dan meningkat searah jarum jam.
 */
export function getStableAngleHash31(targetId: string): number {
  let h = 0;
  for (let i = 0; i < targetId.length; i++) {
    h = (Math.imul(31, h) + targetId.charCodeAt(i)) | 0;
  }
  return Math.abs(h) % 360;
}

export interface RadialMappingResult {
  rawSignal: number;
  clampedSignal: number;
  normalizedU: number; // 0 (-30 dBm, kuat/pusat) s/d 1 (-100 dBm, lemah/luar)
  outOfScale: "low" | "high" | null;
  isPlottable: boolean;
  reasonUnplottable?: string;
}

/**
 * Pemetaan radial sesuai PRD Bagian 13.5 A:
 * v_clamped = clamp(v, -100, -30)
 * u = (-30 - v_clamped) / 70
 * r = r_inner + u * (r_outer - r_inner)
 */
export function computeRadialMapping(
  signalValue: number | null | undefined,
  unit: string = "dBm"
): RadialMappingResult {
  if (
    signalValue === null ||
    signalValue === undefined ||
    typeof signalValue !== "number" ||
    !Number.isFinite(signalValue)
  ) {
    return {
      rawSignal: NaN,
      clampedSignal: RSSI_MIN_SCALE,
      normalizedU: 1,
      outOfScale: null,
      isPlottable: false,
      reasonUnplottable: "Nilai sinyal unavailable atau non-finite (NaN)",
    };
  }

  // Cek kecocokan unit
  if (unit !== "dBm" && unit !== "dBFS") {
    return {
      rawSignal: signalValue,
      clampedSignal: RSSI_MIN_SCALE,
      normalizedU: 1,
      outOfScale: null,
      isPlottable: false,
      reasonUnplottable: `Unit '${unit}' tidak valid untuk skala polar dBm/dBFS`,
    };
  }

  const outOfScale: "low" | "high" | null =
    signalValue < RSSI_MIN_SCALE
      ? "low"
      : signalValue > RSSI_MAX_SCALE
      ? "high"
      : null;

  const clampedSignal = Math.max(
    RSSI_MIN_SCALE,
    Math.min(RSSI_MAX_SCALE, signalValue)
  );
  // -30 dBm -> u = 0; -100 dBm -> u = 1; -65 dBm -> u = 0.5
  const normalizedU = (-30 - clampedSignal) / 70;

  return {
    rawSignal: signalValue,
    clampedSignal,
    normalizedU,
    outOfScale,
    isPlottable: true,
  };
}

/**
 * Evaluasi kesegaran (freshness) target sesuai PRD Bagian 13.6:
 * - WiFi: Fresh <= 30s, Stale > 30s s/d 60s, Expired > 60s
 * - BLE: Fresh <= 3s, Stale > 3s s/d 10s, Expired > 10s
 * - Radio: Mengikuti baseline WiFi (<= 30s)
 */
export function evaluateTargetFreshness(
  target: {
    last_seen?: string;
    observed_at?: string | null;
    first_seen?: string;
    quality?: { age_ms?: number | null; freshness?: FreshnessState };
  },
  nowMs: number,
  mode: ScanMode = "wifi"
): {
  freshness: FreshnessState;
  ageMs: number;
  ageSeconds: number;
  isStale: boolean;
  isExpired: boolean;
} {
  const timestampStr = target.observed_at || target.last_seen;
  if (!timestampStr) {
    return {
      freshness: "unknown",
      ageMs: Infinity,
      ageSeconds: Infinity,
      isStale: true,
      isExpired: true,
    };
  }

  const seenTime = new Date(timestampStr).getTime();
  if (isNaN(seenTime) || seenTime <= 0) {
    return {
      freshness: "unknown",
      ageMs: Infinity,
      ageSeconds: Infinity,
      isStale: true,
      isExpired: true,
    };
  }

  const elapsedClient = Math.max(0, nowMs - seenTime);
  const ageMs =
    target.quality?.age_ms !== undefined && target.quality?.age_ms !== null
      ? Math.max(target.quality.age_ms, elapsedClient)
      : elapsedClient;
  const ageSeconds = Math.round(ageMs / 1000);

  // Jika backend secara eksplisit menandai freshness unknown
  if (target.quality?.freshness === "unknown") {
    return {
      freshness: "unknown",
      ageMs,
      ageSeconds,
      isStale: true,
      isExpired: false,
    };
  }

  if (mode === "bluetooth") {
    if (ageMs <= 3000) {
      return { freshness: "fresh", ageMs, ageSeconds, isStale: false, isExpired: false };
    }
    if (ageMs <= 10000) {
      return { freshness: "stale", ageMs, ageSeconds, isStale: true, isExpired: false };
    }
    return { freshness: "expired", ageMs, ageSeconds, isStale: true, isExpired: true };
  } else {
    // WiFi / Radio
    if (ageMs <= 30000) {
      return { freshness: "fresh", ageMs, ageSeconds, isStale: false, isExpired: false };
    }
    if (ageMs <= 60000) {
      return { freshness: "stale", ageMs, ageSeconds, isStale: true, isExpired: false };
    }
    return { freshness: "expired", ageMs, ageSeconds, isStale: true, isExpired: true };
  }
}

/**
 * Evaluasi aktivitas pemindaian untuk watchdog sweep (PRD Bagian 13.6).
 * Sweep hanya berputar jika:
 * 1. Status sesi adalah "active"
 * 2. Koneksi WebSocket aktif ("connected")
 * 3. Tidak ada jeda/konflik adapter
 * 4. Bukti aktivitas scan diterima dalam batas watchdog max(10000ms, 3 * actual_interval_ms)
 */
export function isScanActivelyMoving(params: {
  sessionStatus?: string | null;
  connectionState: string;
  hasAdapterConflict: boolean;
  lastActivityTimestamp: number;
  actualIntervalMs?: number | null;
  nowMs: number;
}): boolean {
  if (params.sessionStatus !== "active") return false;
  if (params.connectionState !== "connected") return false;
  if (params.hasAdapterConflict) return false;
  if (params.lastActivityTimestamp <= 0) return false;

  const interval = params.actualIntervalMs || 1000;
  const timeoutLimit = Math.max(10000, 3 * interval);
  const elapsed = params.nowMs - params.lastActivityTimestamp;

  return elapsed <= timeoutLimit;
}
