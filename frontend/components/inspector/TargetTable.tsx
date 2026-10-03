"use client";

import React, { useState, useMemo, useEffect } from "react";
import {
  MagnifyingGlass,
  PushPin,
  CaretDown,
  CaretRight,
  WarningOctagon,
  Clock,
  Question,
} from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";
import { TargetSummary } from "@/lib/types";
import { evaluateTargetFreshness } from "@/lib/scanfieldMath";

export function TargetTable() {
  const {
    targets,
    selectedTargetId,
    setSelectedTargetId,
    activeSession,
    setTargets,
    mode,
    searchQuery,
    setSearchQuery,
    viewMode,
    setViewMode,
    showExpiredHistory,
    setShowExpiredHistory,
  } = useScannerStore();

  const [expandedSsid, setExpandedSsid] = useState<Record<string, boolean>>({});
  const [now, setNow] = useState(Date.now());

  // Tick clock every 2 seconds for freshness update
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 2000);
    return () => clearInterval(timer);
  }, []);

  // Filter and compute unified freshness status
  const processedTargets = useMemo(() => {
    return targets
      .map((t) => {
        const { freshness, isStale, isExpired, ageSeconds } = evaluateTargetFreshness(t, now, mode);
        return {
          ...t,
          computed_freshness: freshness,
          is_stale: isStale,
          is_expired: isExpired,
          age_seconds: ageSeconds,
        };
      })
      .filter((t) => {
        // Exclude expired from live view unless showExpiredHistory is enabled
        if (!showExpiredHistory && t.is_expired) return false;

        const term = searchQuery.trim().toLowerCase();
        if (!term) return true;

        return (
          (t.display_name && t.display_name.toLowerCase().includes(term)) ||
          t.target_id.toLowerCase().includes(term) ||
          (t.channel && t.channel.toString().includes(term)) ||
          (t.band && t.band.toLowerCase().includes(term))
        );
      });
  }, [targets, searchQuery, showExpiredHistory, now, mode]);

  // Group by SSID when viewMode === 'ssid'
  const groupedSsidList = useMemo(() => {
    if (viewMode === "bssid") return [];

    const map = new Map<
      string,
      { groupKey: string; ssid: string; targets: typeof processedTargets }
    >();

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
          <div className="inline-flex rounded-[var(--radius-control)] bg-[var(--color-canvas)] p-0.5 border border-[var(--color-line)] text-xs">
            <button
              type="button"
              onClick={() => setViewMode("ssid")}
              className={`px-2.5 py-1 rounded-[calc(var(--radius-control)-2px)] font-medium transition cursor-pointer ${
                viewMode === "ssid"
                  ? "bg-[var(--color-surface-raised)] text-[var(--color-signal-lime)]"
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
                  ? "bg-[var(--color-surface-raised)] text-[var(--color-signal-lime)]"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Per BSSID
            </button>
          </div>

          {/* Stale/History Filter Toggle */}
          <label className="text-[11px] text-zinc-400 flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showExpiredHistory}
              onChange={(e) => setShowExpiredHistory(e.target.checked)}
              className="accent-[var(--color-signal-lime)] rounded"
            />
            <span>Tampilkan Riwayat</span>
          </label>
        </div>

        {/* Search Input */}
        <div className="relative">
          <MagnifyingGlass
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
          />
          <input
            type="text"
            placeholder="Cari SSID, device name, kanal, atau ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[var(--radius-control)] pl-8 pr-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-[var(--color-signal-lime)]"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-zinc-500 hover:text-zinc-300 font-mono"
            >
              Hapus
            </button>
          )}
        </div>
      </div>

      {/* Target List Rendering */}
      <div className="space-y-1.5 max-h-[380px] overflow-y-auto pr-1" role="list">
        {viewMode === "ssid" ? (
          // --- MODE PER SSID (GROUPED NETWORK VIEW) ---
          groupedSsidList.length === 0 ? (
            <div className="text-center py-8 text-xs text-zinc-500 bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[var(--radius-panel)]">
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
                  className={`rounded-[var(--radius-control)] border border-[var(--color-line)] bg-[var(--color-surface)] overflow-hidden transition ${
                    allStale ? "opacity-75" : "opacity-100"
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
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        if (bssidCount > 1) {
                          toggleExpand(group.groupKey);
                        } else {
                          setSelectedTargetId(bestTarget.target_id);
                        }
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    className="p-2.5 flex items-center justify-between gap-3 hover:bg-[var(--color-surface-raised)] cursor-pointer focus:outline-none focus:ring-1 focus:ring-[var(--color-signal-lime)]"
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
                          <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-[var(--color-canvas)] text-zinc-400 border border-[var(--color-line)]">
                            {bssidCount} BSSID
                          </span>
                        )}

                        {allStale && (
                          <span className="inline-flex items-center gap-1 text-[10px] text-[var(--color-status-warning)] font-mono">
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
                        <div className="w-14 h-1.5 bg-[var(--color-canvas)] border border-[var(--color-line)] rounded-full overflow-hidden mt-1 ml-auto">
                          <div
                            className="h-full bg-[var(--color-signal-lime)] rounded-full transition-all"
                            style={{ width: `${Math.round(norm * 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Child BSSID Entries (when expanded) */}
                  {isExpanded && bssidCount > 1 && (
                    <div className="bg-[var(--color-canvas)] border-t border-[var(--color-line)] p-2 space-y-1.5">
                      {group.targets.map((child) => {
                        const isSelected = child.target_id === selectedTargetId;

                        return (
                          <div
                            key={child.target_id}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedTargetId(child.target_id);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                e.stopPropagation();
                                setSelectedTargetId(child.target_id);
                              }
                            }}
                            tabIndex={0}
                            role="button"
                            className={`p-2 rounded-[calc(var(--radius-control)-2px)] border text-xs flex items-center justify-between gap-2 cursor-pointer transition focus:outline-none focus:ring-1 focus:ring-[var(--color-signal-lime)] ${
                              isSelected
                                ? "bg-[var(--color-surface-raised)] border-[var(--color-signal-lime)] text-zinc-100"
                                : "border-[var(--color-line)] hover:bg-[var(--color-surface)] text-zinc-400"
                            }`}
                          >
                            <div className="truncate flex items-center gap-1.5">
                              {child.is_pinned && (
                                <PushPin
                                  size={11}
                                  weight="fill"
                                  className="text-[var(--color-signal-lime)] shrink-0"
                                />
                              )}
                              <span className="font-mono text-[11px] text-zinc-300">
                                {child.target_id}
                              </span>
                              <span className="text-[10px] text-zinc-500 ml-1">
                                {child.band} • Ch {child.channel || "-"}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 font-mono text-xs tabular-nums text-zinc-200 shrink-0">
                              {child.delta_signal !== undefined && child.delta_signal !== null && (
                                <span
                                  className={`text-[10px] ${
                                    child.delta_signal > 0
                                      ? "text-[var(--color-signal-lime)]"
                                      : child.delta_signal < 0
                                      ? "text-[var(--color-status-error)]"
                                      : "text-zinc-500"
                                  }`}
                                >
                                  {child.delta_signal > 0 ? `+${child.delta_signal}` : child.delta_signal} dB
                                </span>
                              )}
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
            <div className="text-center py-8 text-xs text-zinc-500 bg-[var(--color-surface)] border border-[var(--color-line)] rounded-[var(--radius-panel)]">
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
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedTargetId(t.target_id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  className={`p-2.5 rounded-[var(--radius-control)] border transition cursor-pointer flex items-center justify-between gap-3 focus:outline-none focus:ring-1 focus:ring-[var(--color-signal-lime)] ${
                    t.is_stale ? "opacity-75" : "opacity-100"
                  } ${
                    isSelected
                      ? "bg-[var(--color-surface-raised)] border-[var(--color-signal-lime)] text-zinc-100"
                      : "bg-[var(--color-surface)] border-[var(--color-line)] text-zinc-400 hover:text-zinc-200 hover:bg-[var(--color-surface-raised)]"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-zinc-200 truncate">
                        {t.display_name || "Hidden Emitter"}
                      </span>
                      {t.is_pinned && (
                        <PushPin
                          size={12}
                          weight="fill"
                          className="text-[var(--color-signal-lime)] shrink-0"
                        />
                      )}
                      {t.computed_freshness === "stale" && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-[var(--color-status-warning)] font-mono">
                          <WarningOctagon size={11} />
                          Stale
                        </span>
                      )}
                      {t.computed_freshness === "expired" && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-zinc-500 font-mono">
                          <Clock size={11} />
                          Riwayat
                        </span>
                      )}
                      {t.computed_freshness === "unknown" && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-zinc-500 font-mono">
                          <Question size={11} />
                          Unknown
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
                      <div className="flex items-center justify-end gap-1.5 font-mono text-xs font-semibold tabular-nums text-zinc-100">
                        {t.delta_signal !== undefined && t.delta_signal !== null && (
                          <span
                            className={`text-[10px] ${
                              t.delta_signal > 0
                                ? "text-[var(--color-signal-lime)]"
                                : t.delta_signal < 0
                                ? "text-[var(--color-status-error)]"
                                : "text-zinc-500"
                            }`}
                          >
                            {t.delta_signal > 0 ? `+${t.delta_signal}` : t.delta_signal}
                          </span>
                        )}
                        <span>
                          {t.latest_signal}{" "}
                          <span className="text-[9px] text-zinc-500 font-normal">{t.unit}</span>
                        </span>
                      </div>
                      <div className="w-16 h-1.5 bg-[var(--color-canvas)] border border-[var(--color-line)] rounded-full overflow-hidden mt-1 ml-auto">
                        <div
                          className="h-full bg-[var(--color-signal-lime)] rounded-full transition-all"
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
