"use client";

import React from "react";
import { FreshnessState, SourceMethod, RssiProcessing } from "@/lib/types";
import { Pulse, Clock, ShieldCheck, Cpu } from "@phosphor-icons/react";

interface MeasurementQualityStripProps {
  freshness?: FreshnessState;
  ageMs?: number;
  actualIntervalMs?: number;
  sourceMethod?: SourceMethod;
  rssiProcessing?: RssiProcessing;
  qualityFlags?: string[];
  isScanning?: boolean;
}

export function MeasurementQualityStrip({
  freshness = "fresh",
  ageMs = 0,
  actualIntervalMs = 500,
  sourceMethod = "windows_native_wifi",
  rssiProcessing = "os_filtered",
  qualityFlags = ["calibrated"],
  isScanning = false,
}: MeasurementQualityStripProps) {
  const getFreshnessBadge = () => {
    if (!isScanning) {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-800/80 px-2 py-0.5 text-xs text-zinc-400 font-mono">
          <span className="h-1.5 w-1.5 rounded-full bg-zinc-500" />
          Standby
        </span>
      );
    }

    const ageSec = (ageMs / 1000).toFixed(1);
    switch (freshness) {
      case "fresh":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-400 font-mono">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Fresh · {ageSec}s
          </span>
        );
      case "stale":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400 font-mono">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
            Stale · {ageSec}s
          </span>
        );
      case "expired":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-xs text-rose-400 font-mono">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
            Expired
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400 font-mono">
            Freshness unknown
          </span>
        );
    }
  };

  const formatSourceMethod = (m: SourceMethod) => {
    switch (m) {
      case "windows_native_wifi":
        return "Win32 WlanApi Native";
      case "windows_netsh_fallback":
        return "Netsh CLI Fallback";
      case "bleak_ble":
        return "Bleak Core BLE";
      case "soapysdr_rx":
        return "SoapySDR Native Rx";
      case "virtual_simulator":
        return "Uncalibrated Hardware";
      default:
        return "Standard Radio Adapter";
    }
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/90 px-3.5 py-2 text-xs shadow-inner">
      <div className="flex items-center gap-2">
        <Pulse size={15} className="text-zinc-400" />
        <span className="text-zinc-400 font-medium">Measurement Quality:</span>
        {getFreshnessBadge()}
      </div>

      <div className="flex flex-wrap items-center gap-4 text-zinc-400">
        <div className="flex items-center gap-1 font-mono">
          <Clock size={13} className="text-zinc-500" />
          <span>Cadence:</span>
          <span className="text-zinc-200">{actualIntervalMs || 500}ms</span>
        </div>

        <div className="flex items-center gap-1 font-mono">
          <Cpu size={13} className="text-zinc-500" />
          <span>Driver:</span>
          <span className="text-cyan-400">{formatSourceMethod(sourceMethod)}</span>
        </div>

        <div className="flex items-center gap-1 font-mono">
          <ShieldCheck size={13} className="text-zinc-500" />
          <span>Signal:</span>
          <span className="text-zinc-200 capitalize">{rssiProcessing.replace("_", " ")}</span>
        </div>

        {qualityFlags.length > 0 && (
          <div className="flex items-center gap-1" title={qualityFlags.join(", ")}>
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-300">
              {qualityFlags.length} quality {qualityFlags.length === 1 ? "flag" : "flags"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
