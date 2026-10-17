import { GeoEndpoint, GeoRelation, Severity } from "./webScanTypes";

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface ProjectedPoint {
  x: number;
  y: number;
  z: number;
  visible: boolean;
}

export interface ProjectedArcSegment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  zAvg: number;
}

export interface EndpointCluster {
  clusterKey: string;
  latitude: number;
  longitude: number;
  primaryEndpoint: GeoEndpoint;
  endpoints: GeoEndpoint[];
  relations: GeoRelation[];
  highestSeverity: Severity | "none";
  totalRecords: number;
  totalFindings: number;
}

export type GlobeColorMode = "severity" | "http_status" | "latency";

export type TriageStatus =
  | "open"
  | "in_progress"
  | "false_positive"
  | "accepted_risk"
  | "resolved";

export interface SeveritySource {
  id: string;
  severity: Severity;
  triage_status?: TriageStatus | null;
}

/**
 * Builds the finding-id -> severity map that drives globe alarm colouring,
 * honouring the F09 triage contract: findings dismissed as `false_positive` or
 * closed as `resolved` must NOT raise the severity of a relation or endpoint.
 * `accepted_risk` and `in_progress` remain active (the risk is acknowledged,
 * not disproven).
 */
export function buildActiveFindingSeverityMap(
  findings: SeveritySource[]
): Map<string, Severity> {
  const map = new Map<string, Severity>();
  for (const f of findings) {
    if (f.triage_status === "false_positive" || f.triage_status === "resolved") {
      continue;
    }
    map.set(f.id, f.severity);
  }
  return map;
}

const DEG_TO_RAD = Math.PI / 180;

/**
 * Mengonversi koordinat (latitude, longitude) dalam derajat menjadi vektor satuan 3D.
 */
export function latLonToUnitVec3(latDeg: number, lonDeg: number): Vec3 {
  const phi = latDeg * DEG_TO_RAD;
  const lambda = lonDeg * DEG_TO_RAD;
  return {
    x: Math.cos(phi) * Math.sin(lambda),
    y: -Math.sin(phi),
    z: Math.cos(phi) * Math.cos(lambda),
  };
}

/**
 * Memutar vektor 3D berdasarkan sudut rotasi kamera (rotX = pitch, rotY = yaw)
 * dan memproyeksikannya ke koordinat layar Canvas 2D.
 */
export function projectVec3ToScreen(
  v: Vec3,
  radius: number,
  cx: number,
  cy: number,
  rotX: number,
  rotY: number,
  altitudeOffset: number = 0
): ProjectedPoint {
  const r = radius + altitudeOffset;
  const x0 = v.x * r;
  const y0 = v.y * r;
  const z0 = v.z * r;

  // Rotasi sumbu Y (Yaw / Longitude)
  const cosY = Math.cos(rotY);
  const sinY = Math.sin(rotY);
  const x1 = x0 * cosY + z0 * sinY;
  const z1 = -x0 * sinY + z0 * cosY;

  // Rotasi sumbu X (Pitch / Latitude)
  const cosX = Math.cos(rotX);
  const sinX = Math.sin(rotX);
  const y2 = y0 * cosX - z1 * sinX;
  const z2 = y0 * sinX + z1 * cosX;

  return {
    x: cx + x1,
    y: cy + y2,
    z: z2,
    visible: z2 > -0.02 * radius,
  };
}

/**
 * Proyeksi langsung dari (lat, lon) ke koordinat layar.
 */
export function projectLatLonToScreen(
  latDeg: number,
  lonDeg: number,
  radius: number,
  cx: number,
  cy: number,
  rotX: number,
  rotY: number,
  altitudeOffset: number = 0
): ProjectedPoint {
  const unit = latLonToUnitVec3(latDeg, lonDeg);
  return projectVec3ToScreen(unit, radius, cx, cy, rotX, rotY, altitudeOffset);
}

/**
 * Spherical Linear Interpolation (Slerp) antara dua titik di permukaan bola (Great-Circle path).
 */
export function slerpUnitVec3(v1: Vec3, v2: Vec3, t: number): { point: Vec3; omega: number } {
  const dot = Math.max(-1, Math.min(1, v1.x * v2.x + v1.y * v2.y + v1.z * v2.z));
  const omega = Math.acos(dot);

  if (omega < 1e-5) {
    return { point: { ...v1 }, omega: 0 };
  }

  const sinOmega = Math.sin(omega);
  const w1 = Math.sin((1 - t) * omega) / sinOmega;
  const w2 = Math.sin(t * omega) / sinOmega;

  const x = w1 * v1.x + w2 * v2.x;
  const y = w1 * v1.y + w2 * v2.y;
  const z = w1 * v1.z + w2 * v2.z;
  const len = Math.hypot(x, y, z) || 1;

  return {
    point: { x: x / len, y: y / len, z: z / len },
    omega,
  };
}

