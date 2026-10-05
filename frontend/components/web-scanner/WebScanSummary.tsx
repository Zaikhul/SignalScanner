"use client";

import React from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { Severity } from "@/lib/webScanTypes";
import { ShieldCheck, ShieldWarning, Pulse, CheckSquare } from "@phosphor-icons/react";

export function WebScanSummary() {
  const { snapshot, findings, activeJob } = useWebScanStore();

  const result = snapshot?.result;
  const counts = result?.counts_by_severity || {
    critical: findings.filter((f) => f.severity === "critical").length,
    high: findings.filter((f) => f.severity === "high").length,
    medium: findings.filter((f) => f.severity === "medium").length,
    low: findings.filter((f) => f.severity === "low").length,
    info: findings.filter((f) => f.severity === "info").length,
  };

  const totalFindings =
    counts.critical + counts.high + counts.medium + counts.low + counts.info;

  const legacy = result?.legacy_indices;
  const v2Score = legacy?.v2?.value ?? 0;
  const v47Score = legacy?.v47?.value ?? 0;
  const v75Score = legacy?.v75?.value ?? 0;

  const isTerminal = ["completed", "failed", "cancelled"].includes(activeJob?.status || "");
  const hasRun = Boolean(result) || (isTerminal && findings.length > 0);

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      {/* Findings Breakdown Card */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
          <span>Security Findings</span>
          <ShieldWarning size={16} className="text-zinc-400" />
        </div>
        <div className="text-2xl font-bold font-mono text-zinc-100 mb-3">{totalFindings}</div>
        <div className="flex flex-wrap gap-1.5 text-[11px] font-mono">
          <span className="px-1.5 py-0.5 rounded bg-red-950/60 text-red-400 border border-red-500/30">
            Crit: {counts.critical}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-orange-950/60 text-orange-400 border border-orange-500/30">
            High: {counts.high}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-400 border border-amber-500/30">
            Med: {counts.medium}
          </span>
          <span className="px-1.5 py-0.5 rounded bg-blue-950/60 text-blue-400 border border-blue-500/30">
            Low: {counts.low}
          </span>
        </div>
      </div>

      {/* V2 Risk Index */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
          <span>V2 Risk Score</span>
          <ShieldCheck size={16} className="text-zinc-400" />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-2xl font-bold font-mono text-zinc-100">{hasRun ? v2Score : "-"}</span>
          <span className="text-xs text-zinc-400 font-mono">/ 100</span>
        </div>
        <div className="text-xs text-zinc-400">
          Source Band:{" "}
          <span
            className={`font-semibold capitalize ${
              !hasRun
                ? "text-zinc-500"
                : v2Score >= 70
                ? "text-red-400"
                : v2Score >= 50
                ? "text-orange-400"
                : v2Score >= 30
                ? "text-amber-400"
                : "text-emerald-400"
            }`}
          >
            {!hasRun ? "Not Scanned" : v2Score >= 70 ? "Critical" : v2Score >= 50 ? "High" : v2Score >= 30 ? "Medium" : "Low"}
          </span>
        </div>
      </div>

      {/* Legacy Indices (v47 & v75) */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
          <span>Legacy Formulas</span>
          <Pulse size={16} className="text-zinc-400" />
        </div>
        <div className="space-y-1.5 text-xs font-mono">
          <div className="flex justify-between items-center text-zinc-300">
            <span className="text-zinc-400">V47 Index:</span>
            <span>{hasRun ? `${v47Score} / 100` : "-"}</span>
          </div>
          <div className="flex justify-between items-center text-zinc-300">
            <span className="text-zinc-400">V75 Weight:</span>
            <span>{hasRun ? `${v75Score} / 100` : "-"}</span>
          </div>
        </div>
      </div>

      {/* Requests & Telemetry */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
          <span>Audit Traffic</span>
          <CheckSquare size={16} className="text-zinc-400" />
        </div>
        <div className="space-y-1.5 text-xs font-mono">
          <div className="flex justify-between items-center text-zinc-300">
            <span className="text-zinc-400">Requests:</span>
            <span>{result?.requests.completed || 0}</span>
          </div>
          <div className="flex justify-between items-center text-zinc-300">
            <span className="text-zinc-400">Observations:</span>
            <span>{result?.observations_total || 0}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
