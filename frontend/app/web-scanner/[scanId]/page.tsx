"use client";

import React, { useEffect, useState, use, useCallback } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/Header";
import { WebScanStatusBadge } from "@/components/web-scanner/WebScanStatusBadge";
import { WebScanSummary } from "@/components/web-scanner/WebScanSummary";
import { WebScanGeographyPanel } from "@/components/web-scanner/WebScanGeographyPanel";
import { WebScanCharts } from "@/components/web-scanner/WebScanCharts";
import { WebFindingTable } from "@/components/web-scanner/WebFindingTable";
import { WebFindingDetail } from "@/components/web-scanner/WebFindingDetail";
import { WebScanExportMenu } from "@/components/web-scanner/WebScanExportMenu";
import { useWebScanStore } from "@/lib/webScanStore";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { ArrowLeft, ArrowClockwise, ShieldWarning } from "@phosphor-icons/react";

export default function ScanDetailPage({ params }: { params: Promise<{ scanId: string }> }) {
  const { scanId } = use(params);
  const { activeJob, setActiveJob, setSnapshot, setFindings } = useWebScanStore();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadScanData = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const snap = await webScanApiClient.getSnapshot(scanId);
      if (snap?.job) {
        setActiveJob(snap.job);
      }
      setSnapshot(snap);

      const findingsPage = await webScanApiClient.listFindings(scanId, { limit: 100 });
      setFindings(findingsPage.items);
    } catch (err: any) {
      setLoadError(err.message || "Failed to load scan snapshot");
    } finally {
      setLoading(false);
    }
  }, [scanId, setActiveJob, setSnapshot, setFindings]);

  useEffect(() => {
    // Identity boundary check (T04): reset old scan data if switching to a different scanId
    const currentActiveId = useWebScanStore.getState().activeJob?.id;
    if (currentActiveId && currentActiveId !== scanId) {
      setSnapshot(null);
      setFindings([]);
    }
    loadScanData();
  }, [scanId, loadScanData, setSnapshot, setFindings]);

  const isCurrentScan = activeJob?.id === scanId;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <Header />

      <main className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto space-y-6">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <Link
            href="/web-scanner"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-100 transition"
          >
            <ArrowLeft size={14} />
            <span>Kembali ke Web Scanner</span>
          </Link>

          <button
            onClick={loadScanData}
            disabled={loading}
            className="p-1.5 rounded-md bg-zinc-900 border border-white/10 hover:bg-zinc-800 text-zinc-300 text-xs flex items-center gap-1.5 transition disabled:opacity-50"
          >
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} />
            <span>Perbarui</span>
          </button>
        </div>

        {/* Loading state for new scan */}
        {loading && !isCurrentScan && (
          <div className="h-64 flex flex-col items-center justify-center text-xs text-zinc-500 space-y-3">
            <ArrowClockwise size={24} className="animate-spin text-blue-400" />
            <span>Memuat rincian hasil pemindaian {scanId}...</span>
          </div>
        )}

        {/* Load Error Banner */}
        {loadError && (
          <div className="bg-red-950/50 border border-red-500/40 rounded-lg p-4 text-xs text-red-300 flex items-center justify-between">
            <span>{loadError}</span>
            <button onClick={loadScanData} className="underline text-red-400 hover:text-red-200 font-mono">
              Coba lagi
            </button>
          </div>
        )}

        {/* Scan Header Info (Guarded by scanId identity match) */}
        {isCurrentScan && activeJob && (
          <>
            <div className="bg-zinc-900 border border-white/10 rounded-lg p-5 space-y-3 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <h2 className="text-lg font-bold font-mono text-zinc-100">
                      {activeJob.target_display}
                    </h2>
                    <WebScanStatusBadge status={activeJob.status} />
                  </div>
                  <div className="text-xs text-zinc-400 font-mono">
                    Scan ID: <span className="text-zinc-300">{activeJob.id}</span>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <a
                    href="#findings-section"
                    className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/30 text-xs font-mono transition"
                  >
                    <ShieldWarning size={14} />
                    <span>Lihat Temuan Langsung</span>
                  </a>

                  <div className="text-right text-xs font-mono text-zinc-400 space-y-0.5">
                    <div>
                      Dibuat:{" "}
                      <span className="text-zinc-200">
                        {new Date(activeJob.created_at).toLocaleString()}
                      </span>
                    </div>
                    {activeJob.started_at && (
                      <div>
                        Dimulai:{" "}
                        <span className="text-zinc-200">
                          {new Date(activeJob.started_at).toLocaleString()}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {activeJob.status_reason && (
                <div className="p-2.5 rounded bg-zinc-950 border border-white/5 text-xs text-zinc-400 font-mono">
                  Catatan status: {activeJob.status_reason}
                </div>
              )}
            </div>

            {/* Summary Metric Cards & Coverage */}
            <WebScanSummary />

            {/* Priority Findings Table (T15 Hierarchy) */}
            <div id="findings-section" className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-zinc-200">
                  Temuan Keamanan & Bukti Diagnostik
                </h3>
              </div>
              <WebFindingTable />
            </div>

            {/* Scan Flow Graph / 3D Globe & Relation List */}
            <WebScanGeographyPanel scanId={scanId} />

            {/* Visual Charts & Telemetry */}
            <WebScanCharts />

            {/* Deliverables Export Menu */}
            <WebScanExportMenu />

            {/* Finding Detail Modal */}
            <WebFindingDetail />
          </>
        )}
      </main>
    </div>
  );
}