/**
 * Membangun titik-titik kurva busur Great-Circle 3D beserta profil ketinggian parabolik.
 */
export function buildGreatCircleArcPoints(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
  radius: number,
  cx: number,
  cy: number,
  rotX: number,
  rotY: number,
  segments: number = 36
): ProjectedPoint[] {
  const v1 = latLonToUnitVec3(lat1, lon1);
  const v2 = latLonToUnitVec3(lat2, lon2);
  const dot = Math.max(-1, Math.min(1, v1.x * v2.x + v1.y * v2.y + v1.z * v2.z));
  const omega = Math.acos(dot);

  // Ketinggian puncak busur proporsional terhadap jarak sudut geodesik
  const maxAltitude = Math.min(radius * 0.34, Math.max(radius * 0.06, radius * 0.24 * (omega / Math.PI)));

  const points: ProjectedPoint[] = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const { point } = slerpUnitVec3(v1, v2, t);
    // Profil parabolik halus: 4 * t * (1 - t) bernilai 1.0 di t = 0.5
    const alt = 4 * t * (1 - t) * maxAltitude;
    points.push(projectVec3ToScreen(point, radius, cx, cy, rotX, rotY, alt));
  }
  return points;
}

/**
 * Menghitung jarak Euclidean terpendek dari titik kursor (px, py) ke segmen garis [(x1, y1), (x2, y2)].
 * Digunakan untuk Arc Hit-Testing ketika pengguna mengarahkan mouse atau mengklik jalur busur.
 */
export function distancePointToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);

  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq));
  const projX = x1 + t * dx;
  const projY = y1 + t * dy;
  return Math.hypot(px - projX, py - projY);
}

/**
 * Menentukan warna utama dan warna pendaran (glow) untuk suatu relasi berdasarkan mode warna aktif.
 */
export function resolveRelationVisualStyle(
  rel: GeoRelation,
  mode: GlobeColorMode,
  findingSeveritiesById?: Map<string, Severity>
): {
  stroke: string;
  glow: string;
  badgeText: string;
  isDashed: boolean;
  lineWidth: number;
  pulseSpeed: number;
} {
  const recordCount = Math.max(1, rel.record_count || 1);
  const lineWidth = Math.min(4.2, 1.5 + Math.log2(1 + recordCount) * 0.55);
  const isDashed = rel.relation_basis !== "observed_http";

  // Hitung keparahan tertinggi dari atribut relasi atau lookup map findings
  const rankMap: Record<string, number> = {
    critical: 5,
    high: 4,
    medium: 3,
    low: 2,
    info: 1,
    none: 0,
  };
  let highestSev: Severity | "none" = rel.highest_severity || "none";
  if (highestSev === "none" && findingSeveritiesById && rel.linked_finding_ids.length > 0) {
    for (const fid of rel.linked_finding_ids) {
      const s = findingSeveritiesById.get(fid);
      if (s && rankMap[s] > rankMap[highestSev]) {
        highestSev = s;
      }
    }
  }

  // Kecepatan partikel berdasarkan latensi rata-rata (default 0.35 siklus/detik)
  const avgLatency = rel.avg_latency_ms;
  const pulseSpeed =
    avgLatency == null
      ? 0.38
      : avgLatency < 150
      ? 0.55
      : avgLatency <= 600
      ? 0.35
      : 0.18;

  if (mode === "severity") {
    switch (highestSev) {
      case "critical":
        return { stroke: "#f43f5e", glow: "rgba(244, 63, 94, 0.55)", badgeText: "CRITICAL", isDashed, lineWidth, pulseSpeed };
      case "high":
        return { stroke: "#f97316", glow: "rgba(249, 115, 22, 0.50)", badgeText: "HIGH RISK", isDashed, lineWidth, pulseSpeed };
      case "medium":
        return { stroke: "#eab308", glow: "rgba(234, 179, 8, 0.45)", badgeText: "MEDIUM", isDashed, lineWidth, pulseSpeed };
      case "low":
        return { stroke: "#38bdf8", glow: "rgba(56, 189, 248, 0.45)", badgeText: "LOW", isDashed, lineWidth, pulseSpeed };
      default:
        return { stroke: "#10b981", glow: "rgba(16, 185, 129, 0.45)", badgeText: "CLEAN", isDashed, lineWidth, pulseSpeed };
    }
  }

  if (mode === "http_status") {
    const codes = rel.status_codes || [];
    if (codes.some((c) => c >= 500)) {
      return { stroke: "#ef4444", glow: "rgba(239, 68, 68, 0.5)", badgeText: "HTTP 5xx", isDashed, lineWidth, pulseSpeed };
    }
    if (codes.some((c) => c >= 400 && c < 500)) {
      return { stroke: "#f59e0b", glow: "rgba(245, 158, 11, 0.5)", badgeText: "HTTP 4xx", isDashed, lineWidth, pulseSpeed };
    }
    if (codes.some((c) => c >= 200 && c < 300)) {
      return { stroke: "#a8d94f", glow: "rgba(168, 217, 79, 0.5)", badgeText: "HTTP 2xx", isDashed, lineWidth, pulseSpeed };
    }
    if (codes.some((c) => c >= 300 && c < 400)) {
      return { stroke: "#38bdf8", glow: "rgba(56, 189, 248, 0.45)", badgeText: "HTTP 3xx", isDashed, lineWidth, pulseSpeed };
    }
    return { stroke: "#71717a", glow: "rgba(113, 113, 122, 0.35)", badgeText: "NO HTTP", isDashed: true, lineWidth, pulseSpeed };
  }

  // Mode === "latency"
  if (avgLatency == null) {
    return { stroke: "#60a5fa", glow: "rgba(96, 165, 250, 0.4)", badgeText: "N/A ms", isDashed, lineWidth, pulseSpeed };
  }
  if (avgLatency > 600) {
    return { stroke: "#f43f5e", glow: "rgba(244, 63, 94, 0.5)", badgeText: `${Math.round(avgLatency)} ms`, isDashed, lineWidth, pulseSpeed };
  }
  if (avgLatency >= 150) {
    return { stroke: "#f59e0b", glow: "rgba(245, 158, 11, 0.45)", badgeText: `${Math.round(avgLatency)} ms`, isDashed, lineWidth, pulseSpeed };
  }
  return { stroke: "#10b981", glow: "rgba(16, 185, 129, 0.45)", badgeText: `${Math.round(avgLatency)} ms`, isDashed, lineWidth, pulseSpeed };
}

