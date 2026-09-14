"use client";

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useScannerStore } from "@/lib/store";

export function SignalTimeline() {
  const { measurementsByTarget, selectedTargetId, targets, mode } = useScannerStore();

  const chartOption = useMemo(() => {
    // If a target is selected, display its specific timeline; otherwise display top 3 targets
    const targetIdsToShow = selectedTargetId
      ? [selectedTargetId]
      : targets.slice(0, 3).map((t) => t.target_id);

    const series = targetIdsToShow.map((tid) => {
      const history = measurementsByTarget[tid] || [];
      const targetObj = targets.find((t) => t.target_id === tid);
      const name = targetObj?.display_name || tid;

      const data = history.map((m) => [
        new Date(m.captured_at).toLocaleTimeString(),
        m.signal.smoothed_value ?? m.signal.value,
      ]);

      return {
        name,
        type: "line",
        showSymbol: false,
        smooth: true,
        data,
        lineStyle: {
          width: 2,
        },
      };
    });

    const unit = mode === "radio" ? "dBFS" : "dBm";

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: "#171b1d",
        borderColor: "#2a3033",
        textStyle: { color: "#f2f4ef", fontSize: 11 },
      },
      legend: {
        top: 0,
        textStyle: { color: "#9aa3a0", fontSize: 10 },
      },
      grid: {
        top: 30,
        left: 36,
        right: 16,
        bottom: 24,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        axisLine: { lineStyle: { color: "#2a3033" } },
        axisLabel: { color: "#71717a", fontSize: 9, fontFamily: "var(--font-geist-mono)" },
      },
      yAxis: {
        type: "value",
        min: mode === "radio" ? -110 : -95,
        max: mode === "radio" ? -20 : -30,
        axisLine: { lineStyle: { color: "#2a3033" } },
        splitLine: { lineStyle: { color: "#1c2124" } },
        axisLabel: {
          formatter: `{value} ${unit}`,
          color: "#71717a",
          fontSize: 9,
          fontFamily: "var(--font-geist-mono)",
        },
      },
      series,
      color: ["#a8d94f", "#38bdf8", "#fbbf24", "#f472b6"],
    };
  }, [measurementsByTarget, selectedTargetId, targets, mode]);

  return (
    <div className="p-4 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-zinc-200">Tren Kekuatan Sinyal (Timeline)</h3>
          <p className="text-[11px] text-zinc-500">
            {selectedTargetId ? "Fokus pada target terpilih" : "Perbandingan sinyal live"}
          </p>
        </div>
      </div>

      <div className="h-44 w-full">
        <ReactECharts option={chartOption} style={{ width: "100%", height: "100%" }} />
      </div>
    </div>
  );
}
