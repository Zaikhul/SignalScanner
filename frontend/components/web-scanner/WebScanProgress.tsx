"use client";

import React from "react";
import { useWebScanStore } from "@/lib/webScanStore";

export function WebScanProgress() {
  const { isScanning, progressPercent, currentModule, activeJob } = useWebScanStore();

  if (!isScanning && (!activeJob || activeJob.status !== "scanning")) {
    return null;
  }

  const moduleLabels: Record<string, string> = {
    recon: "Recon & Fingerprinting",
    headers: "Security Headers Audit",
    cookies: "Cookie Flags & Session Audit",
    forms: "Form Vulnerabilities & CSRF",
    parameters: "Parameter Injections (SQL/NoSQL/XSS)",
    header_probes: "Header Injection Diagnostics",
    stress: "Load Resilience Benchmark",
    load_resilience: "Load Resilience Benchmark",
    completed: "Audit Analysis Complete",
  };

  const status = activeJob?.status;
  const isTerminal = status === "completed" || status === "partial" || status === "failed" || status === "cancelled";

  let statusLabel = currentModule ? moduleLabels[currentModule] || currentModule : "Inisialisasi Pemindaian...";
  let dotColor = "bg-blue-400 motion-safe:animate-pulse";
  let textColor = "text-blue-400";
  let barColor = "bg-blue-500";

  if (status === "completed") {
    statusLabel = "Audit Analysis Complete";
    dotColor = "bg-emerald-400";
    textColor = "text-emerald-400";
    barColor = "bg-emerald-500";
  } else if (status === "partial") {
    statusLabel = "Audit Analysis Partial";
    dotColor = "bg-amber-400";
    textColor = "text-amber-400";
    barColor = "bg-amber-500";
  } else if (status === "failed") {
    statusLabel = "Scan Failed";
    dotColor = "bg-red-400";
    textColor = "text-red-400";
    barColor = "bg-red-500";
  } else if (status === "cancelled") {
    statusLabel = "Scan Cancelled";
    dotColor = "bg-zinc-400";
    textColor = "text-zinc-400";
    barColor = "bg-zinc-500";
  } else if (progressPercent >= 100) {
    statusLabel = "Menyimpan & Merekonsiliasi Hasil...";
    dotColor = "bg-blue-400 motion-safe:animate-pulse";
    textColor = "text-blue-400";
    barColor = "bg-blue-500";
  }

  const clampedPercent = Math.min(100, Math.max(0, progressPercent));

  return (
    <div
      role="progressbar"
      aria-valuenow={clampedPercent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Progres Pemindaian: ${statusLabel}`}
      className="bg-zinc-900 border border-white/10 rounded-lg p-4 mb-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs mb-2">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dotColor}`} />
          <span className="font-medium text-zinc-200">Fase Saat Ini:</span>
          <span className={`font-mono uppercase tracking-wide ${textColor}`}>
            {statusLabel}
          </span>
        </div>
        <span className="font-mono text-zinc-400 font-semibold">{clampedPercent}%</span>
      </div>

      <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden border border-white/5">
        <div
          className={`h-full rounded-full transition-all duration-300 ease-out ${barColor}`}
          style={{ width: `${clampedPercent}%` }}
        />
      </div>
    </div>
  );
}
