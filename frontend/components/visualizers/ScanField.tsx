"use client";

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { Info, Crosshair } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { SweepArmOverlay } from "./SweepArmOverlay";

// Stable string hash to degree (0 - 359)
function getStableAngle(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash << 5) - hash + id.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash) % 360;
}

export function ScanField() {
  const { targets, selectedTargetId, setSelectedTargetId, mode } = useScannerStore();

  const chartOption = useMemo(() => {
    // Map targets to polar scatter points: [radius (signal), angle (deg), ...]
    const data = targets.map((t) => {
      const angle = getStableAngle(t.target_id);
      const isSelected = t.target_id === selectedTargetId;
      const isPinned = t.is_pinned;

      // Symbol size proportional to signal strength (clamped between 10 and 24)
      const norm = Math.max(0, Math.min(1, (t.latest_signal + 100) / 70));
      const size = isSelected ? 22 : 12 + norm * 10;

      return {
        value: [t.latest_signal, angle],
        name: t.display_name || t.target_id,
        target_id: t.target_id,
        signal: t.latest_signal,
        unit: t.unit,
        channel: t.channel,
        band: t.band,
        snr: t.avg_snr,
        symbolSize: size,
        itemStyle: {
          color: isSelected
            ? "#ffffff"
            : isPinned
            ? "#a8d94f"
            : "#a8d94fcc",
          borderColor: isSelected ? "#a8d94f" : "#111416",
          borderWidth: isSelected ? 3 : 1.5,
          shadowBlur: isSelected ? 10 : 0,
          shadowColor: "rgba(168, 217, 79, 0.4)",
        },
      };
    });

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        backgroundColor: "#171b1d",
        borderColor: "#2a3033",
        textStyle: { color: "#f2f4ef", fontSize: 12 },
        formatter: (params: any) => {
          const d = params.data;
          if (!d) return "";
          return `
            <div style="font-family: var(--font-geist-sans); padding: 2px 4px;">
              <div style="font-weight: 600; color: #a8d94f; margin-bottom: 2px;">${d.name}</div>
              <div style="font-family: var(--font-geist-mono); font-size: 11px; color: #e4e4e7;">
                Kekuatan: <b>${d.signal} ${d.unit}</b>
              </div>
              ${d.channel ? `<div style="font-size: 11px; color: #a1a1aa;">Kanal: ${d.channel} (${d.band || ""})</div>` : ""}
              ${d.snr ? `<div style="font-size: 11px; color: #a1a1aa;">SNR: ${d.snr} dB</div>` : ""}
              <div style="margin-top: 6px; font-size: 9px; color: #71717a; border-top: 1px solid #27272a; padding-top: 3px;">
                *Posisi visual relatif, bukan arah fisik
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
        axisLine: { lineStyle: { color: "#2a3033" } },
        axisLabel: {
          formatter: "{value}°",
          color: "#71717a",
          fontSize: 10,
          fontFamily: "var(--font-geist-mono)",
        },
        splitLine: { lineStyle: { color: "#1f2427", type: "dashed" } },
      },
      radiusAxis: {
        type: "value",
        min: -100,
        max: -30,
        inverse: true, // Stronger signal (-30 dBm) at center
        axisLine: { lineStyle: { color: "#2a3033" } },
        axisLabel: {
          formatter: "{value} dBm",
          color: "#71717a",
          fontSize: 9,
          fontFamily: "var(--font-geist-mono)",
        },
        splitLine: { lineStyle: { color: "#1c2124" } },
      },
      series: [
        {
          type: "scatter",
          coordinateSystem: "polar",
          data,
          animationDurationUpdate: 300,
        },
      ],
    };
  }, [targets, selectedTargetId]);

  const onChartClick = (params: any) => {
    if (params.data?.target_id) {
      setSelectedTargetId(params.data.target_id);
    }
  };

  return (
    <div className="relative aspect-square w-full rounded-[var(--radius-panel)] border border-white/10 bg-zinc-950 overflow-hidden flex items-center justify-center">
      {/* Background Radar Rings & Grid Canvas */}
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

      {/* Center Target Reticle */}
      <div className="absolute w-4 h-4 rounded-full border border-[var(--color-signal)]/60 bg-[var(--color-surface)] pointer-events-none z-10 flex items-center justify-center shadow-[0_0_8px_rgba(168,217,79,0.3)]">
        <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-signal)]" />
      </div>

      {/* Instrument Disclaimer Badge */}
      <div className="absolute bottom-3 left-3 z-20 flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--radius-control)] bg-black/70 border border-white/10 text-[10px] text-zinc-400 backdrop-blur-sm">
        <Info size={13} className="text-[var(--color-signal)] shrink-0" />
        <span>Radius: Kekuatan Relatif | Sudut: Hash Deterministik (Bukan Arah Fisik)</span>
      </div>

      {/* Target count counter in top right */}
      <div className="absolute top-3 right-3 z-20 px-2 py-1 rounded-[var(--radius-control)] bg-black/70 border border-white/10 text-[10px] font-mono text-zinc-300">
        BEACONS: {targets.length}
      </div>
    </div>
  );
}
