"use client";

import React, { useState } from "react";
import {
  ArrowsClockwise,
  DownloadSimple,
  Laptop,
  Broadcast,
  CheckCircle,
  WarningCircle,
  Question,
  Tag,
} from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";
import { LanHost } from "@/lib/types";

export function HostInventory() {
  const { activeAssociation, lanHosts } = useScannerStore();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  if (!activeAssociation || activeAssociation.state !== "connected") {
    return null;
  }

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await apiClient.refreshInventory(activeAssociation.id);
    } catch (e) {
      console.error("Refresh inventory failed", e);
    } finally {
      setTimeout(() => setIsRefreshing(false), 1000);
    }
  };

  const handleExport = async (format: "json" | "csv") => {
    setIsExporting(true);
    try {
      const res = await apiClient.exportInventory(activeAssociation.id, format);
      const blob = new Blob([res.content], {
        type: format === "csv" ? "text/csv;charset=utf-8;" : "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `lan_inventory_${activeAssociation.id}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Export failed", e);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="p-4 rounded-[var(--radius-panel)] bg-[var(--color-surface)] border border-white/10 space-y-3 animate-fade-in">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
        <div>
          <h3 className="text-xs font-semibold text-zinc-100 uppercase tracking-wider flex items-center gap-1.5">
            <Laptop size={15} className="text-[var(--color-signal)]" />
            Inventaris Host LAN ({lanHosts.length} Host Terdeteksi)
          </h3>
          <p className="text-[11px] text-zinc-400 mt-0.5">
            Host terjangkau pada subnet {activeAssociation.prefix || "attached"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="py-1 px-2.5 rounded-[var(--radius-control)] border border-white/10 hover:bg-white/5 text-zinc-300 text-xs flex items-center gap-1 transition disabled:opacity-50"
          >
            <ArrowsClockwise size={13} className={isRefreshing ? "animate-spin" : ""} />
            Pindai ulang host
          </button>

          <div className="flex items-center rounded-[var(--radius-control)] border border-white/10 overflow-hidden text-xs">
            <button
              type="button"
              onClick={() => handleExport("json")}
              disabled={isExporting || lanHosts.length === 0}
              className="py-1 px-2 hover:bg-white/10 text-zinc-300 transition flex items-center gap-1"
            >
              <DownloadSimple size={13} /> JSON
            </button>
            <div className="w-[1px] h-3 bg-white/10" />
            <button
              type="button"
              onClick={() => handleExport("csv")}
              disabled={isExporting || lanHosts.length === 0}
              className="py-1 px-2 hover:bg-white/10 text-zinc-300 transition flex items-center gap-1"
            >
              CSV
            </button>
          </div>
        </div>
      </div>

      {/* Host Table */}
      {lanHosts.length === 0 ? (
        <div className="p-6 text-center text-zinc-500 text-xs border border-dashed border-white/10 rounded-[var(--radius-control)]">
          <Question size={24} className="mx-auto mb-1.5 text-zinc-600" />
          <p className="font-medium text-zinc-400">Belum ada host lain yang terdeteksi</p>
          <p className="text-[11px] text-zinc-600 mt-1 max-w-sm mx-auto">
            Sebagian jaringan menerapkan pembatasan isolasi klien (client isolation). IP collector dan gateway tetap dicatat.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-white/10 text-[10px] text-zinc-500 uppercase tracking-wider">
                <th className="py-2 px-2 font-medium">Alamat IP</th>
                <th className="py-2 px-2 font-medium">Hostname</th>
                <th className="py-2 px-2 font-medium">Vendor OUI</th>
                <th className="py-2 px-2 font-medium">MAC (Hash)</th>
                <th className="py-2 px-2 font-medium">Jangkauan</th>
                <th className="py-2 px-2 font-medium text-right">RTT (ms)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-mono">
              {lanHosts.map((host, idx) => {
                const reachabilityConfig = {
                  up: {
                    label: "Hidup",
                    badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
                    icon: <CheckCircle size={11} weight="fill" />,
                  },
                  limited: {
                    label: "Terbatas",
                    badge: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
                    icon: <Question size={11} />,
                  },
                  down: {
                    label: "Tidak merespons",
                    badge: "bg-red-500/10 text-red-400 border-red-500/20",
                    icon: <WarningCircle size={11} weight="fill" />,
                  },
                }[host.reachability] || {
                  label: host.reachability,
                  badge: "bg-zinc-800 text-zinc-400 border-white/10",
                  icon: null,
                };

                return (
                  <tr
                    key={`${host.ip}_${idx}`}
                    className="hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="py-2 px-2 font-semibold text-zinc-100 flex items-center gap-1.5 tabular-nums">
                      {host.is_gateway ? (
                        <Broadcast size={13} className="text-amber-400" />
                      ) : host.is_self ? (
                        <Laptop size={13} className="text-[var(--color-signal)]" />
                      ) : null}
                      <span>{host.ip}</span>
                      {host.is_gateway && (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 font-sans">
                          Gateway
                        </span>
                      )}
                      {host.is_self && (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-[var(--color-signal)]/20 text-[var(--color-signal)] font-sans">
                          Self
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-zinc-300 font-sans text-xs truncate max-w-[140px]">
                      {host.hostname || "--"}
                    </td>
                    <td className="py-2 px-2 text-zinc-400 font-sans text-xs truncate max-w-[140px]">
                      {host.oui_vendor || "Unknown"}
                    </td>
                    <td className="py-2 px-2 text-[10px] text-zinc-500 truncate max-w-[100px]">
                      {host.mac_hash}
                    </td>
                    <td className="py-2 px-2">
                      <span
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-sans border ${reachabilityConfig.badge}`}
                      >
                        {reachabilityConfig.icon}
                        {reachabilityConfig.label}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-right tabular-nums text-zinc-400">
                      {host.rtt_ms !== null && host.rtt_ms !== undefined
                        ? `${host.rtt_ms.toFixed(1)}`
                        : "--"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
