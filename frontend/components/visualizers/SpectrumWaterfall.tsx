"use client";

import React, { useEffect, useMemo, useRef } from "react";
import ReactECharts from "echarts-for-react";
import { useScannerStore } from "@/lib/store";

export function SpectrumWaterfall() {
  const { latestFftBins, latestFftCenterFreq } = useScannerStore();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const waterfallHistory = useRef<number[][]>([]);

  // Update scrolling waterfall canvas
  useEffect(() => {
    if (!latestFftBins || latestFftBins.length === 0) return;

    waterfallHistory.current.unshift(latestFftBins);
    if (waterfallHistory.current.length > 80) {
      waterfallHistory.current.pop();
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const history = waterfallHistory.current;
    const rowHeight = height / 80;

    ctx.clearRect(0, 0, width, height);

    history.forEach((row, rowIdx) => {
      const y = rowIdx * rowHeight;
      const binWidth = width / row.length;

      row.forEach((dbfs, binIdx) => {
        const x = binIdx * binWidth;
        // Normalize dBFS between -100 (black/blue) and -30 (signal lime/bright yellow)
        const norm = Math.max(0, Math.min(1, (dbfs + 100) / 70));

        let r = 0, g = 0, b = 0;
        if (norm < 0.3) {
          // Dark zinc/blue noise
          b = Math.floor(norm * 3 * 80);
        } else if (norm < 0.7) {
          // Signal lime transition
          const t = (norm - 0.3) / 0.4;
          r = Math.floor(t * 168);
          g = Math.floor(t * 217);
          b = Math.floor(t * 79);
        } else {
          // Intense peak (yellow/white)
          const t = (norm - 0.7) / 0.3;
          r = Math.floor(168 + t * 87);
          g = Math.floor(217 + t * 38);
          b = Math.floor(79 + t * 176);
        }

        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(x, y, Math.ceil(binWidth), Math.ceil(rowHeight));
      });
    });
  }, [latestFftBins]);

  // Spectrum FFT line chart
  const lineOption = useMemo(() => {
    const bins = latestFftBins.length > 0 ? latestFftBins : Array.from({ length: 128 }, () => -95);
    const spanMhz = 2.0; // 2 MHz span default
    const startMhz = (latestFftCenterFreq - 1000000) / 1e6;
    const stepMhz = spanMhz / bins.length;

    const xData = bins.map((_, i) => (startMhz + i * stepMhz).toFixed(3));

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: "#171b1d",
        borderColor: "#2a3033",
        textStyle: { color: "#f2f4ef", fontSize: 11 },
        formatter: (params: any) => {
          const freq = params[0]?.axisValue;
          const pwr = params[0]?.value;
          return `<div style="font-family: var(--font-geist-mono);">Freq: <b>${freq} MHz</b><br/>Power: <b>${pwr} dBFS</b></div>`;
        },
      },
      grid: {
        top: 20,
        left: 36,
        right: 16,
        bottom: 24,
      },
      xAxis: {
        type: "category",
        data: xData,
        axisLine: { lineStyle: { color: "#2a3033" } },
        axisLabel: {
          interval: Math.floor(bins.length / 5),
          color: "#71717a",
          fontSize: 9,
          fontFamily: "var(--font-geist-mono)",
        },
      },
      yAxis: {
        type: "value",
        min: -110,
        max: -20,
        axisLine: { lineStyle: { color: "#2a3033" } },
        splitLine: { lineStyle: { color: "#1c2124" } },
        axisLabel: {
          formatter: "{value} dBFS",
          color: "#71717a",
          fontSize: 9,
          fontFamily: "var(--font-geist-mono)",
        },
      },
      series: [
        {
          type: "line",
          data: bins,
          showSymbol: false,
          lineStyle: { color: "#a8d94f", width: 1.5 },
          areaStyle: {
            color: "rgba(168, 217, 79, 0.1)",
          },
        },
      ],
    };
  }, [latestFftBins, latestFftCenterFreq]);

  return (
    <div className="space-y-3">
      {/* Real-time Spectrum Line */}
      <div className="p-4 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-semibold text-zinc-200">RF Spectrum FFT (dBFS)</h3>
            <p className="text-[11px] text-zinc-500">
              Center: {(latestFftCenterFreq / 1e6).toFixed(2)} MHz | Span: 2.0 MHz
            </p>
          </div>
        </div>
        <div className="h-44 w-full">
          <ReactECharts option={lineOption} style={{ width: "100%", height: "100%" }} />
        </div>
      </div>

      {/* 2D Scrolling Waterfall Canvas */}
      <div className="p-4 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-semibold text-zinc-200">Spectrum Waterfall</h3>
            <p className="text-[11px] text-zinc-500">Densitas energi frekuensi dari waktu ke waktu</p>
          </div>
        </div>
        <div className="w-full h-36 rounded-[var(--radius-control)] border border-white/10 bg-black overflow-hidden relative">
          <canvas ref={canvasRef} width={500} height={140} className="w-full h-full object-fill" />
        </div>
      </div>
    </div>
  );
}
