"use client";

import React, { useState, useMemo } from "react";
import {
  ArrowsClockwise,
  DownloadSimple,
  Laptop,
  Broadcast,
  CheckCircle,
  WarningCircle,
  Question,
  Tag,
  ShieldCheck,
  MagnifyingGlass,
  CircleNotch,
  Globe,
  TerminalWindow,
  Printer,
  Cpu,
  X,
  Crosshair,
} from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";
import { LanHost, PortInfo } from "@/lib/types";

// Service category styling helper
function getPortBadgeStyle(port: number): {
  badge: string;
  dot: string;
  category: string;
} {
  if ([80, 443, 8080, 8443, 8000].includes(port)) {
    return {
      badge: "bg-sky-500/10 text-sky-400 border-sky-500/25 hover:bg-sky-500/20",
      dot: "bg-sky-400",
      category: "Web",
    };
  }
  if ([22, 23, 3389].includes(port)) {
    return {
      badge: "bg-purple-500/10 text-purple-400 border-purple-500/25 hover:bg-purple-500/20",
      dot: "bg-purple-400",
      category: "Remote",
    };
  }
  if ([53, 67, 68, 123, 5353].includes(port)) {
    return {
      badge: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25 hover:bg-emerald-500/20",
      dot: "bg-emerald-400",
      category: "Network",
    };
  }
  if ([445, 139, 631, 9100].includes(port)) {
    return {
      badge: "bg-amber-500/10 text-amber-400 border-amber-500/25 hover:bg-amber-500/20",
      dot: "bg-amber-400",
      category: "Sharing/Print",
    };
  }
  if ([1883, 8883, 5000].includes(port)) {
    return {
      badge: "bg-rose-500/10 text-rose-400 border-rose-500/25 hover:bg-rose-500/20",
      dot: "bg-rose-400",
      category: "IoT",
    };
  }
  return {
    badge: "bg-zinc-800 text-zinc-300 border-white/10 hover:bg-zinc-700",
    dot: "bg-zinc-400",
    category: "Service",
  };
}

