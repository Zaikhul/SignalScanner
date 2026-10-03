"use client";

import React, { useMemo, useState, useEffect } from "react";
import ReactECharts from "echarts-for-react";
import { Info, PushPin, X, Warning, ArrowClockwise } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { SweepArmOverlay } from "./SweepArmOverlay";
import {
  getStableAngleHash31,
  computeRadialMapping,
  evaluateTargetFreshness,
  RSSI_MIN_SCALE,
  RSSI_MAX_SCALE,
} from "@/lib/scanfieldMath";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

export function ScanField() {
  const {
    targets,
    selectedTargetId,
    setSelectedTargetId,
    mode,
    activeSession,
    searchQuery,
    setSearchQuery,
    showExpiredHistory,
    latestQuality,
    connectionState,
    adapterConflictNotice,
  } = useScannerStore();

  const prefersReducedMotion = usePrefersReducedMotion();
  const [now, setNow] = useState<number>(Date.now());

  // Clock tick for freshness updates (every 2s)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 2000);
    return () => clearInterval(timer);
  }, []);

  // 1. Process all available targets and evaluate freshness uniformly
  const evaluatedTargets = useMemo(() => {
    return targets.map((t) => {
      const freshnessInfo = evaluateTargetFreshness(t, now, mode);
      const radial = computeRadialMapping(t.latest_signal, t.unit);
      return {
        ...t,
        computed_freshness: freshnessInfo.freshness,
        age_seconds: freshnessInfo.ageSeconds,
        is_stale: freshnessInfo.isStale,
        is_expired: freshnessInfo.isExpired,
        radial,
      };
    });
  }, [targets, now, mode]);

  // Available count Y (before search/band filter, but respecting history toggle)
  const availableTargets = useMemo(() => {
    return evaluatedTargets.filter((t) => (showExpiredHistory ? true : !t.is_expired));
  }, [evaluatedTargets, showExpiredHistory]);

  // Plotted targets X (filtered by search and must be plottable)
  const plottedTargets = useMemo(() => {
    const term = searchQuery.trim().toLowerCase();
    return availableTargets.filter((t) => {
      if (!t.radial.isPlottable) return false;
      if (!term) return true;
      return (
        (t.display_name && t.display_name.toLowerCase().includes(term)) ||
        t.target_id.toLowerCase().includes(term) ||
        (t.channel && t.channel.toString().includes(term)) ||
        (t.band && t.band.toLowerCase().includes(term))
      );
    });
  }, [availableTargets, searchQuery]);

  // Find currently selected target
  const selectedTarget = useMemo(() => {
    if (!selectedTargetId) return null;
    return evaluatedTargets.find((t) => t.target_id === selectedTargetId) || null;
  }, [evaluatedTargets, selectedTargetId]);

  // Check if selected target is hidden by filter
  const isSelectedTargetFilteredOut = useMemo(() => {
    if (!selectedTarget) return false;
    return !plottedTargets.some((t) => t.target_id === selectedTarget.target_id);
  }, [selectedTarget, plottedTargets]);

  // Calculate guide ring radius for selected target
  const selectedGuideGeometry = useMemo(() => {
    if (!selectedTarget || !selectedTarget.radial.isPlottable) return null;
    const angle = getStableAngleHash31(selectedTarget.target_id);
    const u = selectedTarget.radial.normalizedU; // 0 (-30 dBm) to 1 (-100 dBm)
    // In SVG viewBox 0 0 100 100 centered at (50, 50):
    // r_inner = 4 (8%), r_outer = 43 (86%)
    const rSvg = 4 + u * (43 - 4);
    const rad = ((angle - 90) * Math.PI) / 180;
    const cx = 50 + rSvg * Math.cos(rad);
    const cy = 50 + rSvg * Math.sin(rad);

    return {
      rSvg,
      cx,
      cy,
      angle,
      clampedSignal: selectedTarget.radial.clampedSignal,
    };
  }, [selectedTarget]);

  // ECharts Option
  const chartOption = useMemo(() => {
    const seriesData = plottedTargets.map((t) => {
      const angle = getStableAngleHash31(t.target_id);
      const isSelected = t.target_id === selectedTargetId;

      // Solid color coding according to freshness - NO shadow/glow
      let fillColor = "#a8d94f"; // fresh
      let borderColor = "#111416";
      let borderWidth = 1.5;

      if (t.computed_freshness === "stale") {
        fillColor = "#e7ad52"; // warning amber
      } else if (t.computed_freshness === "expired") {
        fillColor = "#111416"; // hollow
        borderColor = "#78837f";
        borderWidth = 1.5;
      } else if (t.computed_freshness === "unknown") {
        fillColor = "#111416"; // hollow
        borderColor = "#9aa3a0";
        borderWidth = 1.5;
      }

      if (isSelected) {
        fillColor = "#ffffff";
        borderColor = "#a8d94f";
        borderWidth = 2.5;
      }

      return {
        id: t.target_id,
        name: t.display_name || t.target_id,
        // Polar coordinates: [radius (clampedSignal), angle (deg)]
        value: [t.radial.clampedSignal, angle],
        target_id: t.target_id,
        raw_signal: t.radial.rawSignal,
        unit: t.unit,
        channel: t.channel,
        band: t.band,
        snr: t.avg_snr,
        delta: t.delta_signal,
        age_seconds: t.age_seconds,
        freshness: t.computed_freshness,
        out_of_scale: t.radial.outOfScale,
        symbolSize: 8, // FIXED 8 CSS px core diameter per PRD 13.4
        itemStyle: {
          color: fillColor,
          borderColor: borderColor,
          borderWidth: borderWidth,
        },
      };
    });

    return {
      backgroundColor: "transparent",
      animationDurationUpdate: prefersReducedMotion ? 0 : 220,
      animationEasingUpdate: "cubicOut",
      tooltip: {
        trigger: "item",
        backgroundColor: "#171b1d",
        borderColor: "#2a3033",
        borderWidth: 1,
        padding: [8, 12],
        textStyle: { color: "#f2f4ef", fontSize: 12, fontFamily: "var(--font-sans)" },
        extraCssText: "border-radius: 8px; box-shadow: none;",
        formatter: (params: any) => {
          const d = params.data;
          if (!d) return "";
          return `
            <div style="font-family: var(--font-sans); min-width: 170px;">
              <div style="font-weight: 600; color: #f2f4ef; margin-bottom: 4px; font-size: 13px;">${d.name}</div>
              <div style="font-family: var(--font-mono); font-size: 11px; color: #a8d94f; margin-bottom: 2px;">
                Kekuatan: <b>${d.raw_signal} ${d.unit}</b>
                ${d.out_of_scale ? ` <span style="color:#e7ad52;">(Di luar skala)</span>` : ""}
              </div>
              ${d.delta !== undefined && d.delta !== null ? `<div style="font-family: var(--font-mono); font-size: 10px; color: #9aa3a0;">Perubahan Δ: ${d.delta > 0 ? `+${d.delta}` : d.delta} dB</div>` : ""}
              ${d.channel ? `<div style="font-size: 10px; color: #9aa3a0;">Kanal: ${d.channel} ${d.band ? `(${d.band})` : ""}</div>` : ""}
              <div style="font-size: 10px; color: #9aa3a0; margin-top: 2px;">
                Usia: ${d.age_seconds}s (${d.freshness})
              </div>
              <div style="margin-top: 6px; font-size: 9px; color: #78837f; border-top: 1px solid #2a3033; padding-top: 4px;">
                Radius: RSSI relatif | Sudut: Hash tetap
              </div>
            </div>
          `;
        },
      },
      polar: {
        radius: ["8%", "86%"],
      },
      angleAxis: {
        type: "value",
        startAngle: 90,
        min: 0,
        max: 360,
        interval: 45,
        clockwise: true,
        axisLine: { lineStyle: { color: "#2a3033", width: 1 } },
        axisLabel: {
          formatter: "{value}°",
          color: "#78837f",
          fontSize: 9,
          fontFamily: "var(--font-mono)",
        },
        splitLine: { lineStyle: { color: "#1f2427", width: 1, type: "solid" } },
      },
      radiusAxis: {
        type: "value",
        min: RSSI_MIN_SCALE,
        max: RSSI_MAX_SCALE,
        inverse: true, // -30 dBm at center, -100 dBm at outer ring
        axisLine: { lineStyle: { color: "#2a3033", width: 1 } },
        axisLabel: {
          formatter: "{value} dBm",
          color: "#78837f",
          fontSize: 9,
          fontFamily: "var(--font-mono)",
        },
        splitLine: { lineStyle: { color: "#1c2124", width: 1 } },
      },
      series: [
        {
          type: "scatter",
          coordinateSystem: "polar",
          data: seriesData,
          cursor: "pointer",
        },
      ],
    };
  }, [plottedTargets, selectedTargetId, prefersReducedMotion]);

  const onChartClick = (params: any) => {
    if (params.data?.target_id) {
      setSelectedTargetId(params.data.target_id);
    }
  };

  // Operational State label
  const operationalStateLabel = useMemo(() => {
    if (adapterConflictNotice) return "Dijeda (Konflik Adapter)";
    if (connectionState === "disconnected") return "Terputus";
    if (connectionState === "reconnecting") return "Menghubungkan Ulang";
    if (!activeSession) return "Siap memindai";
    if (activeSession.status === "paused") return "Dijeda";
    if (activeSession.status === "completed" || activeSession.status === "stopped") return "Selesai";
    if (activeSession.status === "active") {
      if (plottedTargets.length === 0 && availableTargets.length === 0) {
        return "Belum ada target terdeteksi";
      }
      return "Memindai";
    }
    return "Menunggu hasil collector";
  }, [adapterConflictNotice, connectionState, activeSession, plottedTargets.length, availableTargets.length]);

  return (
    <div className="rounded-[var(--radius-panel)] border border-[var(--color-line)] bg-[var(--color-canvas)] p-4 space-y-3">
      {/* 1. Header Instrumen (PRD 13.4) */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-line)] pb-3">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-semibold text-[var(--color-ink)]">Pemindaian sinyal</h2>
          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-[var(--color-line)] text-zinc-400">
            {mode}
          </span>
          <span className="text-xs text-zinc-400 font-medium">
            • {operationalStateLabel}
          </span>
        </div>

        <div className="flex items-center gap-3 font-mono text-xs text-zinc-400">
          <span>
            Cadence:{" "}
            <strong className="text-zinc-200">
              {latestQuality?.actual_interval_ms
                ? `${latestQuality.actual_interval_ms} ms`
                : "Tidak tersedia"}
            </strong>
          </span>
          <div className="h-3 w-[1px] bg-[var(--color-line)]" />
          <span>
            Diplot: <strong className="text-[var(--color-signal-lime)]">{plottedTargets.length}</strong> /{" "}
            Tersedia: <strong className="text-zinc-200">{availableTargets.length}</strong>
          </span>
        </div>
      </div>

      {/* Notice if selected target is filtered out */}
      {isSelectedTargetFilteredOut && selectedTarget && (
        <div className="px-3 py-1.5 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-[var(--color-status-warning)] text-xs text-zinc-300 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 truncate">
            <Warning size={14} className="text-[var(--color-status-warning)] shrink-0" />
            <span className="truncate">
              Target terpilih <b>{selectedTarget.display_name || selectedTarget.target_id}</b> tersembunyi oleh filter saat ini.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setSearchQuery("")}
            className="text-[11px] font-mono text-[var(--color-signal-lime)] hover:underline shrink-0"
          >
            Hapus filter
          </button>
        </div>
      )}

      {/* 2. Main Center Radar Plot Container */}
      <div className="relative aspect-square w-full rounded-[calc(var(--radius-panel)-4px)] border border-[var(--color-line)] bg-[var(--color-surface)] overflow-hidden flex items-center justify-center">
        {/* ECharts SVG Polar Scatter Plot */}
        <div className="absolute inset-0 z-0">
          <ReactECharts
            option={chartOption}
            style={{ width: "100%", height: "100%" }}
            onEvents={{ click: onChartClick }}
            opts={{ renderer: "svg" }}
          />
        </div>

        {/* Sweep Arm Motion Layer */}
        <SweepArmOverlay />

        {/* Selection Focus Overlay: Guide Ring & Halo around selected target */}
        {selectedGuideGeometry && (
          <svg
            viewBox="0 0 100 100"
            className="absolute inset-0 w-full h-full pointer-events-none z-15"
            aria-hidden="true"
          >
            {/* Guide circle at exact selected radius across 360 degrees */}
            <circle
              cx="50"
              cy="50"
              r={selectedGuideGeometry.rSvg}
              fill="none"
              stroke="#a8d94f"
              strokeWidth="0.35"
              strokeDasharray="1 1"
              strokeOpacity="0.6"
            />
            {/* Outline ring around selected beacon core (2px outline with 3px gap) */}
            <circle
              cx={selectedGuideGeometry.cx}
              cy={selectedGuideGeometry.cy}
              r="2.2"
              fill="none"
              stroke="#a8d94f"
              strokeWidth="0.4"
            />
          </svg>
        )}

        {/* Static Mathematical Center Crosshair (PRD 13.4 - NO glowing HUD reticle) */}
        <div
          className="absolute w-2.5 h-2.5 pointer-events-none z-10 flex items-center justify-center"
          aria-hidden="true"
        >
          <div className="w-[1px] h-full bg-[var(--color-instrument-mark)] opacity-60" />
          <div className="absolute h-[1px] w-full bg-[var(--color-instrument-mark)] opacity-60" />
        </div>

        {/* Semantic Layout Angle Tag (PRD 13.4) */}
        <div className="absolute top-2 left-2 z-20 px-2 py-0.5 rounded-[var(--radius-control)] bg-[var(--color-canvas)]/80 border border-[var(--color-line)] text-[9px] font-mono text-[var(--color-instrument-mark)] pointer-events-none">
          Sudut: hash31-v1
        </div>
      </div>

      {/* 3. Readout Target Strip (PRD 13.4 - Terpilih) */}
      {selectedTarget && (
        <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-[var(--color-line)] flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-[var(--color-ink)] truncate text-sm">
                {selectedTarget.display_name || "Emitter"}
              </span>
              <span className="font-mono text-[10px] text-zinc-400 truncate">
                ({selectedTarget.target_id})
              </span>
              {selectedTarget.is_pinned && (
                <PushPin size={12} weight="fill" className="text-[var(--color-signal-lime)] shrink-0" />
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-1 font-mono text-[11px] text-zinc-400">
              <span>
                Kekuatan:{" "}
                <strong className="text-[var(--color-signal-lime)]">
                  {selectedTarget.latest_signal} {selectedTarget.unit}
                </strong>
                {selectedTarget.radial.outOfScale && (
                  <span className="text-[var(--color-status-warning)] ml-1">
                    (Di luar skala)
                  </span>
                )}
              </span>
              {selectedTarget.delta_signal !== undefined && selectedTarget.delta_signal !== null && (
                <span>
                  Perubahan Δ:{" "}
                  <strong
                    className={
                      selectedTarget.delta_signal > 0
                        ? "text-[var(--color-signal-lime)]"
                        : selectedTarget.delta_signal < 0
                        ? "text-[var(--color-status-error)]"
                        : "text-zinc-400"
                    }
                  >
                    {selectedTarget.delta_signal > 0 ? `+${selectedTarget.delta_signal}` : selectedTarget.delta_signal} dB
                  </strong>
                </span>
              )}
              {selectedTarget.channel && (
                <span>Kanal: {selectedTarget.channel} {selectedTarget.band ? `(${selectedTarget.band})` : ""}</span>
              )}
              <span>
                Usia: {selectedTarget.age_seconds}s lalu ({selectedTarget.computed_freshness})
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setSelectedTargetId(null)}
            className="p-1.5 rounded-[var(--radius-control)] border border-[var(--color-line)] text-zinc-400 hover:text-zinc-200 hover:bg-[var(--color-surface-raised)]"
            title="Tutup seleksi"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* 4. Legenda Semantik (PRD 13.4 - Selalu Terlihat dalam Aliran Layout) */}
      <div className="flex items-start gap-2 pt-1 text-[11px] text-[var(--color-instrument-mark)] leading-relaxed">
        <Info size={14} className="text-[var(--color-signal-lime)] shrink-0 mt-0.5" />
        <p>
          <strong className="text-zinc-300">Radius:</strong> RSSI relatif (−30 dBm kuat di pusat hingga −100 dBm di tepi luar).{" "}
          <strong className="text-zinc-300">Sudut:</strong> Tata letak hash tetap (bukan arah datang atau lokasi fisik).{" "}
          <strong className="text-zinc-300">Sweep:</strong> Indikator aktivitas pemindaian aktual.
        </p>
      </div>

      {/* 5. Fallback Aksesibilitas Pembaca Layar (PRD 13.9 & FR-SCN-10) */}
      <div className="sr-only" aria-live="polite">
        <h3>Daftar Aksesibel Target Pemindaian Sinyal ({plottedTargets.length} target)</h3>
        <table>
          <thead>
            <tr>
              <th>Nama</th>
              <th>Identifier</th>
              <th>Kekuatan Sinyal</th>
              <th>Kanal</th>
              <th>Status Usia</th>
            </tr>
          </thead>
          <tbody>
            {plottedTargets.map((t) => (
              <tr key={t.target_id}>
                <td>{t.display_name || "Unknown"}</td>
                <td>{t.target_id}</td>
                <td>{t.latest_signal} {t.unit}</td>
                <td>{t.channel || "-"}</td>
                <td>{t.computed_freshness} ({t.age_seconds} detik lalu)</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
