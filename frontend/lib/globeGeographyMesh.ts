/**
 * globeGeographyMesh.ts
 * ----------------------------------------------------------------------------
 * Real-Earth geography tessellation for the SignalScanner 3D telemetry globe.
 *
 * Data provenance (Zero-External-Egress compliant):
 *   - Natural Earth (public domain, CC0 1.0 Universal), redistributed via the
 *     `world-atlas` npm package (ISC) and `topojson-client` (ISC).
 *   - Assets are served as *local static files* from `frontend/public/geo/`
 *     (`ne_110m_land.geojson`, `ne_110m_admin_0_countries.geojson`,
 *     `countries-50m.json`, `land-50m.json`). No CDN / tile server is ever
 *     contacted at runtime.
 *
 * Resolution characteristics (measured on the bundled files, not assumed):
 *   - 1:110m land     -> 1 FeatureCollection / 125 polygons, 126 rings,
 *                       1 interior hole ring (Caspian Sea).
 *   - 1:110m countries-> 177 features (148 Polygon + 29 MultiPolygon),
 *                       incl. the Lesotho enclave hole inside South Africa.
 *   - 1:50m           -> >1,400 polygons, separates small islands (Bali,
 *                       Bangka, Belitung, Madura, Singapore, Malta, Bahrain).
 *     Swap the files in `public/geo/` to raise resolution — no code change.
 *
 * Coordinate convention: GeoJSON `[lon, lat]` in degrees, WGS84.
 * Sphere convention:  x = cos(phi)*sin(lambda), y = sin(phi), z = cos(phi)*cos(lambda)
 * (north is +Y, lon 0 faces +Z, east is +X). Radius constants are concentric
 * shells around R_OCEAN so co-planar layers never z-fight.
 */

import * as THREE from "three";
import { feature as topoFeature } from "topojson-client";

// Radius stratification (concentric shells, see renderOrder mapping)
export const R_GLOBE = 100;
export const R_OCEAN = 100.0;
export const R_LAND = 100.32;
export const R_BORDER = 100.4;
export const R_COAST = 100.46;

/** Absolute 2D shoelace area below which a ring is a broken topological sliver. */
export const SLIVER_AREA_THRESHOLD = 1e-5;
/** Maximum angular span (degrees) of a densified ring segment. */
export const MAX_RING_SEGMENT_DEG = 2.8;
/** Maximum angular span (degrees) of a tessellated triangle edge. */
export const MAX_TRIANGLE_SPAN_DEG = 3.4;
/**
 * Hard cap on recursive spherical subdivision depth.
 * Each level halves the longest edge, so a 180 deg input edge needs ~7 levels
 * just to reach 3.4 deg; 20 leaves generous headroom for pathological slivers
 * while still bounding worst-case recursion.
 */
const MAX_SUBDIVISION_DEPTH = 20;
/** Artificial seam guard: both endpoints at the antimeridian. */
const ANTIMERIDIAN_SEAM_LON = 179.92;
/** Artificial seam guard: both endpoints on the polar closure edge. */
const POLAR_SEAM_LAT = -89.4;

const DEG_TO_RAD = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;

export type LonLat = [number, number];

export interface GeoPolygon {
  /** Exterior ring, closed (first === last), CCW, antimeridian-unwrapped. */
  exterior: LonLat[];
  /** Interior hole rings, closed, CW, antimeridian-unwrapped. */
  holes: LonLat[][];
}

export interface GlobeGeometrySet {
  land: THREE.BufferGeometry;
  coastline: THREE.BufferGeometry;
  borders?: THREE.BufferGeometry;
  stats: {
    polygons: number;
    rings: number;
    holes: number;
    landTriangles: number;
    landVertices: number;
    coastlineSegments: number;
    borderSegments: number;
    sliversRejected: number;
  };
}

// Spherical helpers

/** Converts (lat, lon) degrees to a Cartesian vector on a sphere of `radius`. */
export function latLonToVec3(latDeg: number, lonDeg: number, radius = 1): THREE.Vector3 {
  const phi = latDeg * DEG_TO_RAD;
  const lambda = lonDeg * DEG_TO_RAD;
  const cosPhi = Math.cos(phi);
  return new THREE.Vector3(
    cosPhi * Math.sin(lambda) * radius,
    Math.sin(phi) * radius,
    cosPhi * Math.cos(lambda) * radius
  );
}

