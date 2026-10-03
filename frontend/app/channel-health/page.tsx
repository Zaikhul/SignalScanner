"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/Header";
import { ChannelRecommendationCard } from "@/components/channel/ChannelRecommendationCard";
import { ChannelHealthMatrix } from "@/components/channel/ChannelHealthMatrix";
import { ChannelEvidenceDrawer } from "@/components/channel/ChannelEvidenceDrawer";
import { ChannelComparison } from "@/components/channel/ChannelComparison";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";
import { Sparkle, Sliders, Broadcast, ArrowsClockwise } from "@phosphor-icons/react";

export default function ChannelHealthPage() {
  const {
    activeSession,
    channelHealthSnapshot,
    setChannelHealthSnapshot,
    latestRecommendation,
    setLatestRecommendation,
    channelValidations,
    setChannelValidations,
    addChannelValidation,
  } = useScannerStore();

  const [activeBand, setActiveBand] = useState<"2.4GHz" | "5GHz">("2.4GHz");
  const [windowSec, setWindowSec] = useState<number>(300);
  const [regulatoryDomain, setRegulatoryDomain] = useState<string>("ID");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const sessionId = activeSession?.id;

  // Fetch or evaluate channel health on mount / session / band change
  const fetchChannelHealth = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      try {
        const snap = await apiClient.getChannelHealth(sessionId, activeBand);
        setChannelHealthSnapshot(snap);
      } catch {
        // If not yet generated, ignore
      }

      try {
        const rec = await apiClient.getLatestRecommendation(sessionId);
        setLatestRecommendation(rec);
      } catch {
        // If no recommendation yet, ignore
      }

      try {
        const vals = await apiClient.listChannelValidations(sessionId);
        setChannelValidations(vals);
      } catch {
        // If no validations yet, ignore
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Gagal memuat data Channel Health");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, activeBand, setChannelHealthSnapshot, setLatestRecommendation, setChannelValidations]);

  useEffect(() => {
    fetchChannelHealth();
  }, [fetchChannelHealth]);

  const handleEvaluate = async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const rec = await apiClient.evaluateChannelRecommendation(sessionId, {
        band: activeBand,
        channel_width_mhz: 20,
        observation_window_sec: windowSec,
        regulatory_domain: regulatoryDomain,
      });
      setLatestRecommendation(rec);
      await fetchChannelHealth();
    } catch (err: any) {
      setErrorMsg(err.message || "Evaluasi gagal");
    } finally {
      setIsLoading(false);
    }
  };

  const handleTriggerValidation = async (markerId?: string, before?: number, after?: number) => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      const val = await apiClient.triggerChannelValidation(sessionId, {
        marker_id: markerId || null,
        before_window_sec: before || 60,
        after_window_sec: after || 60,
      });
      addChannelValidation(val);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col selection:bg-[var(--color-signal)] selection:text-zinc-950">
      <Header />

      <main className="flex-1 max-w-6xl w-full mx-auto p-4 sm:p-6 space-y-6">
        {/* Page Top Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-xl tracking-tight text-zinc-100">
                Channel Health & Recommendation Engine
              </h1>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)] font-semibold">
                v1.2 Read-Only
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-0.5">
              Analisis matematis tumpang tindih spektral, bobot daya linear (mW), mitigasi interferensi, dan validasi sebelum/sesudah.
            </p>
          </div>

          {/* Controls: Band Toggle, Window, Regulatory */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Band Toggle */}
            <div className="flex items-center rounded-lg border border-white/10 bg-[var(--color-surface-raised)] p-0.5 text-xs font-mono">
              <button
                onClick={() => setActiveBand("2.4GHz")}
                className={`px-3 py-1 rounded-[var(--radius-control)] transition ${
                  activeBand === "2.4GHz"
                    ? "bg-[var(--color-signal)] text-zinc-950 font-bold"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                2.4 GHz
              </button>
              <button
                onClick={() => setActiveBand("5GHz")}
                className={`px-3 py-1 rounded-[var(--radius-control)] transition ${
                  activeBand === "5GHz"
                    ? "bg-[var(--color-signal)] text-zinc-950 font-bold"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                5 GHz
              </button>
            </div>

            {/* Window Selector */}
            <select
              value={windowSec}
              onChange={(e) => setWindowSec(Number(e.target.value))}
              className="h-8 rounded-[var(--radius-control)] border border-white/15 bg-zinc-900 px-2 text-xs font-mono text-zinc-200"
              title="Observation window"
            >
              <option value={60}>Window: 1 Menit (Snapshot)</option>
              <option value={120}>Window: 2 Menit</option>
              <option value={300}>Window: 5 Menit (Standar)</option>
              <option value={600}>Window: 10 Menit (Maksimal)</option>
            </select>

            {/* Regulatory Domain */}
            <select
              value={regulatoryDomain}
              onChange={(e) => setRegulatoryDomain(e.target.value)}
              className="h-8 rounded-[var(--radius-control)] border border-white/15 bg-zinc-900 px-2 text-xs font-mono text-zinc-200"
              title="Regulatory domain"
            >
              <option value="ID">Regulasi: ID (SDPPI)</option>
              <option value="US">Regulasi: US (FCC)</option>
              <option value="EU">Regulasi: EU (ETSI)</option>
            </select>

            <button
              onClick={handleEvaluate}
              disabled={isLoading || !sessionId}
              className="inline-flex min-h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-[var(--radius-control)] bg-[var(--color-signal)] px-3 text-xs font-semibold text-zinc-950 transition-transform active:scale-[0.98] disabled:opacity-50"
            >
              <ArrowsClockwise size={13} className={isLoading ? "animate-spin" : ""} />
              Evaluasi
            </button>
          </div>
        </div>

        {/* Error notice if any */}
        {errorMsg && (
          <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-950/20 text-xs text-rose-300">
            {errorMsg}
          </div>
        )}

        {!sessionId ? (
          <div className="p-12 rounded-[var(--radius-panel)] border border-dashed border-white/10 text-center space-y-3 bg-[var(--color-surface)]">
            <Broadcast size={36} className="text-zinc-500 mx-auto" />
            <h3 className="text-base font-semibold text-zinc-200">Belum Ada Sesi Pemindaian Aktif</h3>
            <p className="text-xs text-zinc-400 max-w-md mx-auto">
              Silakan buat atau aktifkan sesi Live Scan di halaman utama untuk mulai mengumpulkan data telemetri kanal WiFi.
            </p>
            <Link
              href="/"
              className="inline-flex min-h-9 items-center justify-center rounded-[var(--radius-control)] bg-[var(--color-signal)] px-4 text-xs font-semibold text-zinc-950"
            >
              Buka Live Scan
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 1. Recommendation Card */}
            <ChannelRecommendationCard
              recommendation={latestRecommendation}
              onEvaluate={handleEvaluate}
              isLoading={isLoading}
            />

            {/* 2. Channel Health Matrix */}
            <ChannelHealthMatrix snapshot={channelHealthSnapshot} />

            {/* 3. Before-After Comparison */}
            <ChannelComparison
              validations={channelValidations}
              onTriggerValidation={handleTriggerValidation}
              isLoading={isLoading}
            />
          </div>
        )}
      </main>

      {/* Slide-over Evidence Drawer */}
      <ChannelEvidenceDrawer />
    </div>
  );
}
