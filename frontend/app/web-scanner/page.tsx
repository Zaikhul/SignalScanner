"use client";

import React, { useEffect, useState } from "react";
import { Header } from "@/components/layout/Header";
import { WebScanControls } from "@/components/web-scanner/WebScanControls";
import { WebScanProgress } from "@/components/web-scanner/WebScanProgress";
import { WebScanSummary } from "@/components/web-scanner/WebScanSummary";
import { WebScanGeographyPanel } from "@/components/web-scanner/WebScanGeographyPanel";
import { WebScanCharts } from "@/components/web-scanner/WebScanCharts";
import { WebFindingTable } from "@/components/web-scanner/WebFindingTable";
import { WebFindingDetail } from "@/components/web-scanner/WebFindingDetail";
import { WebScanExportMenu } from "@/components/web-scanner/WebScanExportMenu";
import { WebScanHistory } from "@/components/web-scanner/WebScanHistory";
import { useWebScanStore } from "@/lib/webScanStore";
import { useWebScanStream } from "@/hooks/useWebScanStream";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { ShieldCheck, WarningOctagon, Info } from "@phosphor-icons/react";

export default function WebScannerPage() {
  const { activeJob, isScanning, error, setError, setSnapshot, setFindings } = useWebScanStore();
  const [capabilitiesReady, setCapabilitiesReady] = useState<boolean | null>(null);

  // Hook up WebSocket stream for active job
  const { connectionState } = useWebScanStream(activeJob?.id || null, isScanning);

  // Poll snapshot if scanning completes or on initial mount
  useEffect(() => {
    webScanApiClient
      .getCapabilities()
      .then((cap) => {
        setCapabilitiesReady(cap.readiness?.enabled ?? true);
      })
      .catch((err) => {
        setCapabilitiesReady(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <Header />

      <main className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto space-y-6">
        {/* Page Banner */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400">
                <ShieldCheck size={22} weight="bold" />
              </div>
              <h1 className="text-xl font-bold tracking-tight text-zinc-100">
                Ghost Web Scanner Domain
              </h1>
            </div>
            <p className="text-xs text-zinc-400">
              Isolated web security assessment engine: passive recon, security headers, cookie audits, and parameter diagnostics.
            </p>
          </div>

          {connectionState === "connected" && (
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/40 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>Real-Time Stream Active</span>
            </div>
          )}
        </div>

        {/* Feature Flag Disabled Warning if applicable */}
        {capabilitiesReady === false && (
          <div className="bg-amber-950/40 border border-amber-500/30 rounded-lg p-4 flex items-start gap-3 text-xs text-amber-300">
            <WarningOctagon size={18} className="shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block mb-0.5">Web Scanner Feature Flag Disabled:</span>
              The backend configuration has <code className="font-mono bg-black/40 px-1 py-0.5 rounded">WEB_SCANNER_ENABLED=False</code>. Scans cannot be executed until explicitly enabled in environment settings.
            </div>
          </div>
        )}

        {/* Error Alert */}
        {error && (
          <div className="bg-red-950/50 border border-red-500/40 rounded-lg p-3.5 flex items-center justify-between text-xs text-red-300">
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-200 font-mono text-[11px] underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Controls (Target Input, Profile, Launch) */}
        <WebScanControls />

        {/* Live Progress Bar */}
        <WebScanProgress />

        {/* Summary Metric Cards */}
        <WebScanSummary />

        {/* Scan Flow Graph / 3D Globe & Relation List */}
        <WebScanGeographyPanel />

        {/* Descriptive ECharts / Visual Distribution */}
        <WebScanCharts />

        {/* Cryptographic Deliverables Export Menu */}
        <WebScanExportMenu />

        {/* Security Findings Table */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-zinc-200">Security Findings & Diagnostic Proofs</h3>
          </div>
          <WebFindingTable />
        </div>

        {/* Finding Detail Modal */}
        <WebFindingDetail />

        {/* Audit Job History Table */}
        <WebScanHistory />
      </main>
    </div>
  );
}