/** Inverse of latLonToVec3: unit vector -> [lon, lat] in degrees. */
export function vec3ToLonLat(v: THREE.Vector3): LonLat {
  const len = v.length() || 1;
  const lat = Math.asin(Math.max(-1, Math.min(1, v.y / len))) * RAD_TO_DEG;
  const lon = Math.atan2(v.x, v.z) * RAD_TO_DEG;
  return [lon, lat];
}

/** Great-circle angular distance in degrees (periodic-safe across +-180 deg). */
export function angularDistanceDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const phi1 = lat1 * DEG_TO_RAD;
  const phi2 = lat2 * DEG_TO_RAD;
  const dPhi = (lat2 - lat1) * DEG_TO_RAD;
  const dLambda = (lon2 - lon1) * DEG_TO_RAD;
  const h =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * Math.asin(Math.min(1, Math.sqrt(Math.max(0, h)))) * RAD_TO_DEG;
}

/**
 * Geodesic midpoint of two lon/lat points (avoids the pole/longitude bias of a
 * naive coordinate average).
 */
function sphericalMidpoint(ax: number, ay: number, bx: number, by: number): LonLat {
  const va = latLonToVec3(ay, ax, 1);
  const vb = latLonToVec3(by, bx, 1);
  const sum = va.clone().add(vb);
  if (sum.lengthSq() < 1e-12) {
    return [ax, 0];
  }
  return vec3ToLonLat(sum.normalize());
}

// Ring hygiene: unwrapping, winding, sliver filtering, densification

/**
 * Shoelace signed area in squared degrees. Positive => counter-clockwise in a
 * standard (x = lon ->, y = lat ^) plane.
 */
export function computeSignedArea2D(ring: LonLat[]): number {
  if (ring.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % ring.length];
    area += x1 * y2 - x2 * y1;
  }
  return area / 2;
}

/** Drops a duplicated closing vertex so ring math never sees a zero-length edge. */
function stripClosingPoint(ring: LonLat[]): LonLat[] {
  if (ring.length < 2) return ring.slice();
  const [fx, fy] = ring[0];
  const [lx, ly] = ring[ring.length - 1];
  if (Math.abs(fx - lx) < 1e-9 && Math.abs(fy - ly) < 1e-9) {
    return ring.slice(0, -1);
  }
  return ring.slice();
}

/**
 * Removes the +-360 deg longitude jump that a ring shows when it crosses the
 * International Date Line.
 */
export function unwrapLongitudes(ring: LonLat[]): LonLat[] {
  if (ring.length === 0) return [];
  const out: LonLat[] = [];
  let offset = 0;
  // prevLon tracks the *unwrapped* previous longitude so the running offset
  // accumulates correctly across multiple date-line crossings.
  let prevLon = ring[0][0];
  let prevLat = ring[0][1];
  for (let i = 0; i < ring.length; i++) {
    const lon = ring[i][0];
    const lat = ring[i][1];

    // Polar closure edge ([180,-90] -> [-180,-90] on Antarctica): keeping the
    // 360 deg span lets densifyRing() spread it into short segments that hug
    // the pole, instead of collapsing it into a zero-length seam.
    const isPolarClosureEdge = prevLat <= -89.4 && lat <= -89.4;

    if (isPolarClosureEdge) {
      out.push([lon + offset, lat]);
      prevLon = lon + offset;
      prevLat = lat;
      continue;
    }

    const delta = lon + offset - prevLon;
    if (delta > 180) offset -= 360;
    else if (delta < -180) offset += 360;
    const unwrappedLon = lon + offset;
    out.push([unwrappedLon, lat]);
    prevLon = unwrappedLon;
    prevLat = lat;
  }
  return out;
}

/**
 * Splits over-long segments into pieces of at most maxSegmentDeg.
 */
