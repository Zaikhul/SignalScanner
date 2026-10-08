"use client";

import React, { useEffect, useRef } from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { Severity } from "@/lib/webScanTypes";
import { X } from "@phosphor-icons/react";

export function WebFindingDetail() {
  const { selectedFinding, setSelectedFinding } = useWebScanStore();
  const modalRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const triggerElementRef = useRef<HTMLElement | null>(null);

  // Capture trigger element before modal opens, restore focus on close
  useEffect(() => {
    if (selectedFinding) {
      triggerElementRef.current = document.activeElement as HTMLElement | null;
      // Focus modal close button or container
      setTimeout(() => {
        closeBtnRef.current?.focus();
      }, 50);

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          setSelectedFinding(null);
        }
      };

      window.addEventListener("keydown", handleKeyDown);
      return () => {
        window.removeEventListener("keydown", handleKeyDown);
        if (triggerElementRef.current && typeof triggerElementRef.current.focus === "function") {
          triggerElementRef.current.focus();
        }
      };
    }
  }, [selectedFinding, setSelectedFinding]);

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
    <div
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          setSelectedFinding(null);
        }
      }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs"
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="finding-detail-title"
        aria-describedby="finding-detail-reason"
        className="bg-zinc-900 border border-white/10 rounded-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col shadow-2xl animate-in fade-in zoom-in-95 duration-150"
      >
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
            <h3 id="finding-detail-title" className="text-base font-semibold text-zinc-100">
              {f.title}
            </h3>
          </div>
          <button
            ref={closeBtnRef}
            onClick={() => setSelectedFinding(null)}
            aria-label="Tutup dialog rincian temuan"
            className="p-1.5 rounded text-zinc-400 hover:text-zinc-100 hover:bg-white/5 focus:outline-none focus:ring-1 focus:ring-blue-500 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 overflow-y-auto space-y-4 text-xs">
          {/* Reason & Description */}
          <div>
            <h4 className="font-semibold text-zinc-300 mb-1">Alasan Penilaian Risiko</h4>
            <p
              id="finding-detail-reason"
              className="text-zinc-400 leading-relaxed bg-zinc-950 border border-white/5 rounded p-2.5 font-mono"
            >
              {f.severity_reason}
            </p>
          </div>

          <div>
            <h4 className="font-semibold text-zinc-300 mb-1">Deskripsi Kerentanan</h4>
            <p className="text-zinc-400 leading-relaxed">{f.description}</p>
          </div>

          <div>
            <h4 className="font-semibold text-zinc-300 mb-1">Panduan Remediasi</h4>
            <p className="text-emerald-400/90 leading-relaxed bg-emerald-950/20 border border-emerald-500/20 rounded p-2.5">
              {f.remediation}
            </p>
          </div>

          {/* Technical Evidence */}
          <div>
            <h4 className="font-semibold text-zinc-300 mb-2">Bukti Teknis & Eksik Diagnostik</h4>
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
                  <span className="text-zinc-500">Latensi Respons: </span>
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
                  <div className="text-zinc-500 mb-1">Eksik Diagnostik Redacted:</div>
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
            className="px-4 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-blue-500 transition"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
