"use client";

import React from "react";
import { X, Info, ShieldCheck, Cpu, Broadcast, Clock, Warning } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { MethodBadge } from "@/components/ui/MethodBadge";
import { ComponentProvenance } from "@/lib/types";

export function ChannelEvidenceDrawer() {
  const {
    evidenceDrawerOpen,
    setEvidenceDrawerOpen,
    selectedEvidenceChannel,
    channelHealthSnapshot,
    latestRecommendation,
    targets,
  } = useScannerStore();

  if (!evidenceDrawerOpen || !selectedEvidenceChannel) {
    return null;
  }

  const ch = selectedEvidenceChannel;
  const snapshot = channelHealthSnapshot;
  const rec = latestRecommendation;

  // Find all contributing APs for this channel (same channel or overlapping bandwidth)
  const contributingTargets = targets
    .filter((t) => t.channel !== undefined)
    .map((t) => {
      const tCh = t.channel!;
      const tWidth = (t.extra?.channel_width_mhz || t.extra?.channel_width || 20) as number;
      const tRssi = t.latest_signal;
      const pMw = 10.0 ** (tRssi / 10.0);

      // Distance in center freq
      let overlap = 0.0;
      if (ch.band === "2.4GHz") {
        const deltaCh = Math.abs(ch.channel - tCh);
        if (deltaCh === 0) overlap = 1.0;
        else if (deltaCh === 1) overlap = 0.75;
        else if (deltaCh === 2) overlap = 0.50;
        else if (deltaCh === 3) overlap = 0.25;
        else if (deltaCh === 4) overlap = 0.10;
        else overlap = 0.0;
      } else {
        overlap = tCh === ch.channel ? 1.0 : 0.0;
      }

      const isCci = overlap === 1.0;
      const contribMw = pMw * overlap;

      return {
        targetId: t.target_id,
        displayName: t.display_name || "Hidden SSID",
        channel: tCh,
        width: tWidth,
        rssi: tRssi,
        powerMw: pMw,
        overlapRatio: overlap,
        contribMw,
        isCci,
      };
    })
    .filter((t) => t.overlapRatio > 0.0)
    .sort((a, b) => b.contribMw - a.contribMw);

  const renderProvenanceTag = (prov: ComponentProvenance) => {
    switch (prov) {
      case "measured":
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950/60 border border-emerald-500/30 text-emerald-300">
            MEASURED
          </span>
        );
      case "derived":
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-blue-950/60 border border-blue-500/30 text-blue-300">
            DERIVED
          </span>
        );
      case "configured":
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-purple-950/60 border border-purple-500/30 text-purple-300">
            CONFIGURED
          </span>
        );
      case "inferred":
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-950/60 border border-amber-500/30 text-amber-300">
            INFERRED
          </span>
        );
      default:
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-zinc-800 border border-zinc-700 text-zinc-400">
            UNAVAILABLE
          </span>
        );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="w-full max-w-xl bg-zinc-950 border-l border-white/10 h-full flex flex-col shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
      >
        {/* Drawer Header */}
        <div className="p-4 border-b border-white/10 flex items-center justify-between bg-[var(--color-surface)]">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)]">
              <Cpu size={18} weight="bold" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 id="evidence-drawer-title" className="font-semibold text-sm text-zinc-100">
                  Evidence Trail &mdash; Kanal {ch.channel}
                </h3>
                <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-zinc-400">
                  {ch.band} ({ch.width_mhz} MHz)
                </span>
              </div>
              <span className="text-[11px] text-zinc-400 block">
                Skor: {ch.health_score}/100 ({ch.health_label}) &bull; Algoritma: {rec?.algorithm_version || "channel-health-1.0.0"}
              </span>
            </div>
          </div>

          <button
            onClick={() => setEvidenceDrawerOpen(false)}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-white/10 transition"
            aria-label="Tutup evidence drawer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Drawer Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs text-zinc-300">
          {/* Metadata banner */}
          <div className="p-3 rounded-lg border border-white/5 bg-white/[0.02] space-y-1 font-mono text-[11px]">
            <div className="flex justify-between">
              <span className="text-zinc-500">Input Snapshot ID:</span>
              <span className="text-zinc-200">{snapshot?.snapshot_id || "N/A"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Regulatory Domain:</span>
              <span className="text-zinc-200">
                {snapshot?.regulatory_domain.value || "ID"} ({snapshot?.regulatory_domain.provenance})
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Observation Window:</span>
              <span className="text-zinc-200">
                {Math.round(snapshot?.observation_window.duration_seconds || 300)} detik ({snapshot?.observation_window.scan_cycles || 0} siklus)
              </span>
            </div>
          </div>

          {/* 5 Penalty Components Decomposition */}
          <div className="space-y-2">
            <h4 className="font-semibold text-xs font-mono uppercase text-zinc-200 tracking-wider flex items-center gap-1.5">
              <Info size={14} className="text-[var(--color-signal)]" />
              Dekomposisi 5 Komponen Penalti
            </h4>
            <div className="divide-y divide-white/5 border border-white/10 rounded-lg overflow-hidden bg-[var(--color-surface)]">
              {/* Utilization */}
              <div className="p-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-zinc-200">Channel Utilization (Bobot: 30%)</div>
                  <div className="text-[11px] text-zinc-500">Airtime busy radio atau kanal terisi</div>
                </div>
                <div className="flex items-center gap-2">
                  {renderProvenanceTag(ch.components.utilization.provenance)}
                  <span className="font-mono text-zinc-100 font-semibold">
                    {ch.components.utilization.value !== null
                      ? `${(Number(ch.components.utilization.value) * 100).toFixed(1)}%`
                      : "Unavailable"}
                  </span>
                </div>
              </div>

              {/* Overlap Interference */}
              <div className="p-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-zinc-200">Overlap-Weighted Interference (Bobot: 30%)</div>
                  <div className="text-[11px] text-zinc-500">
                    Agregasi daya linear (mW) AP tetangga terbobot spektrum
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {renderProvenanceTag(ch.components.overlap_interference.provenance)}
                  <span className="font-mono text-zinc-100 font-semibold">
                    {ch.components.overlap_interference.value ?? 0.0} (Ratio)
                  </span>
                </div>
              </div>

              {/* Retry */}
              <div className="p-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-zinc-200">Retry, Error & Drop Rate (Bobot: 20%)</div>
                  <div className="text-[11px] text-zinc-500">Tingkat kegagalan transmisi frame</div>
                </div>
                <div className="flex items-center gap-2">
                  {renderProvenanceTag(ch.components.retry.provenance)}
                  <span className="font-mono text-zinc-100 font-semibold">
                    {ch.components.retry.value !== null ? `${ch.components.retry.value}` : "Unavailable"}
                  </span>
                </div>
              </div>

              {/* Noise */}
              <div className="p-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-zinc-200">Noise Floor / Non-WiFi (Bobot: 10%)</div>
                  <div className="text-[11px] text-zinc-500">Energi noise latar belakang</div>
                </div>
                <div className="flex items-center gap-2">
                  {renderProvenanceTag(ch.components.noise.provenance)}
                  <span className="font-mono text-zinc-100 font-semibold">
                    {ch.components.noise.value !== null ? `${ch.components.noise.value} dBm` : "Unavailable"}
                  </span>
                </div>
              </div>

              {/* Temporal Instability */}
              <div className="p-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-zinc-200">Temporal Instability (Bobot: 10%)</div>
                  <div className="text-[11px] text-zinc-500">Fluktuasi deviasi standar RSSI target</div>
                </div>
                <div className="flex items-center gap-2">
                  {renderProvenanceTag(ch.components.temporal_instability.provenance)}
                  <span className="font-mono text-zinc-100 font-semibold">
                    {ch.components.temporal_instability.value ?? 0.1}
                  </span>
                </div>
              </div>
            </div>
            <p className="text-[10px] text-zinc-500 italic">
              *Komponen bertatus UNAVAILABLE tidak diisi nol. Bobot komponen yang tersedia dinormalisasi ulang (weight renormalization) dan confidence diturunkan.
            </p>
          </div>

          {/* Co-Channel vs Adjacent-Channel Summary */}
          <div className="grid grid-cols-2 gap-3 font-mono">
            <div className="p-3 rounded-lg border border-white/10 bg-[var(--color-surface)]">
              <span className="text-[10px] uppercase text-zinc-500 block">CCI Power (Co-Channel)</span>
              <span className="text-base font-bold text-zinc-100">
                {(ch.cci_power_mw * 1000).toFixed(4)} µW
              </span>
              <span className="text-[10px] text-zinc-400 block mt-0.5">
                Kanal sama ({ch.ap_count} AP)
              </span>
            </div>
            <div className="p-3 rounded-lg border border-white/10 bg-[var(--color-surface)]">
              <span className="text-[10px] uppercase text-zinc-500 block">ACI Power (Adjacent-Channel)</span>
              <span className="text-base font-bold text-zinc-100">
                {(ch.aci_power_mw * 1000).toFixed(4)} µW
              </span>
              <span className="text-[10px] text-zinc-400 block mt-0.5">
                Tumpang tindih spektrum kanal tetangga
              </span>
            </div>
          </div>

          {/* Contributing APs Table (mW Domain) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="font-semibold text-xs font-mono uppercase text-zinc-200 tracking-wider">
                Daftar AP Pengkontribusi Interferensi ({contributingTargets.length})
              </h4>
              <span className="text-[10px] font-mono text-zinc-500">Daya linear: P = 10^(RSSI/10)</span>
            </div>

            {contributingTargets.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-white/10 text-center text-zinc-500 text-xs">
                Tidak ada AP tetangga yang tumpang tindih spektrum dengan kanal ini.
              </div>
            ) : (
              <div className="border border-white/10 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead>
                    <tr className="border-b border-white/10 text-zinc-400 bg-white/[0.02]">
                      <th className="py-2 px-2.5">SSID / BSSID Hash</th>
                      <th className="py-2 px-2.5">Kanal</th>
                      <th className="py-2 px-2.5">RSSI</th>
                      <th className="py-2 px-2.5">Overlap</th>
                      <th className="py-2 px-2.5">Tipe</th>
                      <th className="py-2 px-2.5 text-right">Daya (µW)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-zinc-300">
                    {contributingTargets.map((t, idx) => (
                      <tr key={idx} className="hover:bg-white/5">
                        <td className="py-2 px-2.5">
                          <div className="font-semibold text-zinc-100 truncate max-w-[120px]">
                            {t.displayName}
                          </div>
                          <div className="text-[10px] text-zinc-500 truncate max-w-[120px]">
                            {t.targetId}
                          </div>
                        </td>
                        <td className="py-2 px-2.5">Ch {t.channel}</td>
                        <td className="py-2 px-2.5">{t.rssi} dBm</td>
                        <td className="py-2 px-2.5">{(t.overlapRatio * 100).toFixed(0)}%</td>
                        <td className="py-2 px-2.5">
                          {t.isCci ? (
                            <span className="text-amber-400">CCI</span>
                          ) : (
                            <span className="text-blue-400">ACI</span>
                          )}
                        </td>
                        <td className="py-2 px-2.5 text-right text-zinc-100 font-bold">
                          {(t.contribMw * 1000).toFixed(4)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Drawer Footer */}
        <div className="p-4 border-t border-white/10 bg-[var(--color-surface)] flex items-center justify-between">
          <span className="text-[11px] text-zinc-500 font-mono">
            Sistem Pemindai Area v1.2 &bull; Read-Only Engine
          </span>
          <button
            onClick={() => setEvidenceDrawerOpen(false)}
            className="inline-flex min-h-8 items-center justify-center rounded-[var(--radius-control)] border border-white/15 px-3 text-xs text-zinc-200 hover:bg-white/5"
          >
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}
