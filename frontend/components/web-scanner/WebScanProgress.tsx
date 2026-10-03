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

  const isCompleted = progressPercent === 100 || activeJob?.status === "completed";
  const currentLabel = isCompleted
    ? "Audit Analysis Complete"
    : currentModule
    ? moduleLabels[currentModule] || currentModule
    : "Initializing Scan...";

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg p-4 mb-4 shadow-sm">
      <div className="flex items-center justify-between text-xs mb-2">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${
              isCompleted ? "bg-emerald-400" : "bg-blue-400 animate-ping"
            }`}
          />
          <span className="font-medium text-zinc-200">Current Phase:</span>
          <span
            className={`font-mono uppercase tracking-wide ${
              isCompleted ? "text-emerald-400" : "text-blue-400"
            }`}
          >
            {currentLabel}
          </span>
        </div>
        <span className="font-mono text-zinc-400 font-semibold">{progressPercent}%</span>
      </div>

      <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden border border-white/5">
        <div
          className={`h-full rounded-full transition-all duration-300 ease-out ${
            isCompleted ? "bg-emerald-500" : "bg-blue-500"
          }`}
          style={{ width: `${Math.max(progressPercent, 5)}%` }}
        />
      </div>
    </div>
  );
}
