"use client";

import React, { useState, useMemo, useEffect } from "react";
import { MagnifyingGlass, PushPin, WifiHigh, Bluetooth, Radio, CaretDown, CaretRight, WarningOctagon, Stack } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";
import { TargetSummary } from "@/lib/types";

export function TargetTable() {
  const { targets, selectedTargetId, setSelectedTargetId, activeSession, setTargets } = useScannerStore();
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"ssid" | "bssid">("ssid");
  const [showStale, setShowStale] = useState(false);
  const [expandedSsid, setExpandedSsid] = useState<Record<string, boolean>>({});
  const [now, setNow] = useState(Date.now());

  // Tick clock every 5 seconds for stale/decay calculation
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);

  // Filter and compute stale/decay status
  const processedTargets = useMemo(() => {
    return targets
      .map((t) => {
        const lastSeenMs = new Date(t.last_seen).getTime();
        const ageMs = now - lastSeenMs;
        const isStale = ageMs > 30000; // > 30 seconds
        const isExpired = ageMs > 60000; // > 60 seconds TTL
        return {
          ...t,
          is_stale: isStale,
          is_expired: isExpired,
        };
      })
      .filter((t) => {
        // Exclude expired from live view unless showStale is enabled
        if (!showStale && t.is_expired) return false;

        const term = search.toLowerCase();
        return (
          (t.display_name && t.display_name.toLowerCase().includes(term)) ||
          t.target_id.toLowerCase().includes(term) ||
          (t.channel && t.channel.toString().includes(term))
        );
      });
  }, [targets, search, showStale, now]);

  // Group by SSID when viewMode === 'ssid'
  const groupedSsidList = useMemo(() => {
    if (viewMode === "bssid") return [];

    const map = new Map<string, { groupKey: string; ssid: string; targets: typeof processedTargets }>();

    for (const t of processedTargets) {
      const isHidden = !t.display_name || t.display_name.toLowerCase().includes("hidden");
      // Hidden SSIDs must NOT be merged together; keep distinct group key per BSSID
      const groupKey = isHidden ? `hidden_${t.target_id}` : `${t.display_name}_${t.mode}`;

      if (!map.has(groupKey)) {
        map.set(groupKey, {
          groupKey,
          ssid: t.display_name || "Hidden Network",
          targets: [],
        });
      }
      map.get(groupKey)!.targets.push(t);
    }

    return Array.from(map.values()).sort((a, b) => {
      const maxA = Math.max(...a.targets.map((t) => t.latest_signal));
      const maxB = Math.max(...b.targets.map((t) => t.latest_signal));
      return maxB - maxA;
    });
  }, [processedTargets, viewMode]);

  const handleTogglePin = async (e: React.MouseEvent, target: TargetSummary) => {
    e.stopPropagation();
    if (!activeSession) return;

    try {
      const res = await apiClient.togglePinTarget(activeSession.id, target.target_id);
      setTargets(
        targets.map((t) =>
          t.target_id === target.target_id ? { ...t, is_pinned: res.is_pinned } : t
        )
      );
    } catch (err) {
      console.error("Failed to toggle pin", err);
    }
  };

  const toggleExpand = (groupKey: string) => {
    setExpandedSsid((prev) => ({ ...prev, [groupKey]: !prev[groupKey] }));
  };

  return (
    <div className="space-y-3">
      {/* Header Controls: Search & View Mode Switcher */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          {/* View Mode Toggle */}
          <div className="inline-flex rounded-[var(--radius-control)] bg-zinc-950 p-0.5 border border-white/10 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("ssid")}
              className={`px-2.5 py-1 rounded-[calc(var(--radius-control)-2px)] font-medium transition cursor-pointer ${
                viewMode === "ssid"
                  ? "bg-[var(--color-surface-raised)] text-[var(--color-signal)] shadow"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Per SSID
            </button>
            <button
              type="button"
              onClick={() => setViewMode("bssid")}
              className={`px-2.5 py-1 rounded-[calc(var(--radius-control)-2px)] font-medium transition cursor-pointer ${
                viewMode === "bssid"
                  ? "bg-[var(--color-surface-raised)] text-[var(--color-signal)] shadow"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Per BSSID
            </button>
          </div>

          {/* Stale Filter Toggle */}
          <label className="text-[11px] text-zinc-500 flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={showStale}
              onChange={(e) => setShowStale(e.target.checked)}
              className="accent-[var(--color-signal)] rounded"
            />
            <span>Tampilkan Riwayat (&gt;60s)</span>
          </label>
        </div>

        {/* Search Input */}
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Cari SSID, device name, kanal, atau ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[var(--color-surface)] border border-white/10 rounded-[var(--radius-control)] pl-8 pr-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-[var(--color-signal)]"
          />
        </div>
      </div>

      {/* Target List Rendering */}
      <div className="space-y-1.5 max-h-[380px] overflow-y-auto pr-1">
        {viewMode === "ssid" ? (
          // --- MODE PER SSID (GROUPED NETWORK VIEW) ---
          groupedSsidList.length === 0 ? (
            <div className="text-center py-8 text-xs text-zinc-500">
              {targets.length === 0 ? "Belum ada target terdeteksi..." : "Tidak ada hasil pencarian"}
            </div>
          ) : (
            groupedSsidList.map((group) => {
              const bestTarget = group.targets[0];
              const isExpanded = !!expandedSsid[group.groupKey];
              const bssidCount = group.targets.length;
              const maxRssi = Math.max(...group.targets.map((t) => t.latest_signal));
              const norm = Math.max(0, Math.min(1, (maxRssi + 100) / 70));
              const allStale = group.targets.every((t) => t.is_stale);

              return (
                <div
                  key={group.groupKey}
                  className={`rounded-[var(--radius-control)] border border-white/10 bg-[var(--color-surface)] overflow-hidden transition ${
                    allStale ? "opacity-60" : "opacity-100"
                  }`}
                >
                  {/* Parent SSID Header */}
                  <div
                    onClick={() => {
                      if (bssidCount > 1) {
                        toggleExpand(group.groupKey);
                      } else {
                        setSelectedTargetId(bestTarget.target_id);
                      }
                    }}
                    className="p-2.5 flex items-center justify-between gap-3 hover:bg-white/5 cursor-pointer"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {bssidCount > 1 ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(group.groupKey);
                            }}
                            className="text-zinc-400 hover:text-zinc-200"
                          >
                            {isExpanded ? <CaretDown size={14} /> : <CaretRight size={14} />}
                          </button>
                        ) : null}

                        <span className="text-xs font-semibold text-zinc-200 truncate">
                          {group.ssid}
                        </span>

                        {bssidCount > 1 && (
                          <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-zinc-800 text-zinc-400">
                            {bssidCount} BSSID
                          </span>
                        )}

                        {allStale && (
                          <span className="inline-flex items-center gap-1 text-[10px] text-amber-400 font-mono">
                            <WarningOctagon size={11} />
                            Stale
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-zinc-500 truncate">
                        {group.targets.map((t) => (
                          <span key={t.target_id}>
                            {t.band || "2.4GHz"} (Ch {t.channel || 1})
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Peak Signal Bar */}
                    <div className="flex items-center gap-2 text-right shrink-0">
                      <div>
                        <span className="font-mono text-xs font-semibold tabular-nums text-zinc-100 block">
                          {maxRssi} <span className="text-[9px] text-zinc-500">{bestTarget.unit}</span>
                        </span>
                        <div className="w-14 h-1.5 bg-zinc-800 rounded-full overflow-hidden mt-1 ml-auto">
                          <div
                            className="h-full bg-[var(--color-signal)] rounded-full transition-all"
                            style={{ width: `${Math.round(norm * 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Child BSSID Entries (when expanded or single) */}
                  {isExpanded && bssidCount > 1 && (
                    <div className="bg-zinc-950/60 border-t border-white/5 p-2 space-y-1.5">
                      {group.targets.map((child) => {
                        const childNorm = Math.max(0, Math.min(1, (child.latest_signal + 100) / 70));
                        const isSelected = child.target_id === selectedTargetId;

                        return (
                          <div
                            key={child.target_id}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedTargetId(child.target_id);
                            }}
                            className={`p-2 rounded-[calc(var(--radius-control)-2px)] border text-xs flex items-center justify-between gap-2 cursor-pointer transition ${
                              isSelected
                                ? "bg-[var(--color-surface-raised)] border-[var(--color-signal)] text-zinc-100"
                                : "border-white/5 hover:bg-white/5 text-zinc-400"
                            }`}
                          >
                            <div className="truncate">
                              <span className="font-mono text-[11px] text-zinc-300">
                                {child.target_id}
                              </span>
                              <span className="text-[10px] text-zinc-500 ml-2">
                                {child.band} • Kanal {child.channel || "-"}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 font-mono text-xs tabular-nums text-zinc-200">
                              <span>{child.latest_signal} dBm</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          )
        ) : (
          // --- MODE PER BSSID (GRANULAR EMITTER VIEW) ---
          processedTargets.length === 0 ? (
            <div className="text-center py-8 text-xs text-zinc-500">
              {targets.length === 0 ? "Belum ada target terdeteksi..." : "Tidak ada hasil pencarian"}
            </div>
          ) : (
            processedTargets.map((t) => {
              const isSelected = t.target_id === selectedTargetId;
              const norm = Math.max(0, Math.min(1, (t.latest_signal + 100) / 70));

              return (
                <div
                  key={t.target_id}
                  onClick={() => setSelectedTargetId(t.target_id)}
                  className={`p-2.5 rounded-[var(--radius-control)] border transition cursor-pointer flex items-center justify-between gap-3 ${
                    t.is_stale ? "opacity-60" : "opacity-100"
                  } ${
                    isSelected
                      ? "bg-[var(--color-surface-raised)] border-[var(--color-signal)] text-zinc-100 shadow-[0_0_12px_rgba(168,217,79,0.06)]"
                      : "bg-[var(--color-surface)] border-white/10 text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-zinc-200 truncate">
                        {t.display_name || "Hidden Emitter"}
                      </span>
                      {t.is_pinned && (
                        <PushPin size={12} weight="fill" className="text-[var(--color-signal)] shrink-0" />
                      )}
                      {t.is_stale && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-amber-400 font-mono">
                          <WarningOctagon size={11} />
                          Stale
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 mt-0.5 text-[10px] font-mono text-zinc-500 truncate">
                      <span>{t.target_id}</span>
                      {t.channel && <span>• Kanal {t.channel}</span>}
                      {t.band && <span>({t.band})</span>}
                    </div>
                  </div>

                  {/* RSSI Signal Bar & Value */}
                  <div className="flex items-center gap-2 text-right shrink-0">
                    <div>
                      <span className="font-mono text-xs font-semibold tabular-nums text-zinc-100 block">
                        {t.latest_signal} <span className="text-[9px] text-zinc-500">{t.unit}</span>
                      </span>
                      <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden mt-1 ml-auto">
                        <div
                          className="h-full bg-[var(--color-signal)] rounded-full transition-all"
                          style={{ width: `${Math.round(norm * 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )
        )}
      </div>
    </div>
  );
}
