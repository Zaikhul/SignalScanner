"use client";

import React from "react";
import { X, PushPin, Broadcast, CheckCircle, Clock, ShieldCheck, ChartLine } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";
import { SignalTimeline } from "../visualizers/SignalTimeline";
import { ConnectAction } from "./ConnectAction";

export function TargetInspector() {
  const {
    selectedTargetId,
    setSelectedTargetId,
    targets,
    activeSession,
    setTargets,
    inspectorOpen,
    setInspectorOpen,
  } = useScannerStore();

  const target = targets.find((t) => t.target_id === selectedTargetId);

  if (!target) {
    return (
      <div className="p-5 border-l border-white/10 bg-zinc-950/95 h-full flex flex-col items-center justify-center text-center text-zinc-500 text-xs">
        <Broadcast size={28} className="text-zinc-600 mb-2" />
        <p className="font-medium text-zinc-400">Inspektur Target</p>
        <p className="text-[11px] text-zinc-600 mt-1 max-w-[200px]">
          Pilih salah satu beacon pada radar atau daftar target untuk melihat telemetri detail.
        </p>
      </div>
    );
  }

  const handleTogglePin = async () => {
    if (!activeSession) return;
    try {
      const res = await apiClient.togglePinTarget(activeSession.id, target.target_id);
      setTargets(
        targets.map((t) =>
          t.target_id === target.target_id ? { ...t, is_pinned: res.is_pinned } : t
        )
      );
    } catch (e) {
      console.error("Failed to toggle pin", e);
    }
  };

  return (
    <aside className="border-l border-white/10 bg-zinc-950/95 p-4 lg:p-5 h-full flex flex-col gap-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-white/10 pb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-zinc-100 truncate">
              {target.display_name || "Emitter"}
            </h2>
            <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-[var(--color-surface)] border border-white/10 text-zinc-400">
              {target.mode}
            </span>
          </div>
          <div className="text-[11px] font-mono text-zinc-500 mt-0.5 truncate">
            {target.target_id}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleTogglePin}
            className={`p-1.5 rounded-[var(--radius-control)] border transition ${
              target.is_pinned
                ? "bg-[var(--color-signal)] text-zinc-950 border-[var(--color-signal)]"
                : "border-white/10 text-zinc-400 hover:text-zinc-100 hover:bg-white/5"
            }`}
          >
            <PushPin size={15} weight={target.is_pinned ? "fill" : "regular"} />
          </button>
          <button
            type="button"
            onClick={() => setSelectedTargetId(null)}
            className="p-1.5 rounded-[var(--radius-control)] border border-white/10 text-zinc-400 hover:text-zinc-100 hover:bg-white/5 transition"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {/* Primary Metrics Grid */}
      <div className="grid grid-cols-2 gap-2">
        <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
          <span className="text-[10px] text-zinc-500 block font-medium">Sinyal Live</span>
          <div className="flex items-baseline gap-1 mt-0.5">
            <span className="font-mono text-lg font-semibold tabular-nums text-[var(--color-signal)]">
              {target.latest_signal}
            </span>
            <span className="text-[10px] text-zinc-500 font-mono">{target.unit}</span>
          </div>
        </div>

        <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
          <span className="text-[10px] text-zinc-500 block font-medium">Signal-to-Noise</span>
          <div className="flex items-baseline gap-1 mt-0.5">
            <span className="font-mono text-lg font-semibold tabular-nums text-zinc-100">
              {target.avg_snr !== null && target.avg_snr !== undefined ? `${target.avg_snr}` : "--"}
            </span>
            <span className="text-[10px] text-zinc-500 font-mono">dB</span>
          </div>
        </div>

        <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
          <span className="text-[10px] text-zinc-500 block font-medium">Min / Max RSSI</span>
          <div className="font-mono text-xs font-medium tabular-nums text-zinc-200 mt-1">
            {target.min_signal} / {target.max_signal} {target.unit}
          </div>
        </div>

        <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10">
          <span className="text-[10px] text-zinc-500 block font-medium">Total Sampel</span>
          <div className="font-mono text-xs font-medium tabular-nums text-zinc-200 mt-1">
            {target.sample_count} frames
          </div>
        </div>
      </div>

      {/* Target Details */}
      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 space-y-2 text-xs">
        <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider block">
          Spesifikasi Radio & Jaringan
        </span>

        {target.channel && (
          <div className="flex items-center justify-between text-zinc-300">
            <span className="text-zinc-500">Kanal Frekuensi:</span>
            <span className="font-mono text-zinc-200">
              Kanal {target.channel} ({target.band || "N/A"})
            </span>
          </div>
        )}

        <div className="flex items-center justify-between text-zinc-300">
          <span className="text-zinc-500">Pertama Dilihat:</span>
          <span className="font-mono text-[11px] text-zinc-300">
            {new Date(target.first_seen).toLocaleTimeString()}
          </span>
        </div>

        <div className="flex items-center justify-between text-zinc-300">
          <span className="text-zinc-500">Terakhir Update:</span>
          <span className="font-mono text-[11px] text-zinc-300">
            {new Date(target.last_seen).toLocaleTimeString()}
          </span>
        </div>

        {target.extra && target.extra.security && (
          <div className="flex items-center justify-between text-zinc-300">
            <span className="text-zinc-500">Keamanan:</span>
            <span className="font-mono text-[11px] text-zinc-200">{target.extra.security}</span>
          </div>
        )}

        {target.extra && target.extra.manufacturer && (
          <div className="flex items-center justify-between text-zinc-300">
            <span className="text-zinc-500">Manufacturer:</span>
            <span className="font-mono text-[11px] text-zinc-200">{target.extra.manufacturer}</span>
          </div>
        )}
      </div>

      {/* Connect Action for WiFi Networks */}
      <ConnectAction target={target} />

      {/* Focused Signal Timeline */}
      <div className="space-y-1">
        <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider block">
          Riwayat Sinyal Target
        </span>
        <SignalTimeline />
      </div>
    </aside>
  );
}
