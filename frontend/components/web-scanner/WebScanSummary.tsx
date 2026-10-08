"use client";

import React from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { Severity } from "@/lib/webScanTypes";
import { ShieldCheck, ShieldWarning, Pulse, CheckSquare, ListChecks } from "@phosphor-icons/react";

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

  const riskyFindings = counts.critical + counts.high + counts.medium + counts.low;
  const totalFindings = riskyFindings + counts.info;

  // Strict check on V2 Risk Index presence to eliminate false low assurance (T01)
  const v2 = result?.legacy_indices?.v2;
  const hasV2 = typeof v2?.value === "number";
  const v2Score = hasV2 ? v2.value : null;

  const v47 = result?.legacy_indices?.v47;
  const hasV47 = typeof v47?.value === "number";
  const v47Score = hasV47 ? v47.value : null;

  const v75 = result?.legacy_indices?.v75;
  const hasV75 = typeof v75?.value === "number";
  const v75Score = hasV75 ? v75.value : null;

  const isTerminal = ["completed", "failed", "cancelled", "partial"].includes(activeJob?.status || "");
  const hasRun = Boolean(result) && (isTerminal || Boolean(activeJob?.ended_at));

  // Checks coverage breakdown from result.coverage
  const coverage = result?.coverage || [];
  const checksCompleted = coverage.filter((c) => c.status === "completed").length;
  const checksSkipped = coverage.filter((c) => c.status === "skipped").length;
  const checksFailed = coverage.filter((c) => c.status === "failed").length;
  const checksInconclusive = coverage.filter((c) => c.status === "inconclusive").length;
  const totalChecks = coverage.length;

  return (
    <div className="space-y-4 mb-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        {/* Findings Breakdown Card */}
        <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
          <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
            <span>Temuan Keamanan</span>
            <ShieldWarning size={16} className="text-zinc-400" />
          </div>
          <div className="flex items-baseline gap-2 mb-3">
            <span className="text-2xl font-bold font-mono text-zinc-100">{riskyFindings}</span>
            <span className="text-xs text-zinc-400 font-mono">berisiko</span>
            {counts.info > 0 && (
              <span className="text-xs text-zinc-500 font-mono">({counts.info} info)</span>
            )}
          </div>
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
            <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
              Info: {counts.info}
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
            <span className="text-2xl font-bold font-mono text-zinc-100">
              {hasV2 ? v2Score : "—"}
            </span>
            {hasV2 && <span className="text-xs text-zinc-400 font-mono">/ 100</span>}
          </div>
          <div className="text-xs text-zinc-400">
            Kategori Risiko:{" "}
            <span
              className={`font-semibold capitalize ${
                !hasV2
                  ? "text-zinc-500"
                  : v2Score! >= 70
                  ? "text-red-400"
                  : v2Score! >= 50
                  ? "text-orange-400"
                  : v2Score! >= 30
                  ? "text-amber-400"
                  : "text-emerald-400"
              }`}
            >
              {!hasV2
                ? activeJob?.status === "scanning"
                  ? "Sedang Menilai..."
                  : "Belum Dinilai"
                : v2Score! >= 70
                ? "Critical"
                : v2Score! >= 50
                ? "High"
                : v2Score! >= 30
                ? "Medium"
                : "Low"}
            </span>
          </div>
        </div>

        {/* Legacy Indices (v47 & v75) */}
        <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
          <div className="flex items-center justify-between text-xs text-zinc-400 mb-2">
            <span>Formula Legacy</span>
            <Pulse size={16} className="text-zinc-400" />
          </div>
          <div className="space-y-1.5 text-xs font-mono">
            <div className="flex justify-between items-center text-zinc-300">
              <span className="text-zinc-400">V47 Index:</span>
              <span>{hasV47 ? `${v47Score} / 100` : "—"}</span>
            </div>
            <div className="flex justify-between items-center text-zinc-300">
              <span className="text-zinc-400">V75 Weight:</span>
              <span>{hasV75 ? `${v75Score} / 100` : "—"}</span>
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

      {/* Coverage & Checks Summary Strip (T01) */}
      {totalChecks > 0 && (
        <div className="bg-zinc-900/60 border border-white/5 rounded-lg px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-zinc-300">
            <ListChecks size={16} className="text-blue-400" />
            <span className="font-medium">Cakupan Pemeriksaan ({totalChecks} checks terdaftar):</span>
          </div>
          <div className="flex flex-wrap items-center gap-3 font-mono text-[11px]">
            <span className="text-emerald-400 font-semibold">{checksCompleted} Selesai</span>
            {checksSkipped > 0 && (
              <span className="text-zinc-400">{checksSkipped} Dilewati</span>
            )}
            {checksInconclusive > 0 && (
              <span className="text-amber-400">{checksInconclusive} Tidak Konklusif</span>
            )}
            {checksFailed > 0 && (
              <span className="text-red-400">{checksFailed} Gagal</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