export function HostInventory() {
  const { activeAssociation, lanHosts, upsertLanHost } = useScannerStore();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [scanningIp, setScanningIp] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [selectedHost, setSelectedHost] = useState<LanHost | null>(null);

  // Summary statistics
  const stats = useMemo(() => {
    let totalOpenPorts = 0;
    let hostsWithPorts = 0;
    for (const h of lanHosts) {
      const portCount = h.open_ports?.length || 0;
      if (portCount > 0) {
        hostsWithPorts += 1;
        totalOpenPorts += portCount;
      }
    }
    return {
      totalHosts: lanHosts.length,
      hostsWithPorts,
      totalOpenPorts,
    };
  }, [lanHosts]);

  // Filtered hosts
  const filteredHosts = useMemo(() => {
    if (!searchQuery.trim()) return lanHosts;
    const q = searchQuery.toLowerCase().trim();
    return lanHosts.filter((h) => {
      const matchIp = h.ip.toLowerCase().includes(q);
      const matchHostname = (h.hostname || "").toLowerCase().includes(q);
      const matchVendor = (h.oui_vendor || "").toLowerCase().includes(q);
      const matchPort = h.open_ports?.some(
        (p) =>
          p.port.toString().includes(q) ||
          p.service.toLowerCase().includes(q)
      );
      return matchIp || matchHostname || matchVendor || matchPort;
    });
  }, [lanHosts, searchQuery]);

  if (!activeAssociation || activeAssociation.state !== "connected") {
    return null;
  }

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setScanError(null);
    try {
      await apiClient.refreshInventory(activeAssociation.id);
    } catch (e: any) {
      console.error("Refresh inventory failed", e);
      setScanError(e.message || "Gagal menyegarkan inventaris host.");
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
    } catch (e: any) {
      console.error("Export failed", e);
      setScanError(e.message || "Gagal mengekspor data inventaris.");
    } finally {
      setIsExporting(false);
    }
  };

  const handleScanHost = async (hostIp: string) => {
    setScanningIp(hostIp);
    setScanError(null);
    try {
      const updatedHost = await apiClient.scanHostPorts(activeAssociation.id, hostIp);
      upsertLanHost(updatedHost);
      // Update modal host if open
      if (selectedHost && selectedHost.ip === hostIp) {
        setSelectedHost(updatedHost);
      }
    } catch (e: any) {
      console.error(`Port scan on ${hostIp} failed`, e);
      setScanError(e.message || `Gagal memindai port pada host ${hostIp}.`);
    } finally {
      setScanningIp(null);
    }
  };

  return (
    <div className="p-4 rounded-[var(--radius-panel)] bg-[var(--color-surface)] border border-white/10 space-y-3 animate-fade-in text-zinc-200">
      {/* Header & Main Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
        <div>
          <h3 className="text-xs font-semibold text-zinc-100 uppercase tracking-wider flex items-center gap-1.5">
            <Laptop size={15} className="text-[var(--color-signal)]" />
            Inventaris Host LAN & Port Terbuka
          </h3>
          <p className="text-[11px] text-zinc-400 mt-0.5">
            Subnet aktif: <span className="font-mono text-zinc-300 font-medium">{activeAssociation.prefix || "Terhubung"}</span>
            {activeAssociation.gateway && (
              <> • Gateway: <span className="font-mono text-zinc-300">{activeAssociation.gateway}</span></>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="py-1 px-2.5 rounded-[var(--radius-control)] border border-white/10 hover:bg-white/5 text-zinc-300 text-xs flex items-center gap-1 transition disabled:opacity-50"
            title="Pindai ulang penemuan tetangga LAN"
          >
            <ArrowsClockwise size={13} className={isRefreshing ? "animate-spin" : ""} />
            Pindai Host
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

      {/* Summary Metrics Bar & Search Filter */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 pt-1 pb-1">
        <div className="flex items-center gap-2 p-2 rounded bg-white/[0.03] border border-white/5">
          <Laptop size={18} className="text-zinc-400" />
          <div>
            <div className="text-[10px] text-zinc-400">Total Host</div>
            <div className="text-sm font-semibold text-zinc-100 font-mono">{stats.totalHosts}</div>
          </div>
        </div>

        <div className="flex items-center gap-2 p-2 rounded bg-white/[0.03] border border-white/5">
          <Crosshair size={18} className="text-sky-400" />
          <div>
            <div className="text-[10px] text-zinc-400">Host Berport Terbuka</div>
            <div className="text-sm font-semibold text-sky-300 font-mono">
              {stats.hostsWithPorts} <span className="text-[10px] text-zinc-500 font-sans">({stats.totalHosts ? Math.round((stats.hostsWithPorts / stats.totalHosts) * 100) : 0}%)</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 p-2 rounded bg-white/[0.03] border border-white/5">
          <ShieldCheck size={18} className="text-emerald-400" />
          <div>
            <div className="text-[10px] text-zinc-400">Layanan/Port Terdeteksi</div>
            <div className="text-sm font-semibold text-emerald-300 font-mono">{stats.totalOpenPorts}</div>
          </div>
        </div>

        {/* Search Input */}
        <div className="relative flex items-center">
          <MagnifyingGlass size={13} className="absolute left-2.5 text-zinc-500 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Cari IP, host, port..."
            className="w-full pl-8 pr-3 py-1.5 rounded-[var(--radius-control)] bg-black/30 border border-white/10 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-[var(--color-signal)]/60 transition"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2 text-zinc-500 hover:text-zinc-300"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Safety Notice Banner */}
      <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded bg-emerald-500/[0.06] border border-emerald-500/20 text-[11px] text-emerald-300">
        <div className="flex items-center gap-1.5">
          <ShieldCheck size={14} className="text-emerald-400 shrink-0" />
          <span>
            <strong>Pemindaian Port Terkendali:</strong> Dibatasi pada target LAN subnet aktif ({activeAssociation.prefix}). Menggunakan connect probing non-blokir dengan batasan konkurensi aman.
          </span>
        </div>
      </div>

      {/* Error alert if any */}
      {scanError && (
        <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
          <div className="flex items-center gap-1.5">
            <WarningCircle size={14} className="text-rose-400 shrink-0" />
            <span>{scanError}</span>
          </div>
          <button
            type="button"
            onClick={() => setScanError(null)}
            className="text-zinc-400 hover:text-zinc-200"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Host Table */}
      {lanHosts.length === 0 ? (
        <div className="p-6 text-center text-zinc-500 text-xs border border-dashed border-white/10 rounded-[var(--radius-control)]">
          <Question size={24} className="mx-auto mb-1.5 text-zinc-600" />
          <p className="font-medium text-zinc-400">Belum ada host lain yang terdeteksi</p>
          <p className="text-[11px] text-zinc-600 mt-1 max-w-sm mx-auto">
            Sebagian jaringan menerapkan pembatasan isolasi klien (client isolation). IP collector dan gateway tetap dicatat.
          </p>
        </div>
      ) : filteredHosts.length === 0 ? (
        <div className="p-6 text-center text-zinc-500 text-xs border border-dashed border-white/10 rounded-[var(--radius-control)]">
          <p className="font-medium text-zinc-400">Tidak ada host yang cocok dengan kriteria pencarian &quot;{searchQuery}&quot;</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-white/10 text-[10px] text-zinc-500 uppercase tracking-wider">
                <th className="py-2 px-2 font-medium">Alamat IP</th>
                <th className="py-2 px-2 font-medium">Hostname</th>
                <th className="py-2 px-2 font-medium">Vendor OUI</th>
                <th className="py-2 px-2 font-medium">Port Terbuka (Layanan)</th>
                <th className="py-2 px-2 font-medium">Jangkauan</th>
                <th className="py-2 px-2 font-medium text-right">RTT (ms)</th>
                <th className="py-2 px-2 font-medium text-center">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-mono">
              {filteredHosts.map((host, idx) => {
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

                const isScanningThis = scanningIp === host.ip;
                const openPorts = host.open_ports || [];

                return (
                  <tr
                    key={`${host.ip}_${idx}`}
                    className="hover:bg-white/[0.02] transition-colors"
                  >
                    {/* IP & Role */}
                    <td className="py-2 px-2 font-semibold text-zinc-100 tabular-nums">
                      <div className="flex items-center gap-1.5">
                        {host.is_gateway ? (
                          <Broadcast size={13} className="text-amber-400 shrink-0" />
                        ) : host.is_self ? (
                          <Laptop size={13} className="text-[var(--color-signal)] shrink-0" />
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
                      </div>
                    </td>

                    {/* Hostname */}
                    <td className="py-2 px-2 text-zinc-300 font-sans text-xs truncate max-w-[130px]">
                      {host.hostname || "--"}
                    </td>

                    {/* Vendor OUI */}
                    <td className="py-2 px-2 text-zinc-400 font-sans text-xs truncate max-w-[130px]">
                      {host.oui_vendor || "Unknown"}
                    </td>

                    {/* Open Ports Badges */}
                    <td className="py-2 px-2 font-sans">
                      {openPorts.length > 0 ? (
                        <div className="flex flex-wrap items-center gap-1">
                          {openPorts.slice(0, 4).map((p, pIdx) => {
                            const style = getPortBadgeStyle(p.port);
                            return (
                              <button
                                key={`${p.port}_${pIdx}`}
                                type="button"
                                onClick={() => setSelectedHost(host)}
                                title={`${p.service} (Port ${p.port}/TCP) - Klik untuk detail`}
                                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border transition ${style.badge}`}
                              >
                                <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                                <span className="font-semibold">{p.port}</span>
                                <span className="text-[9px] opacity-75 font-sans uppercase">{p.service}</span>
                              </button>
                            );
                          })}
                          {openPorts.length > 4 && (
                            <button
                              type="button"
                              onClick={() => setSelectedHost(host)}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-300 border border-white/10 hover:bg-zinc-700 transition"
                            >
                              +{openPorts.length - 4} lagi
                            </button>
                          )}
                        </div>
                      ) : (
                        <span className="text-[11px] text-zinc-500 italic">
                          Belum ada port terbuka
                        </span>
                      )}
                    </td>

                    {/* Reachability */}
                    <td className="py-2 px-2">
                      <span
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-sans border ${reachabilityConfig.badge}`}
                      >
                        {reachabilityConfig.icon}
                        {reachabilityConfig.label}
                      </span>
                    </td>

                    {/* RTT */}
                    <td className="py-2 px-2 text-right tabular-nums text-zinc-400">
                      {host.rtt_ms !== null && host.rtt_ms !== undefined
                        ? `${host.rtt_ms.toFixed(1)}`
                        : "--"}
                    </td>

                    {/* Actions: Scan Ports */}
                    <td className="py-2 px-2 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleScanHost(host.ip)}
                          disabled={isScanningThis || scanningIp !== null}
                          title="Pindai port umum pada host ini"
                          className="py-1 px-2 rounded-[var(--radius-control)] border border-sky-500/30 hover:bg-sky-500/10 text-sky-400 text-[11px] font-sans flex items-center gap-1 transition disabled:opacity-40"
                        >
                          {isScanningThis ? (
                            <CircleNotch size={12} className="animate-spin text-sky-400" />
                          ) : (
                            <Crosshair size={12} />
                          )}
                          <span>{isScanningThis ? "Memindai..." : "Pindai Port"}</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => setSelectedHost(host)}
                          title="Lihat detail host"
                          className="p-1 rounded-[var(--radius-control)] border border-white/10 hover:bg-white/10 text-zinc-400 hover:text-zinc-200 transition text-xs"
                        >
                          <Tag size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Host Detail Modal / Popover */}
      {selectedHost && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-[#121316] border border-white/15 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl animate-scale-up">
            <div className="flex items-start justify-between border-b border-white/10 pb-3">
              <div>
                <h4 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                  <Laptop size={16} className="text-[var(--color-signal)]" />
                  Detail Host: {selectedHost.ip}
                </h4>
                <p className="text-xs text-zinc-400 font-sans mt-0.5">
                  {selectedHost.hostname || "Tanpa hostname terdaftar"} • {selectedHost.oui_vendor || "Vendor OUI tidak diketahui"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedHost(null)}
                className="text-zinc-400 hover:text-zinc-200 p-1 rounded hover:bg-white/10 transition"
              >
                <X size={16} />
              </button>
            </div>

            {/* Host Metadata Grid */}
            <div className="grid grid-cols-2 gap-2 text-xs font-sans">
              <div className="p-2 rounded bg-white/[0.03] border border-white/5 space-y-0.5">
                <span className="text-[10px] text-zinc-500 uppercase">Pseudonym MAC Hash</span>
                <p className="font-mono text-zinc-300 truncate">{selectedHost.mac_hash}</p>
              </div>
              <div className="p-2 rounded bg-white/[0.03] border border-white/5 space-y-0.5">
                <span className="text-[10px] text-zinc-500 uppercase">Waktu Respon (RTT)</span>
                <p className="font-mono text-zinc-300">
                  {selectedHost.rtt_ms !== null && selectedHost.rtt_ms !== undefined
                    ? `${selectedHost.rtt_ms.toFixed(2)} ms`
                    : "Tidak terukur"}
                </p>
              </div>
              <div className="p-2 rounded bg-white/[0.03] border border-white/5 space-y-0.5">
                <span className="text-[10px] text-zinc-500 uppercase">Metode Penemuan</span>
                <p className="text-zinc-300 truncate">{selectedHost.discovery_methods?.join(", ") || "arp_cache"}</p>
              </div>
              <div className="p-2 rounded bg-white/[0.03] border border-white/5 space-y-0.5">
                <span className="text-[10px] text-zinc-500 uppercase">Terakhir Terdeteksi</span>
                <p className="font-mono text-[11px] text-zinc-300 truncate">
                  {new Date(selectedHost.last_seen).toLocaleTimeString()}
                </p>
              </div>
            </div>

            {/* Open Ports List */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h5 className="text-xs font-semibold text-zinc-200 uppercase tracking-wider flex items-center gap-1.5">
                  <ShieldCheck size={14} className="text-sky-400" />
                  Daftar Port Terbuka ({selectedHost.open_ports?.length || 0})
                </h5>
                <button
                  type="button"
                  onClick={() => handleScanHost(selectedHost.ip)}
                  disabled={scanningIp !== null}
                  className="py-1 px-2 rounded bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 text-xs flex items-center gap-1 transition disabled:opacity-50"
                >
                  {scanningIp === selectedHost.ip ? (
                    <CircleNotch size={12} className="animate-spin" />
                  ) : (
                    <Crosshair size={12} />
                  )}
                  Pindai Ulang
                </button>
              </div>

              {(!selectedHost.open_ports || selectedHost.open_ports.length === 0) ? (
                <div className="p-4 rounded bg-black/30 border border-white/5 text-center text-xs text-zinc-400">
                  Belum ditemukan port TCP terbuka pada port umum standar. Klik &quot;Pindai Ulang&quot; untuk memeriksa kembali.
                </div>
              ) : (
                <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1 font-mono text-xs">
                  {selectedHost.open_ports.map((p, idx) => {
                    const style = getPortBadgeStyle(p.port);
                    return (
                      <div
                        key={`${p.port}_${idx}`}
                        className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5 hover:border-white/10 transition"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${style.dot}`} />
                          <span className="font-bold text-zinc-100">Port {p.port}</span>
                          <span className="text-zinc-400 text-[11px] font-sans">/ TCP</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-zinc-300 font-sans font-medium">{p.service}</span>
                          <span className="px-1.5 py-0.2 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-sans">
                            {p.state}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="pt-2 border-t border-white/10 flex items-center justify-between text-[11px] text-zinc-500">
              <span>Keamanan: Target terverifikasi dalam cakupan RFC 1918.</span>
              <button
                type="button"
                onClick={() => setSelectedHost(null)}
                className="py-1 px-3 rounded-[var(--radius-control)] border border-white/10 hover:bg-white/10 text-zinc-300 text-xs transition"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
