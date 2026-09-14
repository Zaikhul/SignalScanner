"use client";

import React, { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { Table, Eye, Info, Question } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { ChannelHealthItem, ChannelHealthSnapshot } from "@/lib/types";

interface Props {
  snapshot?: ChannelHealthSnapshot | null;
  onSelectChannel?: (item: ChannelHealthItem) => void;
}

export function ChannelHealthMatrix({ snapshot: propSnapshot, onSelectChannel }: Props) {
  const { channelHealthSnapshot, setSelectedEvidenceChannel, setEvidenceDrawerOpen } = useScannerStore();
  const snapshot = propSnapshot || channelHealthSnapshot;
  const [showTable, setShowTable] = useState(false);

  const handleChannelClick = (item: ChannelHealthItem) => {
    setSelectedEvidenceChannel(item);
    setEvidenceDrawerOpen(true);
    if (onSelectChannel) {
      onSelectChannel(item);
    }
  };

  const chartOption = useMemo(() => {
    if (!snapshot || !snapshot.channels || snapshot.channels.length === 0) {
      return null;
    }

    const sortedChannels = [...snapshot.channels].sort((a, b) => a.channel - b.channel);
    const channelLabels = sortedChannels.map((c) => `Kanal ${c.channel}`);
    const healthScores = sortedChannels.map((c) => c.health_score);

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "#171b1d",
        borderColor: "#2a3033",
        textStyle: { color: "#f2f4ef", fontSize: 11 },
        formatter: (params: any) => {
          const idx = params[0]?.dataIndex;
          const ch = sortedChannels[idx];
          if (!ch) return "";

          const cciMilli = (ch.cci_power_mw * 1000).toFixed(4);
          const aciMilli = (ch.aci_power_mw * 1000).toFixed(4);
          const overlapVal = ch.components.overlap_interference.value ?? "N/A";
          const utilVal = ch.components.utilization.value !== null ? `${(Number(ch.components.utilization.value) * 100).toFixed(1)}%` : "Unavailable";

          return `
            <div style="font-family: var(--font-geist-sans); min-width: 180px;">
              <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #2a3033; padding-bottom: 4px; margin-bottom: 4px;">
                <b style="color: #a8d94f;">Kanal ${ch.channel} (${ch.band})</b>
                <span style="font-weight: 600;">Skor: ${ch.health_score}/100</span>
              </div>
              <div style="font-size: 10px; color: #9aa3a0; margin-bottom: 4px;">
                Interpretasi: <b>${ch.health_label}</b> ${ch.is_dfs ? "(DFS)" : ""}
              </div>
              <div style="display: grid; grid-template-columns: 1fr auto; gap: 4px; font-size: 10px;">
                <span>Kepadatan AP:</span> <b>${ch.ap_count} AP</b>
                <span>Overlap Penalty:</span> <b>${overlapVal}</b>
                <span>CCI Power:</span> <b>${cciMilli} µW</b>
                <span>ACI Power:</span> <b>${aciMilli} µW</b>
                <span>Utilisasi Radio:</span> <b>${utilVal}</b>
                <span>Max RSSI:</span> <b>${ch.ap_count > 0 ? ch.max_rssi + " dBm" : "N/A"}</b>
              </div>
              ${ch.exclusion_reasons.length > 0 ? `
                <div style="margin-top: 6px; padding-top: 4px; border-top: 1px dashed #404040; font-size: 9px; color: #fbbf24;">
                  Catatan regulasi: ${ch.exclusion_reasons.join(", ")}
                </div>
              ` : ""}
              <div style="margin-top: 6px; font-size: 9px; color: #71717a;">
                *Klik bar untuk membuka rincian evidence kanal ini
              </div>
            </div>
          `;
        },
      },
      grid: {
        top: 24,
        left: 40,
        right: 20,
        bottom: 30,
      },
      xAxis: {
        type: "category",
        data: channelLabels,
        axisLine: { lineStyle: { color: "#2a3033" } },
        axisLabel: {
          color: "#9aa3a0",
          fontSize: 10,
          fontFamily: "var(--font-geist-mono)",
          interval: 0,
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLine: { lineStyle: { color: "#2a3033" } },
        splitLine: { lineStyle: { color: "#1c2124" } },
        axisLabel: { color: "#9aa3a0", fontSize: 10, fontFamily: "var(--font-geist-mono)" },
      },
      series: [
        {
          name: "Health Score",
          type: "bar",
          data: healthScores,
          itemStyle: {
            color: (params: any) => {
              const ch = sortedChannels[params.dataIndex];
              if (!ch.is_candidate) return "#3f3f46"; // Excluded (zinc-700)
              const score = params.value;
              if (score >= 80) return "#a8d94f"; // Sehat (Signal Lime)
              if (score >= 60) return "#34d399"; // Layak (Emerald)
              if (score >= 40) return "#fbbf24"; // Padat (Amber)
              return "#f87171"; // Buruk (Rose)
            },
            borderRadius: [4, 4, 0, 0],
          },
          label: {
            show: true,
            position: "top",
            color: "#9aa3a0",
            fontSize: 9,
            fontFamily: "var(--font-geist-mono)",
            formatter: "{c}",
          },
        },
      ],
    };
  }, [snapshot]);

  if (!snapshot || !snapshot.channels || snapshot.channels.length === 0) {
    return (
      <div className="p-6 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] text-center">
        <p className="text-xs text-zinc-400">Belum ada data Channel Health Matrix untuk sesi ini.</p>
      </div>
    );
  }

  const sortedChannels = [...snapshot.channels].sort((a, b) => a.channel - b.channel);

  return (
    <div className="p-4 sm:p-5 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] space-y-3">
      {/* Matrix Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="font-semibold text-sm text-zinc-100">Channel Health Matrix</h4>
            <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-zinc-400">
              Skala Relatif 0-100
            </span>
          </div>
          <span className="text-[11px] text-zinc-400">
            Perbandingan komposit seluruh kanal band {snapshot.band} pada observation window ini
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowTable(!showTable)}
            className="inline-flex min-h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-[var(--radius-control)] border border-white/15 bg-transparent px-2.5 text-xs text-zinc-300 hover:bg-white/5 transition active:scale-[0.98]"
            title="Toggle tampilan alternatif tabel aksesibel (WCAG 2.2 AA)"
          >
            <Table size={14} />
            {showTable ? "Lihat Grafik" : "Tabel Aksesibel"}
          </button>
        </div>
      </div>

      {/* Main Visualization or Accessible Table */}
      {showTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse font-mono">
            <thead>
              <tr className="border-b border-white/10 text-zinc-400 bg-white/[0.02]">
                <th className="py-2 px-2.5">Kanal</th>
                <th className="py-2 px-2.5">Skor</th>
                <th className="py-2 px-2.5">Kategori</th>
                <th className="py-2 px-2.5">AP</th>
                <th className="py-2 px-2.5">Max RSSI</th>
                <th className="py-2 px-2.5">Overlap</th>
                <th className="py-2 px-2.5">CCI (µW)</th>
                <th className="py-2 px-2.5">ACI (µW)</th>
                <th className="py-2 px-2.5">Status</th>
                <th className="py-2 px-2.5 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-zinc-300">
              {sortedChannels.map((ch) => (
                <tr
                  key={ch.channel}
                  className="hover:bg-white/5 transition cursor-pointer"
                  onClick={() => handleChannelClick(ch)}
                >
                  <td className="py-2 px-2.5 font-bold text-zinc-100">
                    Kanal {ch.channel}
                    {ch.is_dfs && <span className="ml-1 text-[9px] text-blue-400 font-normal">(DFS)</span>}
                  </td>
                  <td className="py-2 px-2.5 font-bold">
                    <span
                      className={
                        ch.health_score >= 80
                          ? "text-[var(--color-signal)]"
                          : ch.health_score >= 60
                          ? "text-emerald-400"
                          : ch.health_score >= 40
                          ? "text-amber-400"
                          : "text-rose-400"
                      }
                    >
                      {ch.health_score}
                    </span>
                  </td>
                  <td className="py-2 px-2.5">{ch.health_label}</td>
                  <td className="py-2 px-2.5">{ch.ap_count}</td>
                  <td className="py-2 px-2.5">{ch.ap_count > 0 ? `${ch.max_rssi} dBm` : "N/A"}</td>
                  <td className="py-2 px-2.5">{ch.components.overlap_interference.value ?? "N/A"}</td>
                  <td className="py-2 px-2.5">{(ch.cci_power_mw * 1000).toFixed(4)}</td>
                  <td className="py-2 px-2.5">{(ch.aci_power_mw * 1000).toFixed(4)}</td>
                  <td className="py-2 px-2.5">
                    {ch.is_candidate ? (
                      <span className="text-emerald-400">Kandidat</span>
                    ) : (
                      <span className="text-zinc-500">
                        {ch.exclusion_reasons[0] || "Non-kandidat"}
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-2.5 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleChannelClick(ch);
                      }}
                      className="text-xs text-[var(--color-signal)] hover:underline"
                    >
                      Bukti
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div>
          {chartOption && (
            <ReactECharts
              option={chartOption}
              style={{ height: "240px", width: "100%" }}
              onEvents={{
                click: (params: any) => {
                  const ch = sortedChannels[params.dataIndex];
                  if (ch) handleChannelClick(ch);
                },
              }}
            />
          )}

          {/* Matrix Legend */}
          <div className="flex flex-wrap items-center justify-between text-[11px] text-zinc-400 pt-2 border-t border-white/5">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-[var(--color-signal)]" />
                Sehat (80-100)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-emerald-400" />
                Layak (60-79)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-amber-400" />
                Padat (40-59)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-rose-400" />
                Buruk (0-39)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-zinc-700" />
                Non-kandidat regulasi
              </span>
            </div>
            <span className="font-mono text-[10px] text-zinc-500">
              *Klik bar kanal manapun untuk meninjau evidence drawer
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
