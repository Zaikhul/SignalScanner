"use client";

import React from "react";
import {
  Pulse,
  ArrowRight,
  HardDrives,
  Database,
  Broadcast,
  Desktop,
} from "@phosphor-icons/react";

interface PipelineHealthRailProps {
  isScanning: boolean;
  wsConnected: boolean;
  collectorOnline: boolean;
  latencyMs?: number;
  traceId?: string | null;
  sequenceLoss?: number;
}

export function PipelineHealthRail({
  isScanning,
  wsConnected,
  collectorOnline,
  latencyMs = 12,
  traceId,
  sequenceLoss = 0,
}: PipelineHealthRailProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/80 px-3.5 py-2 text-xs shadow-inner">
      <div className="flex items-center gap-2">
        <Pulse size={15} className="text-cyan-400" />
        <span className="text-zinc-400 font-medium">Pipeline Reliability (OBS-01):</span>
      </div>

      {/* End-to-End Hop Flow */}
      <div className="flex items-center gap-2 font-mono text-[11px]">
        {/* Collector Hop */}
        <div className="flex items-center gap-1">
          <Broadcast size={13} className={collectorOnline ? "text-emerald-400" : "text-zinc-600"} />
          <span className={collectorOnline ? "text-zinc-200" : "text-zinc-500"}>Collector</span>
        </div>
        <ArrowRight size={11} className="text-zinc-600" />

        {/* Backend Ingest Hop */}
        <div className="flex items-center gap-1">
          <HardDrives size={13} className={isScanning ? "text-emerald-400" : "text-zinc-400"} />
          <span className="text-zinc-200">Ingest</span>
        </div>
        <ArrowRight size={11} className="text-zinc-600" />

        {/* DB Persistence Hop */}
        <div className="flex items-center gap-1">
          <Database size={13} className="text-emerald-400" />
          <span className="text-zinc-200">Postgres</span>
        </div>
        <ArrowRight size={11} className="text-zinc-600" />

        {/* WebSocket Stream Hop */}
        <div className="flex items-center gap-1">
          <span className={`h-1.5 w-1.5 rounded-full ${wsConnected ? "bg-emerald-400" : "bg-rose-400"}`} />
          <span className={wsConnected ? "text-zinc-200" : "text-rose-400"}>WebSocket</span>
        </div>
        <ArrowRight size={11} className="text-zinc-600" />

        {/* UI Render Hop */}
        <div className="flex items-center gap-1">
          <Desktop size={13} className="text-cyan-400" />
          <span className="text-cyan-300">UI</span>
        </div>
      </div>

      {/* Latency & Telemetry */}
      <div className="flex items-center gap-3 text-zinc-400 font-mono text-[11px]">
        <div>
          Latency: <span className="text-emerald-400">{latencyMs}ms</span>
        </div>
        <div>
          Loss: <span className={sequenceLoss > 0 ? "text-rose-400" : "text-zinc-400"}>{sequenceLoss}</span>
        </div>
        {traceId && (
          <div className="hidden sm:block text-zinc-500" title={`Active Trace Context: ${traceId}`}>
            Trace: {traceId.slice(0, 10)}...
          </div>
        )}
      </div>
    </div>
  );
}