export function densifyRing(ring: LonLat[], maxSegmentDeg: number = MAX_RING_SEGMENT_DEG): LonLat[] {
  if (ring.length < 2 || maxSegmentDeg <= 0) return ring.slice();
  const out: LonLat[] = [];
  for (let i = 0; i < ring.length - 1; i++) {
    const [lon1, lat1] = ring[i];
    const [lon2, lat2] = ring[i + 1];
    out.push([lon1, lat1]);
    const span = Math.max(Math.abs(lon2 - lon1), Math.abs(lat2 - lat1));
    if (span > maxSegmentDeg) {
      const steps = Math.ceil(span / maxSegmentDeg);
      for (let s = 1; s < steps; s++) {
        const t = s / steps;
        out.push([lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t]);
      }
    }
  }
  out.push(ring[ring.length - 1]);
  return out;
}

/**
 * Full ring preparation pipeline:
 * strip closing dup -> unwrap antimeridian -> densify -> enforce winding -> re-close.
 */
export function sanitizeAndDensifyRing(
  rawRing: LonLat[] | number[][],
  isHole: boolean,
  maxSegmentDeg: number = MAX_RING_SEGMENT_DEG
): LonLat[] {
  const ring: LonLat[] = (rawRing as number[][]).map(
    (p) => [p[0], p[1]] as LonLat
  );
  const stripped = stripClosingPoint(ring);
  if (stripped.length < 3) return [];

  const unwrapped = unwrapLongitudes(stripped);
  const densified = densifyRing(unwrapped, maxSegmentDeg);

  const area = computeSignedArea2D(densified.slice(0, -1));
  const wantsCCW = !isHole;
  const isCCW = area > 0;
  const ordered = wantsCCW === isCCW ? densified : [...densified].reverse();

  const closed = ordered.slice();
  const first = closed[0];
  const last = closed[closed.length - 1];
  if (!(Math.abs(first[0] - last[0]) < 1e-9 && Math.abs(first[1] - last[1]) < 1e-9)) {
    closed.push([first[0], first[1]]);
  }
  return closed;
}

// GeoJSON / TopoJSON extraction

type AnyGeometry = {
  type: string;
  coordinates?: unknown;
  geometries?: AnyGeometry[];
};

interface RawPolygonRings {
  rings: number[][][];
}

function collectRawPolygons(geometry: AnyGeometry | null | undefined, out: RawPolygonRings[]): void {
  if (!geometry) return;
  switch (geometry.type) {
    case "Polygon":
      out.push({ rings: (geometry.coordinates as number[][][]) ?? [] });
      break;
    case "MultiPolygon":
      for (const poly of (geometry.coordinates as number[][][][]) ?? []) {
        out.push({ rings: poly });
      }
      break;
    case "GeometryCollection":
      for (const child of geometry.geometries ?? []) collectRawPolygons(child, out);
      break;
    default:
      break;
  }
}

/**
 * Recursively extracts every polygon (with its interior hole rings) from a
 * GeoJSON FeatureCollection / Feature / GeometryCollection / Polygon /
 * MultiPolygon, or from a TopoJSON Topology.
 */
export function extractPolygonsFromGeoJSON(input: unknown): GeoPolygon[] {
  const raw: RawPolygonRings[] = [];
  const collectFromFeature = (feat: unknown): void => {
    if (!feat || typeof feat !== "object") return;
    const obj = feat as Record<string, unknown>;
    if (obj.type === "Feature") {
      collectRawPolygons(obj.geometry as AnyGeometry, raw);
    } else if (obj.type === "FeatureCollection") {
      for (const f of (obj.features as unknown[]) ?? []) collectFromFeature(f);
    } else if (typeof obj.type === "string") {
      collectRawPolygons(obj as AnyGeometry, raw);
    }
  };

  const root = input as Record<string, unknown> | null;
  if (!root || typeof root !== "object") return [];

  if (root.type === "Topology") {
    const topology = root as unknown as Parameters<typeof topoFeature>[0];
    const objects = (root.objects as Record<string, unknown>) ?? {};
    for (const key of Object.keys(objects)) {
      const converted = topoFeature(topology, objects[key] as never);
      collectFromFeature(converted);
    }
  } else {
    collectFromFeature(root);
  }

  const polygons: GeoPolygon[] = [];
  for (const { rings } of raw) {
    if (!rings.length) continue;

    const exterior = sanitizeAndDensifyRing(rings[0], false);
    if (exterior.length < 4) continue;

    const rawExteriorArea = Math.abs(
      computeSignedArea2D(stripClosingPoint((rings[0] as number[][]).map((p) => [p[0], p[1]] as LonLat)))
    );
    if (rawExteriorArea < SLIVER_AREA_THRESHOLD) continue;

    const holes: LonLat[][] = [];
    for (let i = 1; i < rings.length; i++) {
      const hole = sanitizeAndDensifyRing(rings[i], true);
      if (hole.length >= 4) holes.push(hole);
    }

    polygons.push({ exterior, holes });
  }
  return polygons;
}

