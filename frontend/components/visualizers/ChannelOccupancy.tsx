"use client";

import React, { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useScannerStore } from "@/lib/store";
import { MethodBadge } from "@/components/ui/MethodBadge";

export function ChannelOccupancy() {
  const { targets } = useScannerStore();
  const [activeBand, setActiveBand] = useState<"2.4GHz" | "5GHz">("2.4GHz");

  const chartOption = useMemo(() => {
    // 2.4 GHz channels: 1 through 14
    // 5 GHz channels: 36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165
    const channels =
      activeBand === "2.4GHz"
        ? [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        : [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 149, 153, 157, 161, 165];

    const channelCounts: Record<number, number> = {};
    const channelMaxRssi: Record<number, number> = {};
    channels.forEach((c) => {
      channelCounts[c] = 0;
      channelMaxRssi[c] = -100;
    });

    targets.forEach((t) => {
      if (t.channel && channelCounts[t.channel] !== undefined) {
        channelCounts[t.channel] += 1;
        channelMaxRssi[t.channel] = Math.max(channelMaxRssi[t.channel], t.latest_signal);
      }
    });

    const countData = channels.map((c) => channelCounts[c]);

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: "#171b1d",
        borderColor: "#2a3033",
        textStyle: { color: "#f2f4ef", fontSize: 11 },
        formatter: (params: any) => {
          const ch = params[0]?.axisValue;
          const count = params[0]?.value;
          const maxRssi = channelMaxRssi[Number(ch)];
          const overlapRatio = Math.min((count * 0.15), 1.0).toFixed(2);
          return `
            <div style="font-family: var(--font-geist-sans);">
              <div style="font-weight: 600; color: #a8d94f;">Kanal ${ch} (${activeBand})</div>
              <div>Access Point: <b>${count}</b> AP</div>
              <div>Overlap Index (Inferred): <b>${overlapRatio}</b> (Ratio)</div>
              <div>Max RSSI: <b>${count > 0 ? maxRssi : "N/A"} dBm</b></div>
              <div style="margin-top: 4px; font-size: 9px; color: #9aa3a0;">*Metrik inferensi tumpang tindih BSSID, bukan airtime radio fisik</div>
            </div>
          `;
        },
      },
      grid: {
        top: 24,
        left: 32,
        right: 16,
        bottom: 24,
      },
      xAxis: {
        type: "category",
        data: channels.map(String),
        axisLine: { lineStyle: { color: "#2a3033" } },
        axisLabel: { color: "#9aa3a0", fontSize: 10, fontFamily: "var(--font-geist-mono)" },
      },
      yAxis: {
        type: "value",
        minInterval: 1,
        axisLine: { lineStyle: { color: "#2a3033" } },
        splitLine: { lineStyle: { color: "#1c2124" } },
        axisLabel: { color: "#9aa3a0", fontSize: 10, fontFamily: "var(--font-geist-mono)" },
      },
      series: [
        {
          name: "Jumlah AP",
          type: "bar",
          data: countData,
          itemStyle: {
            color: (params: any) => {
              const val = params.value;
              if (val >= 4) return "#f87171"; // Crowded (rose)
              if (val >= 2) return "#fbbf24"; // Moderate (amber)
              if (val === 1) return "#a8d94f"; // Optimal (signal lime)
              return "#27272a";
            },
            borderRadius: [4, 4, 0, 0],
          },
        },
      ],
    };
  }, [targets, activeBand]);

  return (
    <div className="p-4 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold text-zinc-200">Estimasi Tumpang Tindih Kanal (CHAN-01)</h3>
            <MethodBadge evidence="inferred" methodName="weighted_bssid_overlap_v2" />
          </div>
          <p className="text-[11px] text-zinc-500">Distribusi densitas AP & inferensi tumpang tindih kanal</p>
        </div>

        {/* Band Switcher */}
        <div className="flex items-center gap-1 p-1 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 text-xs">
          <button
            type="button"
            onClick={() => setActiveBand("2.4GHz")}
            className={`px-2.5 py-1 rounded-[var(--radius-control)] font-medium transition ${
              activeBand === "2.4GHz"
                ? "bg-[var(--color-signal)] text-zinc-950"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            2.4 GHz
          </button>
          <button
            type="button"
            onClick={() => setActiveBand("5GHz")}
            className={`px-2.5 py-1 rounded-[var(--radius-control)] font-medium transition ${
              activeBand === "5GHz"
                ? "bg-[var(--color-signal)] text-zinc-950"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            5 GHz
          </button>
        </div>
      </div>

      <div className="h-44 w-full">
        <ReactECharts option={chartOption} style={{ width: "100%", height: "100%" }} />
      </div>
    </div>
  );
}
