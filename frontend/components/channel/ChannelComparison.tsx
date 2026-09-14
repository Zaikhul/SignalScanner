"use client";

import React, { useState } from "react";
import { Sliders, CheckCircle, Warning, Clock, TrendUp, TrendDown, Minus } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { ChannelValidationRun } from "@/lib/types";

interface Props {
  validations?: ChannelValidationRun[];
  onTriggerValidation?: (markerId?: string, beforeSec?: number, afterSec?: number) => Promise<void>;
  isLoading?: boolean;
}

export function ChannelComparison({
  validations: propValidations,
  onTriggerValidation,
  isLoading = false,
}: Props) {
  const { channelValidations, activeSession, validationModalOpen, setValidationModalOpen } = useScannerStore();
  const runs = propValidations || channelValidations;

  const [selectedMarkerId, setSelectedMarkerId] = useState<string>("");
  const [beforeSec, setBeforeSec] = useState<number>(60);
  const [afterSec, setAfterSec] = useState<number>(60);

  const markers = activeSession?.markers || [];

  const handleRunValidation = async () => {
    if (onTriggerValidation) {
      await onTriggerValidation(selectedMarkerId || undefined, beforeSec, afterSec);
    }
  };

  return (
    <div className="p-5 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)]">
            <Sliders size={16} weight="bold" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-semibold text-sm text-zinc-100">Validasi Sebelum & Sesudah Perubahan Kanal</h4>
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.2 rounded bg-white/5 border border-white/10 text-zinc-400">
                Observasi Teramati
              </span>
            </div>
            <span className="text-[11px] text-zinc-400 block">
              Membandingkan metrik jendela sebelum dan sesudah marker perubahan kanal tanpa klaim kausal otomatis
            </span>
          </div>
        </div>

        {/* Trigger Controls */}
        <div className="flex items-center gap-2">
          {markers.length > 0 ? (
            <select
              value={selectedMarkerId}
              onChange={(e) => setSelectedMarkerId(e.target.value)}
              className="h-8 rounded-[var(--radius-control)] border border-white/15 bg-zinc-900 px-2 text-xs text-zinc-200"
            >
              <option value="">Pilih Marker Acuan...</option>
              {markers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} ({new Date(m.timestamp).toLocaleTimeString()})
                </option>
              ))}
            </select>
          ) : (
            <span className="text-xs text-zinc-500 font-mono italic">Belum ada marker sesi</span>
          )}

          <button
            onClick={handleRunValidation}
            disabled={isLoading || markers.length === 0}
            className="inline-flex min-h-8 items-center justify-center gap-1 whitespace-nowrap rounded-[var(--radius-control)] bg-[var(--color-signal)] px-3 text-xs font-semibold text-zinc-950 transition-transform active:scale-[0.98] disabled:opacity-50"
          >
            {isLoading ? "Menghitung..." : "Jalankan Validasi"}
          </button>
        </div>
      </div>

      {/* Validation Runs List */}
      {runs.length === 0 ? (
        <div className="p-6 rounded-lg border border-dashed border-white/10 text-center space-y-1">
          <p className="text-xs text-zinc-400">
            Belum ada data validasi perubahan kanal yang dijalankan untuk sesi ini.
          </p>
          <p className="text-[11px] text-zinc-500">
            Tambahkan marker pada timeline saat melakukan pergantian kanal AP, lalu jalankan validasi perbandingan di sini.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((r) => {
            const deltas = r.metric_deltas || {};
            return (
              <div
                key={r.validation_id}
                className="p-4 rounded-xl border border-white/10 bg-[var(--color-surface-raised)]/60 space-y-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-zinc-100">
                      Marker: {r.marker_label || "Titik Perubahan Kanal"}
                    </span>
                    <span className="text-[10px] font-mono text-zinc-400">
                      ID: {r.validation_id}
                    </span>
                  </div>
                  <span className="text-[11px] font-mono text-zinc-400">
                    {new Date(r.created_at).toLocaleTimeString()}
                  </span>
                </div>

                {/* Summary Label (Scientific phrasing) */}
                <div className="p-2.5 rounded-lg bg-white/5 border border-white/5 text-xs text-zinc-200 font-mono flex items-center gap-2">
                  <CheckCircle size={15} className="text-[var(--color-signal)] shrink-0" weight="bold" />
                  <span>{r.summary_label}</span>
                </div>

                {/* Metric Deltas Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
                  {Object.entries(deltas).map(([metricKey, d]) => {
                    const deltaVal = d.delta ?? 0;
                    const isPositive = deltaVal > 0;
                    const isZero = deltaVal === 0;

                    return (
                      <div
                        key={metricKey}
                        className="p-2.5 rounded-lg border border-white/5 bg-black/20 flex items-center justify-between"
                      >
                        <div>
                          <span className="text-zinc-400 block capitalize text-[11px]">
                            {metricKey.replace(/_/g, " ")}
                          </span>
                          <span className="text-zinc-500 text-[10px]">
                            Sebelum: {d.before ?? "N/A"} &rarr; Sesudah: {d.after ?? "N/A"}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 font-bold">
                          {isZero ? (
                            <span className="text-zinc-400 flex items-center gap-0.5">
                              <Minus size={12} /> 0.0
                            </span>
                          ) : isPositive ? (
                            <span className="text-emerald-400 flex items-center gap-0.5">
                              <TrendUp size={14} weight="bold" /> +{deltaVal}
                            </span>
                          ) : (
                            <span className="text-rose-400 flex items-center gap-0.5">
                              <TrendDown size={14} weight="bold" /> {deltaVal}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="text-[10px] text-zinc-500 italic">
                  *Perbandingan mengacu pada observation window sebelum dan sesudah marker; tidak menyimpulkan korelasi kausal tanpa kontrol eksperimental.
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