// Spherical curvature tessellation

export function subdivideTriangleSpherical2D(
  ax: number,
  ay: number,
  bx: number,
  by: number,
  cx: number,
  cy: number,
  maxSpanDeg: number = MAX_TRIANGLE_SPAN_DEG,
  outCoords: number[] = []
): number[] {
  const recurse = (
    p0: LonLat,
    p1: LonLat,
    p2: LonLat,
    depth: number
  ): void => {
    const dab = angularDistanceDeg(p0[1], p0[0], p1[1], p1[0]);
    const dbc = angularDistanceDeg(p1[1], p1[0], p2[1], p2[0]);
    const dca = angularDistanceDeg(p2[1], p2[0], p0[1], p0[0]);
    const max = Math.max(dab, dbc, dca);

    if (max <= maxSpanDeg || depth >= MAX_SUBDIVISION_DEPTH) {
      outCoords.push(p0[0], p0[1], p1[0], p1[1], p2[0], p2[1]);
      return;
    }

    if (max === dab) {
      const m = sphericalMidpoint(p0[0], p0[1], p1[0], p1[1]);
      recurse(p0, m, p2, depth + 1);
      recurse(m, p1, p2, depth + 1);
    } else if (max === dbc) {
      const m = sphericalMidpoint(p1[0], p1[1], p2[0], p2[1]);
      recurse(p0, p1, m, depth + 1);
      recurse(p0, m, p2, depth + 1);
    } else {
      const m = sphericalMidpoint(p2[0], p2[1], p0[0], p0[1]);
      recurse(p0, p1, m, depth + 1);
      recurse(m, p1, p2, depth + 1);
    }
  };

  recurse([ax, ay], [bx, by], [cx, cy], 0);
  return outCoords;
}

// Geometry builders (one merged BufferGeometry per layer)

