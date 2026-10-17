import { describe, it, expect } from "vitest";
import * as THREE from "three";
import {
  R_LAND,
  R_COAST,
  R_BORDER,
  SLIVER_AREA_THRESHOLD,
  extractPolygonsFromGeoJSON,
  sanitizeAndDensifyRing,
  computeSignedArea2D,
  angularDistanceDeg,
  subdivideTriangleSpherical2D,
  buildLandMeshGeometry,
  buildCoastlineGeometry,
  buildBorderGeometry,
  isArtificialSeam,
  latLonToVec3,
  GeoPolygon,
} from "@/lib/globeGeographyMesh";

function makePolygon(rings: number[][][]): unknown {
  if (rings.length === 1) {
    return { type: "Polygon", coordinates: rings };
  }
  return { type: "MultiPolygon", coordinates: [rings] };
}

function squareRing(centerLon = 0, size = 10, ccw = true): number[][] {
  const half = size / 2;
  const pts = [
    [centerLon - half, -half],
    [centerLon + half, -half],
    [centerLon + half, half],
    [centerLon - half, half],
  ];
  const ring = ccw ? pts : [...pts].reverse();
  ring.push([ring[0][0], ring[0][1]]);
  return ring;
}

describe("globeGeographyMesh - real-earth geography tessellation", () => {
  it("extracts Polygon and MultiPolygon features with interior hole rings", () => {
    const outer = squareRing(0, 10, true);
    const hole = squareRing(0, 4, false);

    const polyFC = {
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [outer, hole] } },
        { type: "Feature", properties: {}, geometry: { type: "MultiPolygon", coordinates: [[squareRing(20, 5, true)], [squareRing(40, 5, true)]] } },
      ],
    };

    const polygons = extractPolygonsFromGeoJSON(polyFC);
    expect(polygons.length).toBe(3);

    const withHole = polygons.find((p) => p.holes.length === 1);
    expect(withHole).toBeDefined();
    expect(withHole!.holes[0].length).toBeGreaterThanOrEqual(4);

    // Winding normalization: exterior CCW, hole CW
    const extArea = computeSignedArea2D(withHole!.exterior.slice(0, -1));
    const holeArea = computeSignedArea2D(withHole!.holes[0].slice(0, -1));
    expect(extArea).toBeGreaterThan(0);
    expect(holeArea).toBeLessThan(0);
  });

  it("extracts polygons from a Topology via topojson.feature", () => {
    // Minimal TopoJSON square: two arcs forming the boundary of a box.
    const topology = {
      type: "Topology",
      transform: { scale: [1, 1], translate: [0, 0] },
      arcs: [
        [[0, 0], [10, 0]],
        [[10, 0], [10, 10]],
        [[10, 10], [0, 10]],
        [[0, 10], [0, 0]],
      ],
      objects: {
        land: {
          type: "GeometryCollection",
          geometries: [
            { type: "Polygon", arcs: [[0, 1, 2, 3]] },
          ],
        },
      },
    };
    const polygons = extractPolygonsFromGeoJSON(topology);
    expect(polygons.length).toBe(1);
    expect(polygons[0].holes.length).toBe(0);
  });

  it("rejects microscopic topological slivers but keeps valid small islands", () => {
    const tiny = {
      type: "Polygon",
      coordinates: [
        [
          [100, 0],
          [100 + Math.sqrt(SLIVER_AREA_THRESHOLD) / 10, 0],
          [100, Math.sqrt(SLIVER_AREA_THRESHOLD) / 10],
          [100, 0],
        ],
      ],
    };
    const tinyResult = extractPolygonsFromGeoJSON(tiny);
    expect(tinyResult.length).toBe(0);

    // A valid island of ~4 deg^2 must survive
    const island = makePolygon([squareRing(115, 2, true)]);
    const islandResult = extractPolygonsFromGeoJSON(island);
    expect(islandResult.length).toBe(1);
    expect(islandResult[0].exterior.length).toBeGreaterThanOrEqual(4);
  });

  it("unwraps antimeridian crossings and densifies the Antarctica polar closure", () => {
    // Ring crossing the date line: 170 -> -170 must be unwrapped to 170 -> 190
    const dateline = sanitizeAndDensifyRing(
      [
        [170, 10],
        [-170, 10],
        [-170, 20],
        [170, 20],
        [170, 10],
      ],
      false
    );
    const lons = dateline.map((p) => p[0]);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);
    // The ring lives on the 170..190 side of the date line, not -170..170
    expect(maxLon - minLon).toBeLessThan(30);

    // Antarctica polar closure: [0, -80] -> [180, -90] -> [-180, -90] -> [0, -80]
    // The [180,-90] -> [-180,-90] edge spans 360 deg and must be densified into short segments.
    const polar = sanitizeAndDensifyRing(
      [
        [0, -80],
        [180, -90],
        [-180, -90],
        [0, -80],
      ],
      false
    );
    // Densified closure produces many intermediate points along the pole edge
    expect(polar.length).toBeGreaterThan(10);
  });

  it("normalizes winding order: exterior CCW, holes CW", () => {
    const cw = sanitizeAndDensifyRing(squareRing(10, 8, false), false);
    const ccw = sanitizeAndDensifyRing(squareRing(10, 8, true), true);

    expect(computeSignedArea2D(cw.slice(0, -1))).toBeGreaterThan(0);
    expect(computeSignedArea2D(ccw.slice(0, -1))).toBeLessThan(0);
  });

  it("spherical subdivision caps every triangle edge at maxSpanDeg", () => {
    const big: number[] = [];
    subdivideTriangleSpherical2D(0, 0, 60, 0, 0, 40, 3.4, big);

    const triangleCount = big.length / 6;
    expect(triangleCount).toBeGreaterThan(1);

    for (let i = 0; i < big.length; i += 6) {
      const ax = big[i];
      const ay = big[i + 1];
      const bx = big[i + 2];
      const by = big[i + 3];
      const cx = big[i + 4];
      const cy = big[i + 5];

      const d1 = angularDistanceDeg(ay, ax, by, bx);
      const d2 = angularDistanceDeg(by, bx, cy, cx);
      const d3 = angularDistanceDeg(cy, cx, ay, ax);
      expect(Math.max(d1, d2, d3)).toBeLessThanOrEqual(3.4 + 1e-6);
    }
  });

  it("builds land mesh geometry with vertices on R_LAND and outward normals", () => {
    const polygons = extractPolygonsFromGeoJSON(
      makePolygon([squareRing(20, 10, true)])
    );
    expect(polygons.length).toBe(1);

    const land = buildLandMeshGeometry(polygons, R_LAND);
    const pos = land.getAttribute("position") as THREE.BufferAttribute;
    const nor = land.getAttribute("normal") as THREE.BufferAttribute;
    expect(pos).toBeDefined();
    expect(nor).toBeDefined();
    expect(pos.count).toBeGreaterThanOrEqual(3);
    expect(pos.count % 3).toBe(0);
    expect(nor.count).toBe(pos.count);

    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const z = pos.getZ(i);
      const radius = Math.hypot(x, y, z);
      expect(Math.abs(radius - R_LAND)).toBeLessThanOrEqual(0.01);

      const nx = nor.getX(i);
      const ny = nor.getY(i);
      const nz = nor.getZ(i);
      const dot = (x * nx + y * ny + z * nz) / radius;
      expect(dot).toBeGreaterThan(0);
    }
  });

  it("builds coastline and border geometries with correct radii and no artificial seams", () => {
    const polygons = extractPolygonsFromGeoJSON(
      makePolygon([squareRing(40, 10, true)])
    );
    const coast = buildCoastlineGeometry(polygons, R_COAST);
    const cpos = coast.getAttribute("position") as THREE.BufferAttribute;
    expect(cpos).toBeDefined();
    expect(cpos.count).toBeGreaterThanOrEqual(2);
    expect(cpos.count % 2).toBe(0);

    for (let i = 0; i < cpos.count; i++) {
      const x = cpos.getX(i);
      const y = cpos.getY(i);
      const z = cpos.getZ(i);
      expect(Math.abs(Math.hypot(x, y, z) - R_COAST)).toBeLessThanOrEqual(0.01);
    }

    // Artificial seam detection
    expect(isArtificialSeam(180, 20, -180, 20)).toBe(true);
    expect(isArtificialSeam(-179.95, -85, 179.95, -85)).toBe(true);
    expect(isArtificialSeam(10, -89.5, 20, -89.6)).toBe(true);
    expect(isArtificialSeam(10, 20, 20, 30)).toBe(false);

    // Borders from a raw MultiLineString
    const borders = buildBorderGeometry(
      [
        [[0, 0], [10, 0], [20, 5]],
        [[40, 40], [50, 50]],
      ],
      R_BORDER
    );
    const bpos = borders.getAttribute("position") as THREE.BufferAttribute;
    expect(bpos.count).toBe(6);
    for (let i = 0; i < bpos.count; i++) {
      const x = bpos.getX(i);
      const y = bpos.getY(i);
      const z = bpos.getZ(i);
      expect(Math.abs(Math.hypot(x, y, z) - R_BORDER)).toBeLessThanOrEqual(0.01);
    }
  });

  it("latLonToVec3 places Jakarta on the sphere at the expected coordinates", () => {
    const v = latLonToVec3(-6.2088, 106.8456, 1);
    expect(Math.hypot(v.x, v.y, v.z)).toBeCloseTo(1.0, 5);
    expect(v.y).toBeLessThan(0);
    expect(v.x).toBeGreaterThan(0);
    expect(v.z).toBeLessThan(0);
  });
});
