import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";
import {
  extractPolygonsFromGeoJSON,
  buildLandMeshGeometry,
  R_LAND,
} from "@/lib/globeGeographyMesh";

const GEO_DIR = path.resolve(__dirname, "../public/geo");
const read = (n: string) => JSON.parse(fs.readFileSync(path.join(GEO_DIR, n), "utf8"));

function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

describe("coverage smoke", () => {
  it("covers the Indonesian archipelago, Japan, UK, NZ, Madagascar, Cuba", () => {
    const polys = extractPolygonsFromGeoJSON(read("ne_110m_land.geojson"));
    // Probe points were validated against the actual dataset during development.
    const probes: [string, number, number][] = [
      ["Sumatra", 101.5, -0.5],
      ["Java (incl. Bali)", 110.0, -7.3],
      ["Kalimantan", 114.0, -0.5],
      ["Sulawesi", 121.0, -2.0],
      ["Papua", 138.0, -5.0],
      ["Bali", 115.2, -8.4],
      ["Flores", 121.0, -8.6],
      ["Timor", 125.5, -9.0],
      ["Seram", 128.9, -3.0],
      ["Halmahera", 127.8, 0.8],
      ["Japan Honshu", 138.5, 36.0],
      ["Philippines Luzon", 121.0, 16.0],
      ["Great Britain", -1.5, 52.5],
      ["New Zealand", 172.5, -41.5],
      ["Madagascar", 46.5, -19.0],
      ["Cuba (Havana)", -82.4, 23.1],
    ];
    const missing: string[] = [];
    for (const [name, lon, lat] of probes) {
      const hit = polys.some(
        (p) =>
          pointInRing(lon, lat, p.exterior) &&
          !p.holes.some((h) => pointInRing(lon, lat, h))
      );
      if (!hit) missing.push(name);
    }
    console.log("missing probes:", missing);
    expect(missing).toEqual([]);
  });

  it("has the Caspian Sea hole (not land)", () => {
    const polys = extractPolygonsFromGeoJSON(read("ne_110m_land.geojson"));
    // Caspian centre approx 50.5E, 41.5N
    const coveredByHole = polys.some((p) =>
      p.holes.some((h) => pointInRing(50.5, 41.5, h))
    );
    const coveredByLandExterior = polys.some((p) => pointInRing(50.5, 41.5, p.exterior));
    console.log("Caspian: in hole =", coveredByHole, "| in exterior =", coveredByLandExterior);
    expect(coveredByHole).toBe(true);
  });

  it("keeps Lesotho as a hole in the countries dataset", () => {
    const polys = extractPolygonsFromGeoJSON(read("ne_110m_admin_0_countries.geojson"));
    // Lesotho centre approx 28.2E, -29.6S
    const inHole = polys.some((p) => p.holes.some((h) => pointInRing(28.2, -29.6, h)));
    console.log("Lesotho in hole =", inHole);
    expect(inHole).toBe(true);
  });

  it("produces geometry within performance budget", () => {
    const t0 = Date.now();
    const polys = extractPolygonsFromGeoJSON(read("ne_110m_land.geojson"));
    const geom = buildLandMeshGeometry(polys, R_LAND);
    const ms = Date.now() - t0;
    const tris = geom.attributes.position.count / 3;
    console.log(`build: ${ms} ms, ${tris} triangles`);
    expect(ms).toBeLessThan(5000);
  });
});
