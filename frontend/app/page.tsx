"use client";

import React from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ModeRail } from "@/components/controls/ModeRail";
import { CollectorPicker } from "@/components/controls/CollectorPicker";
import { SessionControls } from "@/components/controls/SessionControls";
import { MetricStrip } from "@/components/visualizers/MetricStrip";
import { ScanField } from "@/components/visualizers/ScanField";
import { NetworkField } from "@/components/visualizers/NetworkField";
import { ChannelOccupancy } from "@/components/visualizers/ChannelOccupancy";
import { SpectrumWaterfall } from "@/components/visualizers/SpectrumWaterfall";
import { SignalTimeline } from "@/components/visualizers/SignalTimeline";
import { TargetTable } from "@/components/inspector/TargetTable";
import { TargetInspector } from "@/components/inspector/TargetInspector";
import { InterfaceSummary } from "@/components/inspector/InterfaceSummary";
import { HostInventory } from "@/components/inspector/HostInventory";
import { MeasurementQualityStrip } from "@/components/dashboard/MeasurementQualityStrip";
import { PipelineHealthRail } from "@/components/dashboard/PipelineHealthRail";
import { AssociationStatus } from "@/components/dashboard/AssociationStatus";
import { AdapterConflictBanner } from "@/components/layout/AdapterConflictBanner";
import { CapabilityPreflightSheet } from "@/components/controls/CapabilityPreflightSheet";
import { SessionProvenanceDrawer } from "@/components/controls/SessionProvenanceDrawer";
import { MarkerModal } from "@/components/controls/MarkerModal";
import { WifiCredentialModal } from "@/components/modals/WifiCredentialModal";
import { ChannelEvidenceDrawer } from "@/components/channel/ChannelEvidenceDrawer";
import { Sparkle } from "@phosphor-icons/react";
import Link from "next/link";
import { useScannerStore } from "@/lib/store";
import { useSessionStream } from "@/hooks/useSessionStream";

export default function LiveScanPage() {
  const {
    mode,
    activeSession,
    selectedTargetId,
    selectedCollectorId,
    collectors,
    latestQuality,
    latestTraceId,
    connectionState,
    droppedFrames,
    activeAssociation,
    preflightModalOpen,
    setPreflightModalOpen,
    provenanceModalOpen,
    setProvenanceModalOpen,
    markerModalOpen,
    setMarkerModalOpen,
  } = useScannerStore();

  // Initialize real-time WebSocket connection to active session
  const { isConnected } = useSessionStream(activeSession?.id);

  const activeCollector = collectors.find((c) => c.id === selectedCollectorId);
  const isCollectorOnline = activeCollector?.status === "ready" || activeCollector?.status === "busy";
  const isAssociated = activeAssociation?.state === "connected";

  const leftRail = (
    <div className="space-y-6">
      <ModeRail />
      <CollectorPicker />
      <SessionControls />
    </div>
  );

  const centerStage = (
    <div className="space-y-4 max-w-4xl mx-auto">
      {/* Persistent Adapter Conflict Banner (PRD FR-ADP-01 & FR-ADP-02) */}
      <AdapterConflictBanner />

      {/* Association Status Badge */}
      <AssociationStatus />

      {/* Top Measurement Quality Strip (FQ-01) */}
      <MeasurementQualityStrip
        freshness={latestQuality?.freshness || "fresh"}
        ageMs={latestQuality?.age_ms || 0}
        actualIntervalMs={latestQuality?.actual_interval_ms || 500}
        sourceMethod={latestQuality?.source_method || (mode === "wifi" ? "windows_native_wifi" : mode === "bluetooth" ? "bleak_ble" : "soapysdr_rx")}
        rssiProcessing={latestQuality?.rssi_processing || "os_filtered"}
        qualityFlags={latestQuality?.quality_flags || []}
        isScanning={activeSession?.status === "active"}
      />

      {/* Top Metrics Row */}
      <MetricStrip />

      {/* Main Center Stage: NetworkField when Associated, ScanField when in Discover */}
      {isAssociated ? (
        <div className="space-y-4">
          <NetworkField />
          <HostInventory />
        </div>
      ) : (
        <ScanField />
      )}

      {/* Pipeline Health Rail (OBS-01) */}
      <PipelineHealthRail
        isScanning={activeSession?.status === "active"}
        wsConnected={isConnected}
        collectorOnline={isCollectorOnline}
        traceId={latestTraceId}
        sequenceLoss={droppedFrames}
      />

      {/* Mode-Specific Secondary Visualizers (only in discover mode) */}
      {!isAssociated && (
        <>
          {mode === "wifi" ? (
            <div className="space-y-4">
              <ChannelOccupancy />
              <div className="p-3.5 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)]">
                    <Sparkle size={16} weight="bold" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-zinc-100 flex items-center gap-1.5">
                      Channel Health & Recommendation Engine
                      <span className="text-[9px] font-mono uppercase px-1.5 py-0.2 rounded bg-white/5 border border-white/10 text-[var(--color-signal)]">
                        v1.2 Read-Only
                      </span>
                    </div>
                    <div className="text-[11px] text-zinc-400">
                      Analisis daya linear mW, matriks tumpang tindih spektrum, dan rekomendasi kanal terbobot.
                    </div>
                  </div>
                </div>
                <Link
                  href="/channel-health"
                  className="inline-flex min-h-8 items-center justify-center gap-1 rounded-[var(--radius-control)] bg-[var(--color-signal)] px-3 text-xs font-semibold text-zinc-950 transition-transform active:scale-[0.98] shrink-0"
                >
                  Buka Analisis &rarr;
                </Link>
              </div>
            </div>
          ) : mode === "radio" ? (
            <SpectrumWaterfall />
          ) : (
            <SignalTimeline />
          )}
        </>
      )}
    </div>
  );

  const rightInspector = (
    <div className="h-full flex flex-col space-y-3">
      {/* Interface Summary when associated */}
      <InterfaceSummary />

      {selectedTargetId ? (
        <TargetInspector />
      ) : (
        <div className="p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-2">
            <h2 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              Daftar Target Terdeteksi
            </h2>
          </div>
          <TargetTable />
        </div>
      )}
    </div>
  );

  return (
    <>
      <AppShell
        leftRail={leftRail}
        centerStage={centerStage}
        rightInspector={rightInspector}
      />

      {/* WiFi Credential & Authority Gate Modal (PRD FR-CON-03 & FR-CON-06) */}
      <WifiCredentialModal />

      {/* Preflight Diagnostics Sheet (DIAG-01) */}
      <CapabilityPreflightSheet
        collectorId={selectedCollectorId}
        mode={mode}
        isOpen={preflightModalOpen}
        onClose={() => setPreflightModalOpen(false)}
      />

      {/* Session Provenance & Evidence Drawer (PROV-01 & EVID-01) */}
      {activeSession && (
        <SessionProvenanceDrawer
          sessionId={activeSession.id}
          isOpen={provenanceModalOpen}
          onClose={() => setProvenanceModalOpen(false)}
        />
      )}

      {/* Marker Modal */}
      <MarkerModal />

      {/* Channel Evidence Drawer (v1.2) */}
      <ChannelEvidenceDrawer />
    </>
  );
}
