"use client";

import React from "react";
import { useScannerStore } from "@/lib/store";

export function MetricStrip() {
  const { targets, mode, droppedFrames } = useScannerStore();

  const maxSignal =
    targets.length > 0
      ? Math.max(...targets.map((t) => t.latest_signal))
      : null;

  const validSnrs = targets.map((t) => t.avg_snr).filter((s): s is number => s !== null && s !== undefined);
  const avgSnr =
    validSnrs.length > 0
      ? Math.round((validSnrs.reduce((a, b) => a + b, 0) / validSnrs.length) * 10) / 10
      : null;

  const unit = mode === "radio" ? "dBFS" : "dBm";

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {/* Target count */}
      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
        <span className="text-[11px] text-zinc-400 block font-medium">Target Terdeteksi</span>
        <div className="flex items-baseline gap-1 mt-0.5">
          <span className="font-mono text-xl font-semibold tabular-nums text-zinc-100">
            {targets.length}
          </span>
          <span className="text-[10px] text-zinc-500 font-mono">emitter</span>
        </div>
      </div>

      {/* Peak Signal */}
      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
        <span className="text-[11px] text-zinc-400 block font-medium">Kekuatan Puncak</span>
        <div className="flex items-baseline gap-1 mt-0.5">
          <span className="font-mono text-xl font-semibold tabular-nums text-[var(--color-signal)]">
            {maxSignal !== null ? `${maxSignal.toFixed(1)}` : "--.-"}
          </span>
          <span className="text-[10px] text-zinc-500 font-mono">{unit}</span>
        </div>
      </div>

      {/* Average SNR */}
      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
        <span className="text-[11px] text-zinc-400 block font-medium">Rata-rata SNR</span>
        <div className="flex items-baseline gap-1 mt-0.5">
          <span className="font-mono text-xl font-semibold tabular-nums text-zinc-100">
            {avgSnr !== null ? `${avgSnr.toFixed(1)}` : "--.-"}
          </span>
          <span className="text-[10px] text-zinc-500 font-mono">dB</span>
        </div>
      </div>

      {/* Frame Quality / Integrity */}
      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
        <span className="text-[11px] text-zinc-400 block font-medium">Integritas Stream</span>
        <div className="flex items-baseline gap-1 mt-0.5">
          <span
            className={`font-mono text-xl font-semibold tabular-nums ${
              droppedFrames === 0 ? "text-zinc-100" : "text-amber-400"
            }`}
          >
            {droppedFrames === 0 ? "100%" : `${droppedFrames} drop`}
          </span>
          <span className="text-[10px] text-zinc-500 font-mono">seq sync</span>
        </div>
      </div>
    </div>
  );
}