export function buildLandMeshGeometry(
  polygons: GeoPolygon[],
  radius: number = R_LAND
): THREE.BufferGeometry {
  const positions: number[] = [];
  const normals: number[] = [];

  for (const polygon of polygons) {
    const contour = polygon.exterior
      .slice(0, -1)
      .map((p) => new THREE.Vector2(p[0], p[1]));
    const holes = polygon.holes.map((ring) =>
      ring.slice(0, -1).map((p) => new THREE.Vector2(p[0], p[1]))
    );
    if (contour.length < 3) continue;

    let faces: number[][] = [];
    try {
      faces = THREE.ShapeUtils.triangulateShape(contour, holes);
    } catch {
      faces = [];
    }
    if (!faces.length) continue;

    const vertices = contour.concat(...holes);
    const subdivided: number[] = [];
    for (const [ia, ib, ic] of faces) {
      const a = vertices[ia];
      const b = vertices[ib];
      const c = vertices[ic];
      if (!a || !b || !c) continue;
      subdivideTriangleSpherical2D(a.x, a.y, b.x, b.y, c.x, c.y, MAX_TRIANGLE_SPAN_DEG, subdivided);
    }

    for (let i = 0; i < subdivided.length; i += 6) {
      let lonA = subdivided[i];
      let latA = subdivided[i + 1];
      let lonB = subdivided[i + 2];
      let latB = subdivided[i + 3];
      let lonC = subdivided[i + 4];
      let latC = subdivided[i + 5];

      const va = latLonToVec3(latA, lonA, radius);
      let vb = latLonToVec3(latB, lonB, radius);
      let vc = latLonToVec3(latC, lonC, radius);

      const edge1 = vc.clone().sub(vb);
      const edge2 = va.clone().sub(vb);
      const normal = edge1.cross(edge2);
      if (normal.dot(va) < 0) {
        const tmp = vb;
        vb = vc;
        vc = tmp;
      }

      positions.push(va.x, va.y, va.z, vb.x, vb.y, vb.z, vc.x, vc.y, vc.z);

      const na = va.clone().normalize();
      const nb = vb.clone().normalize();
      const nc = vc.clone().normalize();
      normals.push(na.x, na.y, na.z, nb.x, nb.y, nb.z, nc.x, nc.y, nc.z);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  geometry.computeBoundingSphere();
  return geometry;
}

export function isArtificialSeam(lon1: number, lat1: number, lon2: number, lat2: number): boolean {
  const onDateLine =
    Math.abs(lon1) >= ANTIMERIDIAN_SEAM_LON && Math.abs(lon2) >= ANTIMERIDIAN_SEAM_LON;
  const onPolarClosure = lat1 <= POLAR_SEAM_LAT && lat2 <= POLAR_SEAM_LAT;
  return onDateLine || onPolarClosure;
}

export function buildCoastlineGeometry(
  polygons: GeoPolygon[],
  radius: number = R_COAST
): THREE.BufferGeometry {
  const positions: number[] = [];

  const pushRing = (ring: LonLat[]): void => {
    for (let i = 0; i < ring.length - 1; i++) {
      const [lon1, lat1] = ring[i];
      const [lon2, lat2] = ring[i + 1];
      if (isArtificialSeam(lon1, lat1, lon2, lat2)) continue;
      const a = latLonToVec3(lat1, lon1, radius);
      const b = latLonToVec3(lat2, lon2, radius);
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
  };

  for (const polygon of polygons) {
    pushRing(polygon.exterior);
    for (const hole of polygon.holes) pushRing(hole);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeBoundingSphere();
  return geometry;
}

export function buildBorderGeometry(
  lines: number[][][] | GeoPolygon[],
  radius: number = R_BORDER
): THREE.BufferGeometry {
  const positions: number[] = [];

  const pushLine = (line: LonLat[]): void => {
    for (let i = 0; i < line.length - 1; i++) {
      const [lon1, lat1] = line[i];
      const [lon2, lat2] = line[i + 1];
      if (isArtificialSeam(lon1, lat1, lon2, lat2)) continue;
      const a = latLonToVec3(lat1, lon1, radius);
      const b = latLonToVec3(lat2, lon2, radius);
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
  };

  const looksLikePolygons = (value: unknown): value is GeoPolygon[] =>
    Array.isArray(value) && value.length > 0 && typeof (value[0] as GeoPolygon)?.exterior !== "undefined";

  if (looksLikePolygons(lines)) {
    for (const polygon of lines) {
      pushLine(polygon.exterior);
      for (const hole of polygon.holes) pushLine(hole);
    }
  } else {
    for (const line of lines as number[][][]) {
      const normalized = unwrapLongitudes(
        (line ?? []).map((p) => [p[0], p[1]] as LonLat)
      );
      pushLine(normalized);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeBoundingSphere();
  return geometry;
}

export function buildGlobeGeometries(
  landSource: unknown,
  borderLines?: number[][][]
): GlobeGeometrySet {
  const polygons = extractPolygonsFromGeoJSON(landSource);
  const land = buildLandMeshGeometry(polygons, R_LAND);
  const coastline = buildCoastlineGeometry(polygons, R_COAST);
  const borders = borderLines ? buildBorderGeometry(borderLines, R_BORDER) : undefined;

  const holeCount = polygons.reduce((sum, p) => sum + p.holes.length, 0);
  const ringCount = polygons.reduce((sum, p) => sum + 1 + p.holes.length, 0);
  const landVertices = (land.getAttribute("position")?.count ?? 0) as number;

  return {
    land,
    coastline,
    borders,
    stats: {
      polygons: polygons.length,
      rings: ringCount,
      holes: holeCount,
      landTriangles: Math.floor(landVertices / 3),
      landVertices,
      coastlineSegments: Math.floor((coastline.getAttribute("position")?.count ?? 0) / 2),
      borderSegments: borders ? Math.floor((borders.getAttribute("position")?.count ?? 0) / 2) : 0,
      sliversRejected: 0,
    },
  };
}

export function disposeGlobeGeometries(set: GlobeGeometrySet): void {
  set.land.dispose();
  set.coastline.dispose();
  set.borders?.dispose();
}
