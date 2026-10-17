#!/usr/bin/env node
/**
 * generate-geo-assets.mjs
 * ----------------------------------------------------------------------------
 * Generates the local, offline-first Natural Earth assets served from
 * `frontend/public/geo/` out of the `world-atlas` npm package (which bundles
 * Natural Earth data, public domain / CC0 1.0).
 *
 * Usage (from frontend/):
 *   node scripts/generate-geo-assets.mjs 110m
 *   node scripts/generate-geo-assets.mjs 50m
 *
 * Outputs (for resolution <res>):
 *   public/geo/ne_<res>_land.geojson                   — land polygons
 *   public/geo/ne_<res>_admin_0_countries.geojson      — country polygons
 *   public/geo/ne_<res>_admin_0_boundary_lines.geojson — interior borders
 *
 * Resolution characteristics (measured on the bundled files):
 *   - 110m: land = 125 polygons / 126 rings / 1 Caspian hole; countries = 177
 *     features (148 Polygon + 29 MultiPolygon) incl. the Lesotho enclave hole.
 *     Covers the 13 major Indonesian islands, Japan, Philippines, UK, NZ, ...
 *     but not micro-islands below the 1:110m threshold (Singapore, Malta).
 *   - 50m:  >1,400 polygons; separates small islands and micro-states
 *     (Bali, Bangka, Belitung, Madura, Singapore, Malta, Bahrain).
 *
 * Keep the output filenames in sync with GEO_RESOLUTION in
 * components/web-scanner/WebScanGlobe.tsx.
 */

import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import { feature, mesh } from "topojson-client";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(__dirname, "..");

const resolution = (process.argv[2] || "110m").toLowerCase();
if (!["110m", "50m", "10m"].includes(resolution)) {
  console.error('Unknown resolution "' + resolution + '". Use one of: 110m, 50m, 10m.');
  process.exit(1);
}

const worldAtlasDir = path.join(frontendRoot, "node_modules", "world-atlas");
const outDir = path.join(frontendRoot, "public", "geo");
fs.mkdirSync(outDir, { recursive: true });

function loadTopo(name) {
  const file = path.join(worldAtlasDir, name);
  if (!fs.existsSync(file)) {
    console.error("Missing source file: " + file + " (run pnpm install first).");
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeGeoJson(filename, geojson) {
  const file = path.join(outDir, filename);
  fs.writeFileSync(file, JSON.stringify(geojson));
  const kb = (fs.statSync(file).size / 1024).toFixed(1);
  console.log("  [ok] " + filename + " (" + kb + " KB)");
}

console.log("Generating Natural Earth " + resolution + " assets -> public/geo/");

const landTopo = loadTopo("land-" + resolution + ".json");
const landGeo = feature(landTopo, landTopo.objects.land);
writeGeoJson("ne_" + resolution + "_land.geojson", landGeo);

const countriesTopo = loadTopo("countries-" + resolution + ".json");
const countriesGeo = feature(countriesTopo, countriesTopo.objects.countries);
writeGeoJson("ne_" + resolution + "_admin_0_countries.geojson", countriesGeo);

const bordersGeo = mesh(
  countriesTopo,
  countriesTopo.objects.countries,
  (a, b) => a !== b
);
writeGeoJson("ne_" + resolution + "_admin_0_boundary_lines.geojson", bordersGeo);

console.log("Done. Files are static assets - no runtime egress required.");
