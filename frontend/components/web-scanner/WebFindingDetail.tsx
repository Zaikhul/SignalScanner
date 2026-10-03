"use client";

import React from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { Severity } from "@/lib/webScanTypes";
import { X } from "@phosphor-icons/react";

export function WebFindingDetail() {
  const { selectedFinding, setSelectedFinding } = useWebScanStore();

  if (!selectedFinding) return null;

  const f = selectedFinding;
  const evidence = f.evidence || {};

  const severityBadges: Record<Severity, string> = {
    critical: "bg-red-950/60 text-red-400 border-red-500/30",
    high: "bg-orange-950/60 text-orange-400 border-orange-500/30",
    medium: "bg-amber-950/60 text-amber-400 border-amber-500/30",
    low: "bg-blue-950/60 text-blue-400 border-blue-500/30",
    info: "bg-zinc-800 text-zinc-300 border-zinc-700",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
      <div className="bg-zinc-900 border border-white/10 rounded-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col shadow-2xl">
        {/* Modal Header */}
        <div className="p-4 border-b border-white/10 flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded font-mono uppercase text-[10px] font-semibold border ${
                  severityBadges[f.severity]
                }`}
              >
                {f.severity}
              </span>
              <span className="text-xs font-mono text-zinc-400">{f.check_id}</span>
            </div>
            <h3 className="text-base font-semibold text-zinc-100">{f.title}</h3>
          </div>
          <button
            onClick={() => setSelectedFinding(null)}
            className="p-1 rounded text-zinc-400 hover:text-zinc-100 hover:bg-white/5 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 overflow-y-auto space-y-4 text-xs">
          {/* Reason & Description */}
          <div>
            <h4 className="font-semibold text-zinc-300 mb-1">Reason for Assessment</h4>
            <p className="text-zinc-400 leading-relaxed bg-zinc-950 border border-white/5 rounded p-2.5 font-mono">
              {f.severity_reason}
            </p>
          </div>

          <div>
            <h4 className="font-semibold text-zinc-300 mb-1">Vulnerability Description</h4>
            <p className="text-zinc-400 leading-relaxed">{f.description}</p>
          </div>

          <div>
            <h4 className="font-semibold text-zinc-300 mb-1">Remediation Guidance</h4>
            <p className="text-emerald-400/90 leading-relaxed bg-emerald-950/20 border border-emerald-500/20 rounded p-2.5">
              {f.remediation}
            </p>
          </div>

          {/* Technical Evidence */}
          <div>
            <h4 className="font-semibold text-zinc-300 mb-2">Technical Evidence & Diagnostic Excerpts</h4>
            <div className="bg-zinc-950 border border-white/10 rounded-md p-3 space-y-2 font-mono text-[11px]">
              {evidence.url_display && (
                <div>
                  <span className="text-zinc-500">Target URL: </span>
                  <span className="text-zinc-200 break-all">{evidence.url_display}</span>
                </div>
              )}
              {evidence.status_code && (
                <div>
                  <span className="text-zinc-500">HTTP Status: </span>
                  <span className="text-zinc-200">{evidence.status_code}</span>
                </div>
              )}
              {evidence.elapsed_ms !== null && evidence.elapsed_ms !== undefined && (
                <div>
                  <span className="text-zinc-500">Response Latency: </span>
                  <span className="text-zinc-200">
                    {evidence.elapsed_ms.toFixed(1)} ms
                    {evidence.baseline_elapsed_ms
                      ? ` (Baseline: ${evidence.baseline_elapsed_ms.toFixed(1)} ms)`
                      : ""}
                  </span>
                </div>
              )}

              {evidence.excerpts && evidence.excerpts.length > 0 && (
                <div className="pt-2 border-t border-white/5 space-y-1">
                  <div className="text-zinc-500 mb-1">Redacted Diagnostic Excerpts:</div>
                  {evidence.excerpts.map((ex, i) => (
                    <div
                      key={i}
                      className="bg-zinc-900 border border-white/5 px-2 py-1 rounded text-amber-300/90 overflow-x-auto whitespace-pre-wrap"
                    >
                      {ex.value_redacted}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-3 border-t border-white/10 flex justify-end bg-zinc-950/40">
          <button
            onClick={() => setSelectedFinding(null)}
            className="px-4 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
