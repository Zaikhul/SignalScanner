"use client";

import React, { useEffect, useState } from "react";
import { HardDrives, CheckCircle, WarningCircle, RadioButton, CircleNotch } from "@phosphor-icons/react";
import { apiClient } from "@/lib/apiClient";
import { useScannerStore } from "@/lib/store";
import { Collector, CollectorStatus } from "@/lib/types";

export function CollectorPicker() {
  const { selectedCollectorId, setSelectedCollectorId, setCollectors, collectors } = useScannerStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadCollectors() {
      try {
        const list = await apiClient.listCollectors();
        if (isMounted) {
          setCollectors(list);
          if (list.length > 0 && (!selectedCollectorId || selectedCollectorId === "col_default")) {
            const active = list.find((c) => c.status === "ready" || c.status === "busy") || list[0];
            setSelectedCollectorId(active.id);
          }
        }
      } catch (e) {
        console.debug("Failed to poll collectors", e);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadCollectors();
    // Poll every 3 seconds for dynamic auto-discovery of newly started daemons
    const interval = setInterval(loadCollectors, 3000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [setCollectors, setSelectedCollectorId, selectedCollectorId]);

  const selected = collectors.find((c) => c.id === selectedCollectorId) || collectors[0];
  const rawStatus = (selected?.status || "offline") as CollectorStatus;

  // Helper to render badge styles & text
  const getStatusBadge = (status: CollectorStatus) => {
    switch (status) {
      case "ready":
        return {
          icon: <CheckCircle size={12} weight="fill" className="text-emerald-400" />,
          label: "Ready",
          colorClass: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
        };
      case "busy":
      case "scanning":
        return {
          icon: <CircleNotch size={12} className="animate-spin text-cyan-400" />,
          label: "Scanning",
          colorClass: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
        };
      case "starting":
        return {
          icon: <RadioButton size={12} className="animate-pulse text-amber-400" />,
          label: "Starting",
          colorClass: "text-amber-400 bg-amber-500/10 border-amber-500/20",
        };
      case "offline":
        return {
          icon: <RadioButton size={12} className="text-zinc-500" />,
          label: "Offline",
          colorClass: "text-zinc-400 bg-zinc-800 border-zinc-700",
        };
      case "permission_denied":
      case "error":
      default:
        return {
          icon: <WarningCircle size={12} weight="fill" className="text-rose-400" />,
          label: "Error",
          colorClass: "text-rose-400 bg-rose-500/10 border-rose-500/20",
        };
    }
  };

  const badge = getStatusBadge(rawStatus);

  return (
    <div className="space-y-2">
      <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider block">
        Perangkat Collector
      </label>

      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HardDrives size={16} className="text-zinc-400" />
            <span className="text-xs font-medium text-zinc-200">
              {selected?.name || "Local Host Scanner"}
            </span>
          </div>
          <div className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] font-mono font-medium ${badge.colorClass}`}>
            {badge.icon}
            <span>{badge.label}</span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-1 pt-1 text-[10px] font-mono text-zinc-400 border-t border-white/5">
          <div>
            <span className="text-zinc-500 block">OS:</span>
            <span className="text-zinc-300 capitalize">{selected?.platform || "Windows"}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">WiFi:</span>
            <span className="text-zinc-300">WlanApi</span>
          </div>
          <div>
            <span className="text-zinc-500 block">BLE:</span>
            <span className="text-zinc-300">Bleak</span>
          </div>
        </div>
      </div>
    </div>
  );
}
