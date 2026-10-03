"use client";

import React, { useEffect, useState, use, useCallback } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/Header";
import { WebScanStatusBadge } from "@/components/web-scanner/WebScanStatusBadge";
import { WebScanSummary } from "@/components/web-scanner/WebScanSummary";
import { WebScanCharts } from "@/components/web-scanner/WebScanCharts";
import { WebFindingTable } from "@/components/web-scanner/WebFindingTable";
import { WebFindingDetail } from "@/components/web-scanner/WebFindingDetail";
import { WebScanExportMenu } from "@/components/web-scanner/WebScanExportMenu";
import { useWebScanStore } from "@/lib/webScanStore";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { ArrowLeft, ArrowClockwise } from "@phosphor-icons/react";

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
      setSnapshot(snap);
      setActiveJob(snap.job);

      const findingsPage = await webScanApiClient.listFindings(scanId, { limit: 100 });
      setFindings(findingsPage.items);
    } catch (err: any) {
      setLoadError(err.message || "Failed to load scan snapshot");
    } finally {
      setLoading(false);
    }
  }, [scanId, setActiveJob, setSnapshot, setFindings]);

  useEffect(() => {
    loadScanData();
  }, [loadScanData]);

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
            <span>Back to Web Scanner</span>
          </Link>

          <button
            onClick={loadScanData}
            disabled={loading}
            className="p-1.5 rounded-md bg-zinc-900 border border-white/10 hover:bg-zinc-800 text-zinc-300 text-xs flex items-center gap-1.5 transition"
          >
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Scan Header Info */}
        {activeJob && (
          <div className="bg-zinc-900 border border-white/10 rounded-lg p-5 space-y-3">
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

              <div className="text-right text-xs font-mono text-zinc-400 space-y-0.5">
                <div>
                  Created:{" "}
                  <span className="text-zinc-200">
                    {new Date(activeJob.created_at).toLocaleString()}
                  </span>
                </div>
                {activeJob.started_at && (
                  <div>
                    Started:{" "}
                    <span className="text-zinc-200">
                      {new Date(activeJob.started_at).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {activeJob.status_reason && (
              <div className="p-2.5 rounded bg-zinc-950 border border-white/5 text-xs text-zinc-400 font-mono">
                Status note: {activeJob.status_reason}
              </div>
            )}
          </div>
        )}

        {loadError && (
          <div className="bg-red-950/50 border border-red-500/40 rounded-lg p-4 text-xs text-red-300">
            {loadError}
          </div>
        )}

        {/* Summary Metric Cards */}
        <WebScanSummary />

        {/* Deliverables Export Menu */}
        <WebScanExportMenu />

        {/* Visual Charts */}
        <WebScanCharts />

        {/* Findings Table */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-zinc-200">Security Findings & Diagnostic Proofs</h3>
          <WebFindingTable />
        </div>

        {/* Finding Detail Modal */}
        <WebFindingDetail />
      </main>
    </div>
  );
}