/**
 * Mengelompokkan endpoint target yang memiliki koordinat lokasi berdekatan (toleransi 0.25 derajat)
 * untuk mencegah tumpang tindih pin dan label pada kanvas.
 */
export function clusterTargetEndpoints(
  relations: GeoRelation[],
  endpointsById: Map<string, GeoEndpoint>,
  findingSeveritiesById?: Map<string, Severity>
): EndpointCluster[] {
  const clusters = new Map<string, EndpointCluster>();
  const rankMap: Record<string, number> = {
    critical: 5,
    high: 4,
    medium: 3,
    low: 2,
    info: 1,
    none: 0,
  };

  for (const rel of relations) {
    const ep = endpointsById.get(rel.target_endpoint_id);
    if (!ep?.location) continue;

    // Pembulatan grid 0.25 derajat (~27 km) untuk pengelompokan kota/data center yang sama
    const latKey = (Math.round(ep.location.latitude * 4) / 4).toFixed(2);
    const lonKey = (Math.round(ep.location.longitude * 4) / 4).toFixed(2);
    const key = `${latKey}:${lonKey}`;

    let highestSev: Severity | "none" = rel.highest_severity || "none";
    if (highestSev === "none" && findingSeveritiesById) {
      for (const fid of rel.linked_finding_ids) {
        const s = findingSeveritiesById.get(fid);
        if (s && rankMap[s] > rankMap[highestSev]) highestSev = s;
      }
    }

    const existing = clusters.get(key);
    if (!existing) {
      clusters.set(key, {
        clusterKey: key,
        latitude: ep.location.latitude,
        longitude: ep.location.longitude,
        primaryEndpoint: ep,
        endpoints: [ep],
        relations: [rel],
        highestSeverity: highestSev,
        totalRecords: rel.record_count,
        totalFindings: rel.linked_finding_ids.length,
      });
    } else {
      if (!existing.endpoints.some((e) => e.id === ep.id)) {
        existing.endpoints.push(ep);
      }
      existing.relations.push(rel);
      existing.totalRecords += rel.record_count;
      existing.totalFindings += rel.linked_finding_ids.length;
      if (rankMap[highestSev] > rankMap[existing.highestSeverity]) {
        existing.highestSeverity = highestSev;
      }
    }
  }

  return Array.from(clusters.values());
}
