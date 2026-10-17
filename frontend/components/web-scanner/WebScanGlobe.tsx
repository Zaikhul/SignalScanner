"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowsClockwise,
  Crosshair,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
  Play,
  Pause,
  ShieldWarning,
  Pulse,
  Stack,
  HardDrives,
  GlobeHemisphereWest,
  MapTrifold,
  Cube,
} from "@phosphor-icons/react";
import { GeoEndpoint, GeoRelation, Severity } from "@/lib/webScanTypes";
import { useWebScanStore } from "@/lib/webScanStore";
import {
  buildActiveFindingSeverityMap,
  clusterTargetEndpoints,
  GlobeColorMode,
} from "@/lib/globeMath";
import { WebScanGlobeThree, GlobeVisualPreset } from "@/lib/WebScanGlobeThree";
import {
  buildGlobeGeometries,
  GlobeGeometrySet,
  R_GLOBE,
  R_LAND,
} from "@/lib/globeGeographyMesh";

interface WebScanGlobeProps {
  endpointsById: Map<string, GeoEndpoint>;
  relations: GeoRelation[];
  selectedRelationId: string | null;
  onSelectRelation: (id: string | null) => void;
  onCanvasError?: () => void;
  onWebglError?: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Real Earth geography assets — Natural Earth (public domain, CC0 1.0),
// redistributed via `world-atlas` (ISC) and served as LOCAL STATIC FILES from
// `frontend/public/geo/`. No CDN or tile server is contacted at runtime.
//
// Resolution is documented honestly:
//   110m (default) — ~125 land polygons / 126 rings / 1 Caspian hole;
//                    177 country features incl. the Lesotho enclave hole.
//                    Covers the 13 major Indonesian islands, Japan, the
//                    Philippines, UK, NZ, Madagascar, Cuba, Fiji, …
//                    Micro-islands below the 1:110m threshold (Singapore,
//                    Malta) are not separated.
//   50m            — ~1,400 polygons; separates small islands and micro-states
//                    (Bali, Bangka, Belitung, Madura, Singapore, Malta…).
//                    Regenerate with `node scripts/generate-geo-assets.mjs 50m`
//                    and flip GEO_RESOLUTION to "50m" — no code change needed.
// ─────────────────────────────────────────────────────────────────────────────
const GEO_RESOLUTION = "110m" as "110m" | "50m";
const GEO_BASE = "/geo";

const REGION_JUMPS: {
  id: "nusantara" | "asia_pacific" | "europe" | "americas";
  label: string;
}[] = [
  { id: "nusantara", label: "Nusantara" },
  { id: "asia_pacific", label: "Asia-Pasifik" },
  { id: "europe", label: "Eropa" },
  { id: "americas", label: "Amerika" },
];

const PRESETS: { id: GlobeVisualPreset; label: string }[] = [
  { id: "hex_matrix", label: "Hex-Matrix" },
  { id: "night_ops", label: "Night Ops" },
  { id: "wireframe", label: "Wireframe" },
];

export function WebScanGlobe({
  endpointsById,
  relations,
  selectedRelationId,
  onSelectRelation,
  onCanvasError,
  onWebglError,
}: WebScanGlobeProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const engineRef = useRef<WebScanGlobeThree | null>(null);

  const { findings } = useWebScanStore();

  // UI state (mirrors engine state)
  const [colorMode, setColorMode] = useState<GlobeColorMode>("severity");
  const [visualPreset, setVisualPreset] = useState<GlobeVisualPreset>("hex_matrix");
  const [showBorders, setShowBorders] = useState<boolean>(true);
  const [autoOrbit, setAutoOrbit] = useState<boolean>(false);
  const [zoomDisplay, setZoomDisplay] = useState<number>(1.05);
  const [isReady, setIsReady] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [geometryStats, setGeometryStats] = useState<{
    polygons: number;
    holes: number;
    landTriangles: number;
  } | null>(null);

  const [hoveredRelationId, setHoveredRelationId] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);
  const [dimensions, setDimensions] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  });

  const reducedMotionRef = useRef(false);

  // F09: triage contract — false_positive / resolved findings are suppressed
  // so they never raise the severity colour of pillars, arcs, or clusters.
  const findingSeveritiesById = useMemo(
    () =>
      buildActiveFindingSeverityMap(
        findings.map((f) => ({
          id: f.id,
          severity: f.severity,
          triage_status: f.triage_status ?? null,
        }))
      ),
    [findings]
  );

  // Relations whose endpoints have no honest coordinates (RFC 1918 / unmapped).
  // These are NEVER given fake coordinates on the sphere.
  const unlocatedRelations = useMemo(() => {
    return relations.filter((rel) => {
      const src = endpointsById.get(rel.source_endpoint_id);
      const tgt = endpointsById.get(rel.target_endpoint_id);
      return !src?.location || !tgt?.location;
    });
  }, [relations, endpointsById]);

  const mappedTargetCount = useMemo(
    () => clusterTargetEndpoints(relations, endpointsById, findingSeveritiesById).length,
    [relations, endpointsById, findingSeveritiesById]
  );

  // Detect prefers-reduced-motion
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    reducedMotionRef.current = media.matches;
    const listener = (e: MediaQueryListEvent) => {
      reducedMotionRef.current = e.matches;
    };
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  // ResizeObserver for container responsiveness
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setDimensions({ width: Math.floor(width), height: Math.floor(height) });
          engineRef.current?.resize(Math.floor(width), Math.floor(height));
        }
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // ── Engine bootstrap: create renderer, then load real geography ──────────
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const reducedMotion =
      typeof window !== "undefined" && window.matchMedia
        ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
        : false;

    let engine: WebScanGlobeThree;
    try {
      engine = new WebScanGlobeThree({
        canvas,
        container,
        endpointsById,
        relations,
        selectedRelationId,
        colorMode: "severity",
        visualPreset: "hex_matrix",
        showBorders: true,
        autoOrbit: false,
        reducedMotion,
        onSelectRelation,
        onHoverChange: (relationId, _clusterKey, pos) => {
          setHoveredRelationId(relationId);
          setTooltipPos(pos);
        },
        onError: () => {
          onCanvasError?.();
          onWebglError?.();
        },
      });
    } catch {
      onCanvasError?.();
      onWebglError?.();
      return;
    }

    engineRef.current = engine;

    // Load Natural Earth assets from local static files (offline-first).
    let cancelled = false;
    const loadGeography = async () => {
      try {
        const [landRes, borderRes] = await Promise.all([
          fetch(`${GEO_BASE}/ne_${GEO_RESOLUTION}_land.geojson`),
          fetch(`${GEO_BASE}/ne_${GEO_RESOLUTION}_admin_0_boundary_lines.geojson`),
        ]);

        if (!landRes.ok) {
          throw new Error(`Geography asset unavailable (HTTP ${landRes.status})`);
        }

        const landGeo = await landRes.json();
        let borderLines: number[][][] | undefined;
        if (borderRes.ok) {
          const borderGeo = await borderRes.json();
          // MultiLineString → coordinates; tolerate missing/alternate shapes.
          if (borderGeo?.type === "MultiLineString" && Array.isArray(borderGeo.coordinates)) {
            borderLines = borderGeo.coordinates;
          } else if (borderGeo?.type === "Feature" && borderGeo.geometry?.type === "MultiLineString") {
            borderLines = borderGeo.geometry.coordinates;
          } else if (
            borderGeo?.type === "FeatureCollection" &&
            Array.isArray(borderGeo.features)
          ) {
            const merged: number[][][] = [];
            for (const feat of borderGeo.features) {
              const g = feat?.geometry;
              if (g?.type === "MultiLineString") merged.push(...g.coordinates);
              else if (g?.type === "LineString") merged.push(g.coordinates);
            }
            borderLines = merged;
          }
        }

        if (cancelled) return;

        const geometries: GlobeGeometrySet = buildGlobeGeometries(landGeo, borderLines);
        engine.applyGeometries(geometries);
        setGeometryStats({
          polygons: geometries.stats.polygons,
          holes: geometries.stats.holes,
          landTriangles: geometries.stats.landTriangles,
        });
        setIsReady(true);
      } catch (err) {
        if (cancelled) return;
        setLoadError(
          err instanceof Error ? err.message : "Gagal memuat aset geografi Natural Earth."
        );
      }
    };

    void loadGeography();

    return () => {
      cancelled = true;
      engine.destroy();
      engineRef.current = null;
    };
    // Engine is created once; subsequent prop changes flow through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push telemetry updates into the engine whenever data/state changes
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine || !isReady) return;
    engine.updateTelemetry(
      endpointsById,
      relations,
      selectedRelationId,
      colorMode,
      Array.from(findingSeveritiesById.entries()).map(([id, severity]) => ({
        id,
        severity,
      }))
    );
  }, [endpointsById, relations, selectedRelationId, colorMode, findingSeveritiesById, isReady]);

  // Sync visual preset
  useEffect(() => {
    engineRef.current?.setVisualPreset(visualPreset);
  }, [visualPreset]);

  // Sync border visibility
  useEffect(() => {
    engineRef.current?.setBordersVisible(showBorders);
  }, [showBorders]);

  // Sync auto-orbit
  useEffect(() => {
    engineRef.current?.setAutoOrbit(autoOrbit);
  }, [autoOrbit]);

  // Fly to the selected relation's target
  useEffect(() => {
    if (!selectedRelationId) return;
    const rel = relations.find((r) => r.id === selectedRelationId);
    if (!rel) return;
    const tgt = endpointsById.get(rel.target_endpoint_id);
    if (!tgt?.location) return;
    engineRef.current?.flyTo(tgt.location.latitude, tgt.location.longitude);
  }, [selectedRelationId, relations, endpointsById]);

  // Keyboard navigation (WCAG 2.2 AA)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const engine = engineRef.current;
    if (!engine) return;
    const step = 0.12;

    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        engine.setRotationTargetDelta(-step, 0);
        break;
      case "ArrowRight":
        e.preventDefault();
        engine.setRotationTargetDelta(step, 0);
        break;
      case "ArrowUp":
        e.preventDefault();
        engine.setRotationTargetDelta(0, -step);
        break;
      case "ArrowDown":
        e.preventDefault();
        engine.setRotationTargetDelta(0, step);
        break;
      case "+":
      case "=":
        e.preventDefault();
        engine.setZoom(engine.getZoom() + 0.15);
        setZoomDisplay(engine.getZoom());
        break;
      case "-":
      case "_":
        e.preventDefault();
        engine.setZoom(engine.getZoom() - 0.15);
        setZoomDisplay(engine.getZoom());
        break;
      case "[":
      case "]": {
        if (relations.length === 0) break;
        e.preventDefault();
        const currentIndex = relations.findIndex((r) => r.id === selectedRelationId);
        const nextIndex =
          e.key === "]"
            ? (currentIndex + 1) % relations.length
            : (currentIndex - 1 + relations.length) % relations.length;
        onSelectRelation(relations[nextIndex].id);
        break;
      }
      case "b":
      case "B":
        e.preventDefault();
        setShowBorders((v) => !v);
        break;
      default:
        break;
    }
  };

  const hoveredRelation = useMemo(
    () => relations.find((r) => r.id === hoveredRelationId) || null,
    [relations, hoveredRelationId]
  );
  const hoveredTarget = hoveredRelation
    ? endpointsById.get(hoveredRelation.target_endpoint_id)
    : null;

  const handleZoom = (delta: number) => {
    const engine = engineRef.current;
    if (!engine) return;
    engine.setZoom(engine.getZoom() + delta);
    setZoomDisplay(engine.getZoom());
  };

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      role="application"
      aria-label="Kanvas interaktif Globe 3D WebGL pemindaian web. Gunakan tombol panah untuk memutar globe, plus atau minus untuk zoom, kurung siku untuk berpindah relasi, dan tombol B untuk menampilkan atau menyembunyikan batas negara."
      onKeyDown={handleKeyDown}
      className="relative w-full h-[460px] bg-zinc-950 rounded-lg overflow-hidden border border-white/10 select-none focus:outline-none focus:ring-1 focus:ring-[var(--color-signal)]"
    >
      <canvas ref={canvasRef} className="w-full h-full block" aria-hidden="true" />

      {/* Loading / error overlays */}
      {!isReady && !loadError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-[11px] font-mono text-zinc-400 pointer-events-none">
          <ArrowsClockwise size={20} className="animate-spin text-sky-400" />
          <span>Menjahit geometri Natural Earth…</span>
        </div>
      )}
      {loadError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center text-[11px] font-mono text-red-300">
          <span>{loadError}</span>
          <span className="text-zinc-500">
            Aset lokal: public/geo/ne_{GEO_RESOLUTION}_land.geojson
          </span>
        </div>
      )}

      {/* Top-Left: Color Mode Switcher + Dynamic Legend + Presets */}
      <div className="absolute top-3 left-3 flex flex-col gap-2 max-w-[290px]">
        <div className="bg-zinc-900/90 backdrop-blur border border-white/10 rounded-lg p-1 flex items-center gap-1 text-[11px] font-mono">
          <button
            type="button"
            onClick={() => setColorMode("severity")}
            aria-pressed={colorMode === "severity"}
            className={`px-2 py-1 rounded flex items-center gap-1 transition ${
              colorMode === "severity"
                ? "bg-[var(--color-signal)] text-zinc-950 font-bold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <ShieldWarning size={12} />
            <span>Risiko</span>
          </button>
          <button
            type="button"
            onClick={() => setColorMode("http_status")}
            aria-pressed={colorMode === "http_status"}
            className={`px-2 py-1 rounded flex items-center gap-1 transition ${
              colorMode === "http_status"
                ? "bg-[var(--color-signal)] text-zinc-950 font-bold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Stack size={12} />
            <span>HTTP</span>
          </button>
          <button
            type="button"
            onClick={() => setColorMode("latency")}
            aria-pressed={colorMode === "latency"}
            className={`px-2 py-1 rounded flex items-center gap-1 transition ${
              colorMode === "latency"
                ? "bg-[var(--color-signal)] text-zinc-950 font-bold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Pulse size={12} />
            <span>Latensi</span>
          </button>
        </div>

        {/* Visual surface preset switcher */}
        <div className="bg-zinc-900/90 backdrop-blur border border-white/10 rounded-lg p-1 flex items-center gap-1 text-[10px] font-mono">
          <Cube size={11} className="text-zinc-500 ml-1" />
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setVisualPreset(p.id)}
              aria-pressed={visualPreset === p.id}
              className={`px-1.5 py-1 rounded transition ${
                visualPreset === p.id
                  ? "bg-white/15 text-zinc-100 font-bold"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setShowBorders((v) => !v)}
            aria-pressed={showBorders}
            title="Tampilkan / sembunyikan batas negara (B)"
            className={`px-1.5 py-1 rounded transition flex items-center gap-1 ${
              showBorders ? "bg-white/10 text-zinc-200" : "text-zinc-600 hover:text-zinc-400"
            }`}
          >
            <MapTrifold size={11} />
            <span>Batas</span>
          </button>
        </div>

        <div className="bg-zinc-900/85 backdrop-blur border border-white/10 rounded-lg p-2.5 text-[10px] text-zinc-300 space-y-1.5 pointer-events-none font-mono">
          {colorMode === "severity" && (
            <>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
                <span>Critical / High Finding</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
                <span>Medium Finding</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
                <span>Bersih / Info Only</span>
              </div>
            </>
          )}
          {colorMode === "http_status" && (
            <>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#a8d94f] inline-block" />
                <span>2xx Sukses</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
                <span>4xx Client / WAF Block</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />
                <span>5xx Server Error</span>
              </div>
            </>
          )}
          {colorMode === "latency" && (
            <>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
                <span>&lt; 150 ms (Cepat)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
                <span>150–600 ms (Sedang)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
                <span>&gt; 600 ms (Lambat / Delay)</span>
              </div>
            </>
          )}
          {geometryStats && (
            <div className="border-t border-white/10 pt-1.5 text-[9px] text-zinc-500 leading-relaxed">
              Natural Earth {GEO_RESOLUTION} · {geometryStats.polygons} poligon ·{" "}
              {geometryStats.holes} lubang · {geometryStats.landTriangles.toLocaleString("id-ID")}{" "}
              segitiga · {mappedTargetCount} target terpetakan
            </div>
          )}
        </div>
      </div>

      {/* Top-Right: Region Jump Buttons */}
      <div className="absolute top-3 right-3 flex flex-col gap-1.5 items-end">
        <div className="bg-zinc-900/90 backdrop-blur border border-white/10 rounded-lg p-1 flex items-center gap-1 text-[10px] font-mono">
          <GlobeHemisphereWest size={11} className="text-zinc-500 ml-1" />
          {REGION_JUMPS.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => engineRef.current?.jumpToRegion(r.id)}
              className="px-1.5 py-1 rounded text-zinc-400 hover:text-zinc-100 hover:bg-white/10 transition"
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Bottom-Left: Unlocated / RFC 1918 honest dock */}
      {unlocatedRelations.length > 0 && (
        <div className="absolute bottom-3 left-3 max-w-[260px] bg-zinc-900/90 backdrop-blur border border-white/10 rounded-lg p-2.5 space-y-1.5 text-[11px]">
          <div className="flex items-center gap-1.5 text-zinc-300 font-semibold font-mono">
            <HardDrives size={13} className="text-amber-400 shrink-0" />
            <span>Target Lokal / Non-GeoIP ({unlocatedRelations.length})</span>
          </div>
          <div className="max-h-24 overflow-y-auto space-y-1 pr-1">
            {unlocatedRelations.map((rel) => {
              const tgt = endpointsById.get(rel.target_endpoint_id);
              const isSel = rel.id === selectedRelationId;
              return (
                <button
                  key={rel.id}
                  type="button"
                  onClick={() => onSelectRelation(isSel ? null : rel.id)}
                  className={`w-full text-left px-2 py-1 rounded font-mono text-[10px] flex items-center justify-between gap-2 border transition ${
                    isSel
                      ? "bg-blue-500/20 border-blue-400 text-white"
                      : "bg-zinc-950/80 border-white/5 text-zinc-300 hover:bg-zinc-800"
                  }`}
                >
                  <span className="truncate">{tgt?.ip || tgt?.display_name || "Target"}</span>
                  <span className="text-[9px] text-amber-400 shrink-0">
                    {tgt?.location_status === "unsupported" ? "RFC1918" : "Unmapped"}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-[9px] text-zinc-500 leading-snug">
            Koordinat tidak dipalsukan — target internal ditampilkan di sini.
          </p>
        </div>
      )}

      {/* Floating HUD tooltip (3D raycast hover) */}
      {hoveredRelation && hoveredTarget && tooltipPos && (
        <div
          style={{
            left: Math.min((dimensions.width || 600) - 240, Math.max(12, tooltipPos.x + 14)),
            top: Math.max(12, tooltipPos.y - 10),
          }}
          className="absolute z-20 w-60 pointer-events-none bg-zinc-950/95 backdrop-blur border border-white/15 rounded-lg p-3 shadow-2xl space-y-1.5 text-[11px] font-mono"
        >
          <div className="flex items-center justify-between border-b border-white/10 pb-1">
            <span className="font-bold text-zinc-100 truncate">
              {hoveredTarget.ip || hoveredTarget.display_name}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-zinc-300">
              {hoveredRelation.record_count} req
            </span>
          </div>
          <div className="text-zinc-400 text-[10px] space-y-0.5">
            <div>
              Lokasi:{" "}
              <span className="text-zinc-200">
                {hoveredTarget.location
                  ? [hoveredTarget.location.city, hoveredTarget.location.region, hoveredTarget.location.country]
                      .filter(Boolean)
                      .join(", ") || "Region-level (tanpa kota)"
                  : "Tidak diketahui"}
              </span>
            </div>
            {hoveredTarget.location_level === "region" && (
              <div className="text-amber-400/90">
                Provenance: region-level estimate (tanpa kota sintetis)
              </div>
            )}
            {hoveredTarget.provider_info && (
              <div className="truncate">
                Provider: <span className="text-zinc-300">{hoveredTarget.provider_info}</span>
              </div>
            )}
            <div>
              Status HTTP:{" "}
              <span className="text-emerald-400">
                {hoveredRelation.status_codes.join(", ") || "N/A"}
              </span>
            </div>
            {hoveredRelation.avg_latency_ms != null && (
              <div>
                Rata-rata RTT:{" "}
                <span className="text-sky-400">{hoveredRelation.avg_latency_ms} ms</span>
              </div>
            )}
            {hoveredRelation.total_bytes ? (
              <div>
                Volume:{" "}
                <span className="text-zinc-300">
                  {(hoveredRelation.total_bytes / 1024).toFixed(1)} KB
                </span>
              </div>
            ) : null}
            {hoveredRelation.module_ids && hoveredRelation.module_ids.length > 0 && (
              <div className="truncate">
                Modul: <span className="text-zinc-300">{hoveredRelation.module_ids.join(", ")}</span>
              </div>
            )}
            {hoveredRelation.linked_finding_ids.length > 0 && (
              <div className="text-amber-400 font-semibold pt-0.5">
                ⚠ {hoveredRelation.linked_finding_ids.length} Temuan Keamanan Tertaut
              </div>
            )}
          </div>
        </div>
      )}

      {/* Bottom-Right: Camera Controls */}
      <div className="absolute bottom-3 right-3 flex items-center gap-1.5 bg-zinc-900/85 backdrop-blur border border-white/10 rounded-lg p-1 text-zinc-300">
        <button
          type="button"
          onClick={() => setAutoOrbit((o) => !o)}
          title={autoOrbit ? "Hentikan Rotasi Otomatis" : "Putar Otomatis (Orbit)"}
          aria-label="Toggle Auto Orbit"
          aria-pressed={autoOrbit}
          className={`p-1.5 rounded transition ${
            autoOrbit ? "bg-[var(--color-signal)] text-zinc-950" : "hover:bg-white/10"
          }`}
        >
          {autoOrbit ? <Pause size={15} weight="fill" /> : <Play size={15} weight="fill" />}
        </button>
        <button
          type="button"
          onClick={() => handleZoom(0.18)}
          title="Perbesar (Zoom In)"
          aria-label="Zoom In"
          className="p-1.5 hover:bg-white/10 rounded transition"
        >
          <MagnifyingGlassPlus size={16} />
        </button>
        <span className="text-[9px] font-mono text-zinc-500 w-8 text-center tabular-nums">
          {zoomDisplay.toFixed(2)}×
        </span>
        <button
          type="button"
          onClick={() => handleZoom(-0.18)}
          title="Perkecil (Zoom Out)"
          aria-label="Zoom Out"
          className="p-1.5 hover:bg-white/10 rounded transition"
        >
          <MagnifyingGlassMinus size={16} />
        </button>
        {selectedRelationId && (
          <button
            type="button"
            onClick={() => {
              const rel = relations.find((r) => r.id === selectedRelationId);
              const tgt = rel ? endpointsById.get(rel.target_endpoint_id) : null;
              if (tgt?.location) {
                engineRef.current?.flyTo(tgt.location.latitude, tgt.location.longitude);
              }
            }}
            title="Fokus ke Target Terpilih"
            aria-label="Fokus ke Target Terpilih"
            className="p-1.5 hover:bg-white/10 text-sky-400 rounded transition"
          >
            <Crosshair size={16} />
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            engineRef.current?.resetCamera();
            setZoomDisplay(1.05);
          }}
          title="Reset Kamera"
          aria-label="Reset Orientasi Kamera"
          className="p-1.5 hover:bg-white/10 rounded transition"
        >
          <ArrowsClockwise size={16} />
        </button>
      </div>

      {/* Bottom-Center: spherical shell legend (technical honesty) */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 text-[9px] font-mono text-zinc-600 pointer-events-none whitespace-nowrap">
        R<sub>globe</sub>={R_GLOBE} · R<sub>land</sub>={R_LAND} · WebGL
      </div>
    </div>
  );
}
