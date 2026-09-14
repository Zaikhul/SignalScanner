"use client";

import React, { useState } from "react";
import {
  Sparkle,
  CheckCircle,
  WarningCircle,
  Info,
  ArrowsClockwise,
  ChartBar,
  ShieldCheck,
  ShieldWarning,
  Sliders,
} from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { ChannelRecommendation } from "@/lib/types";

interface Props {
  recommendation?: ChannelRecommendation | null;
  onEvaluate?: () => Promise<void>;
  isLoading?: boolean;
}

export function ChannelRecommendationCard({
  recommendation: propRec,
  onEvaluate,
  isLoading = false,
}: Props) {
  const {
    latestRecommendation,
    setEvidenceDrawerOpen,
    setSelectedEvidenceChannel,
    channelHealthSnapshot,
    setValidationModalOpen,
  } = useScannerStore();

  const rec = propRec || latestRecommendation;

  const handleOpenEvidence = (channelNum: number) => {
    if (channelHealthSnapshot) {
      const found = channelHealthSnapshot.channels.find((c) => c.channel === channelNum);
      if (found) {
        setSelectedEvidenceChannel(found);
      }
    }
    setEvidenceDrawerOpen(true);
  };

  if (!rec) {
    return (
      <div className="p-5 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Sparkle size={18} weight="bold" className="text-[var(--color-signal)]" />
              <h3 className="font-semibold text-sm text-zinc-100">Recommendation Engine (v1.2)</h3>
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-zinc-400">
                Read-Only
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-1">
              Evaluasi kesehatan kanal belum dijalankan untuk sesi ini. Jalankan evaluasi snapshot untuk melihat rekomendasi objektif.
            </p>
          </div>
          {onEvaluate && (
            <button
              onClick={onEvaluate}
              disabled={isLoading}
              className="inline-flex min-h-9 items-center justify-center gap-1.5 whitespace-nowrap rounded-[var(--radius-control)] bg-[var(--color-signal)] px-3.5 text-xs font-semibold text-zinc-950 transition-transform active:scale-[0.98] disabled:opacity-50"
            >
              <ArrowsClockwise size={14} className={isLoading ? "animate-spin" : ""} />
              {isLoading ? "Mengevaluasi..." : "Evaluasi Snapshot"}
            </button>
          )}
        </div>
      </div>
    );
  }

  const { primary, alternatives, confidence, confidence_reasons, supporting_factors, counter_signals, missing_evidence, conflict_detected, freshness_status } = rec;

  const getConfidenceBadge = (level: string) => {
    switch (level.toLowerCase()) {
      case "high":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-emerald-950/60 border border-emerald-500/40 text-emerald-300">
            <ShieldCheck size={13} weight="bold" />
            Confidence: High
          </span>
        );
      case "medium":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-amber-950/60 border border-amber-500/40 text-amber-300">
            <Info size={13} weight="bold" />
            Confidence: Medium
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-rose-950/60 border border-rose-500/40 text-rose-300">
            <ShieldWarning size={13} weight="bold" />
            Confidence: Low
          </span>
        );
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-[var(--color-signal)]";
    if (score >= 60) return "text-emerald-400";
    if (score >= 40) return "text-amber-400";
    return "text-rose-400";
  };

  return (
    <div className="p-5 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-4">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)]">
            <Sparkle size={16} weight="bold" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sm text-zinc-100">Rekomendasi Kanal WiFi</h3>
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.2 rounded bg-white/5 border border-white/10 text-zinc-400">
                {rec.band} ({rec.channel_width_mhz} MHz)
              </span>
              {freshness_status === "stale" && (
                <span className="text-[10px] font-mono uppercase px-1.5 py-0.2 rounded bg-amber-950/60 border border-amber-500/30 text-amber-300">
                  Data Stale
                </span>
              )}
            </div>
            <span className="text-[11px] text-zinc-400 block">
              Snapshot: {rec.input_snapshot_id} (Algoritma: {rec.algorithm_version})
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {getConfidenceBadge(confidence)}
          {onEvaluate && (
            <button
              onClick={onEvaluate}
              disabled={isLoading}
              className="inline-flex min-h-8 items-center justify-center gap-1 whitespace-nowrap rounded-[var(--radius-control)] border border-white/15 bg-transparent px-2.5 text-xs text-zinc-200 hover:bg-white/5 active:scale-[0.98] disabled:opacity-50"
              title="Evaluasi ulang snapshot observasi terkini"
            >
              <ArrowsClockwise size={13} className={isLoading ? "animate-spin" : ""} />
              Evaluasi Ulang
            </button>
          )}
        </div>
      </div>

      {/* Conflict Notice if tie margin */}
      {conflict_detected && (
        <div className="p-2.5 rounded-lg border border-amber-500/30 bg-amber-950/20 text-xs text-amber-200 flex items-center gap-2">
          <WarningCircle size={16} className="text-amber-400 shrink-0" weight="fill" />
          <span>
            <b>Selisih Skor Tipis (&le; 2 poin):</b> Terdeteksi persaingan ketat antara kanal utama dan alternatif. Disarankan menjalankan perbandingan A/B sebelum menetapkan keputusan.
          </span>
        </div>
      )}

      {/* Primary & Alternatives Grid */}
      <div className="grid grid-cols-1 md:grid-cols-[1.3fr_1fr] gap-4">
        {/* Primary Winner Card */}
        <div className="p-4 rounded-xl border border-[var(--color-signal)]/30 bg-[var(--color-surface-raised)]/70 relative overflow-hidden flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400">
                {primary.cta_label}
              </span>
              <div className="flex items-baseline gap-2 mt-0.5">
                <span className="font-mono text-3xl font-bold tracking-tight text-zinc-100">
                  Kanal {primary.channel}
                </span>
                {primary.is_dfs && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-950/60 border border-blue-500/30 text-blue-300">
                    DFS
                  </span>
                )}
              </div>
            </div>

            <div className="text-right">
              <span className="text-[10px] font-mono uppercase text-zinc-400 block">Health Score</span>
              <div className="flex items-baseline justify-end gap-1">
                <span className={`font-mono text-3xl font-bold ${getScoreColor(primary.score)}`}>
                  {primary.score}
                </span>
                <span className="text-xs text-zinc-400 font-mono">/100</span>
              </div>
              <span className="text-xs font-medium text-zinc-300">
                {primary.health_label}
              </span>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between">
            <span className="text-[11px] text-zinc-400">
              Kandidat relatif terbaik pada observation window ini
            </span>
            <button
              onClick={() => handleOpenEvidence(primary.channel)}
              className="text-xs text-[var(--color-signal)] hover:underline font-medium flex items-center gap-1"
            >
              Lihat Bukti (Evidence) &rarr;
            </button>
          </div>
        </div>

        {/* Alternatives Card */}
        <div className="p-4 rounded-xl border border-white/10 bg-[var(--color-surface-raised)]/40 flex flex-col justify-between">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-400 block mb-2">
              Kandidat Alternatif
            </span>
            {alternatives.length === 0 ? (
              <p className="text-xs text-zinc-400 italic">Tidak ada kandidat alternatif yang memenuhi syarat regulasi.</p>
            ) : (
              <div className="space-y-2">
                {alternatives.map((alt) => (
                  <div
                    key={alt.channel}
                    className="flex items-center justify-between p-2 rounded-lg bg-white/5 border border-white/5 text-xs hover:border-white/10 transition"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-zinc-100">Kanal {alt.channel}</span>
                      {alt.is_dfs && (
                        <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-blue-950/60 border border-blue-500/30 text-blue-300">
                          DFS
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`font-mono font-medium ${getScoreColor(alt.score)}`}>
                        {alt.score}/100 ({alt.health_label})
                      </span>
                      <button
                        onClick={() => handleOpenEvidence(alt.channel)}
                        className="text-[11px] text-zinc-400 hover:text-zinc-200 underline"
                      >
                        Detail
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between">
            <span className="text-[10px] font-mono text-zinc-500">
              Durasi observasi: {Math.round(rec.observation_window.duration_seconds)}s ({rec.observation_window.scan_cycles} siklus)
            </span>
            <button
              onClick={() => setValidationModalOpen(true)}
              className="text-xs text-zinc-300 hover:text-zinc-100 font-medium flex items-center gap-1"
            >
              <Sliders size={13} />
              Validasi Sebelum/Sesudah
            </button>
          </div>
        </div>
      </div>

      {/* Supporting Factors & Counter Signals */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
        {/* Supporting Factors */}
        <div className="p-3 rounded-lg border border-white/5 bg-white/[0.02] space-y-1.5">
          <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
            <CheckCircle size={14} weight="bold" />
            Faktor Pendukung
          </span>
          <ul className="space-y-1 text-xs text-zinc-300">
            {supporting_factors.map((f, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="text-emerald-400 font-bold">&bull;</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Counter Signals & Missing Evidence */}
        <div className="p-3 rounded-lg border border-white/5 bg-white/[0.02] space-y-1.5">
          <span className="text-[11px] font-mono font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
            <WarningCircle size={14} weight="bold" />
            Counter-Signals & Keterbatasan
          </span>
          <ul className="space-y-1 text-xs text-zinc-300">
            {counter_signals.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="text-amber-400 font-bold">&bull;</span>
                <span>{c}</span>
              </li>
            ))}
            {missing_evidence.length > 0 && (
              <li className="text-[11px] text-zinc-400 mt-1 italic">
                Data belum diukur: {missing_evidence.join(", ")}
              </li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
