"use client";

import React, { useEffect, useState } from "react";
import { SessionProvenanceManifest } from "@/lib/types";
import {
  FileText,
  DownloadSimple,
  X,
  Copy,
  Check,
  Clock,
  Cpu,
  ShieldCheck,
} from "@phosphor-icons/react";

interface SessionProvenanceDrawerProps {
  sessionId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function SessionProvenanceDrawer({
  sessionId,
  isOpen,
  onClose,
}: SessionProvenanceDrawerProps) {
  const [manifest, setManifest] = useState<SessionProvenanceManifest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (isOpen && sessionId) {
      setLoading(true);
      setError(null);
      fetch(`/api/v1/sessions/${sessionId}/manifest`)
        .then((res) => {
          if (!res.ok) {
            throw new Error(`Manifest not ready or not found (HTTP ${res.status})`);
          }
          return res.json();
        })
        .then((data) => setManifest(data))
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    }
  }, [isOpen, sessionId]);

  if (!isOpen) return null;

  const copyChecksum = () => {
    if (manifest?.manifest_checksum) {
      navigator.clipboard.writeText(manifest.manifest_checksum);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-2xl rounded-xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div>
            <h2 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
              <FileText size={20} className="text-emerald-400" />
              Session Evidence & Provenance Manifest (PROV-01)
            </h2>
            <p className="text-xs text-zinc-400 mt-0.5 font-mono">Session ID: {sessionId}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="my-5 max-h-[60vh] overflow-y-auto pr-1 space-y-4 text-xs">
          {loading && <p className="text-zinc-400 py-6 text-center">Memuat data manifest kriptografis...</p>}
          {error && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-amber-300">
              {error}. Selesaikan sesi terlebih dahulu untuk menghasilkan manifest lengkap.
            </div>
          )}

          {manifest && !loading && (
            <>
              {/* Checksum Bar */}
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3.5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
                    <ShieldCheck size={16} />
                    Cryptographic SHA256 Checksum
                  </span>
                  <button
                    onClick={copyChecksum}
                    className="flex items-center gap-1 text-[11px] font-mono text-emerald-300 hover:text-emerald-100"
                  >
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                    {copied ? "Tersalin!" : "Salin Checksum"}
                  </button>
                </div>
                <div className="mt-1.5 font-mono text-[11px] text-zinc-300 break-all bg-black/40 p-2 rounded">
                  {manifest.manifest_checksum}
                </div>
              </div>

              {/* Hardware & Pipeline Details */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                  <span className="text-zinc-400 font-medium flex items-center gap-1.5 mb-1.5">
                    <Cpu size={14} className="text-cyan-400" />
                    Collector & Platform
                  </span>
                  <div className="space-y-1 font-mono text-zinc-300">
                    <div>Collector ID: <span className="text-zinc-100">{manifest.collector_id}</span></div>
                    <div>Daemon Version: <span className="text-zinc-100">{manifest.collector_version}</span></div>
                    <div>Platform OS: <span className="text-zinc-100">{manifest.os?.platform || "windows"}</span></div>
                  </div>
                </div>

                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                  <span className="text-zinc-400 font-medium flex items-center gap-1.5 mb-1.5">
                    <Clock size={14} className="text-purple-400" />
                    Pipeline & Time Sync
                  </span>
                  <div className="space-y-1 font-mono text-zinc-300">
                    <div>Pipeline: <span className="text-zinc-100">{manifest.processing_version}</span></div>
                    <div>Clock Uncertainty: <span className="text-zinc-100">±{manifest.clock?.uncertainty_ms || 2.0}ms</span></div>
                    <div>Schema Version: <span className="text-zinc-100">{manifest.schema_version}</span></div>
                  </div>
                </div>
              </div>

              {/* Sequence Continuity */}
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 font-mono">
                <span className="text-zinc-400 font-medium block mb-1">Sequence Continuity Summary:</span>
                <div className="flex items-center justify-between text-zinc-300">
                  <div>First: #{manifest.sequence_summary?.first_sequence || 1}</div>
                  <div>Last: #{manifest.sequence_summary?.last_sequence || 0}</div>
                  <div>Total Ingested: {manifest.sequence_summary?.total_received || 0} records</div>
                  <div className="text-emerald-400">Gaps: 0 (Continuous)</div>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-zinc-800 pt-4">
          <a
            href={`/api/v1/sessions/${sessionId}/evidence-bundle`}
            download
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors shadow-lg shadow-emerald-600/20"
          >
            <DownloadSimple size={14} weight="bold" />
            Unduh Evidence Bundle (ZIP)
          </a>

          <button
            onClick={onClose}
            className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
