"use client";

import React, { useState } from "react";
import { PreflightDiagnosticResult, DiagnosticStatus, ScanMode } from "@/lib/types";
import {
  CheckCircle,
  Warning,
  XCircle,
  ArrowClockwise,
  X,
  ShieldCheck,
  Cpu,
  Database,
  Clock,
} from "@phosphor-icons/react";

interface CapabilityPreflightSheetProps {
  collectorId: string;
  mode: ScanMode;
  isOpen: boolean;
  onClose: () => void;
  onProceedToScan?: () => void;
}

export function CapabilityPreflightSheet({
  collectorId,
  mode,
  isOpen,
  onClose,
  onProceedToScan,
}: CapabilityPreflightSheetProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PreflightDiagnosticResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runPreflight = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/collectors/${collectorId}/preflight?mode=${mode}`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error(`Preflight failed with HTTP ${res.status}`);
      }
      const data: PreflightDiagnosticResult = await res.json();
      setResult(data);
    } catch (e: any) {
      setError(e.message || "Failed to execute preflight diagnostics");
    } finally {
      setLoading(false);
    }
  }, [collectorId, mode]);

  React.useEffect(() => {
    if (isOpen && collectorId) {
      runPreflight();
    }
  }, [isOpen, collectorId, runPreflight]);

  if (!isOpen) return null;

  const getStatusBadge = (status: DiagnosticStatus) => {
    switch (status) {
      case "READY":
        return (
          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400 font-mono">
            <CheckCircle size={13} weight="fill" />
            READY
          </span>
        );
      case "DEGRADED":
        return (
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-400 font-mono">
            <Warning size={13} weight="fill" />
            DEGRADED
          </span>
        );
      case "BLOCKED":
        return (
          <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-xs font-semibold text-rose-400 font-mono">
            <XCircle size={13} weight="fill" />
            BLOCKED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs font-semibold text-zinc-400 font-mono">
            UNSUPPORTED
          </span>
        );
    }
  };

  const getLayerIcon = (layer: string) => {
    switch (layer) {
      case "os_permission":
        return <ShieldCheck size={16} className="text-cyan-400" />;
      case "adapter":
        return <Cpu size={16} className="text-purple-400" />;
      case "storage_stream":
      case "backend":
        return <Database size={16} className="text-emerald-400" />;
      case "clock":
        return <Clock size={16} className="text-amber-400" />;
      default:
        return <Cpu size={16} className="text-zinc-400" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
              <ShieldCheck size={20} className="text-cyan-400" />
              Capability Preflight Diagnostics (DIAG-01)
            </h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              Verifikasi kesiapan hardware, driver OS, database, dan sinkronisasi sebelum scan
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="my-5 max-h-[60vh] overflow-y-auto pr-1 space-y-3">
          {loading && (
            <div className="flex flex-col items-center justify-center py-10 text-zinc-400">
              <ArrowClockwise size={28} className="animate-spin text-cyan-400 mb-3" />
              <p className="text-sm">Menjalankan diagnosa multi-layer...</p>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-400">
              {error}
            </div>
          )}

          {result && !loading && (
            <>
              <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/60 p-3.5">
                <div>
                  <span className="text-xs text-zinc-400">Overall Diagnostic Verdict:</span>
                  <div className="mt-1">{getStatusBadge(result.overall_status)}</div>
                </div>
                <div className="text-right text-xs text-zinc-500 font-mono">
                  <div>Platform: {result.platform}</div>
                  <div>Mode: {result.mode.toUpperCase()}</div>
                </div>
              </div>

              <div className="space-y-2.5 mt-4">
                {result.checks.map((c, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border border-zinc-800/80 bg-zinc-900/40 p-3.5 transition-colors hover:border-zinc-700"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        {getLayerIcon(c.layer)}
                        <span className="font-mono text-xs font-medium text-zinc-200 capitalize">
                          {c.name.replace(/_/g, " ")}
                        </span>
                      </div>
                      {getStatusBadge(c.status)}
                    </div>
                    <p className="mt-1.5 text-xs text-zinc-300 pl-6.5">{c.message}</p>
                    {c.technical_details && (
                      <p className="mt-1 text-[11px] font-mono text-zinc-500 pl-6.5">
                        Technical: {c.technical_details}
                      </p>
                    )}
                    {c.remediation_step && (
                      <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/5 p-2 text-xs text-amber-300/90 ml-6.5">
                        <strong>Langkah Remediasi:</strong> {c.remediation_step}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-zinc-800 pt-4">
          <button
            onClick={runPreflight}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3.5 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-700 transition-colors disabled:opacity-50"
          >
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} />
            Uji Ulang
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              Tutup
            </button>
            {onProceedToScan && result?.overall_status !== "BLOCKED" && (
              <button
                onClick={() => {
                  onClose();
                  onProceedToScan();
                }}
                className="rounded-lg bg-cyan-500 px-4 py-2 text-xs font-semibold text-zinc-950 hover:bg-cyan-400 transition-colors shadow-lg shadow-cyan-500/20"
              >
                Lanjutkan Pemindaian
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
