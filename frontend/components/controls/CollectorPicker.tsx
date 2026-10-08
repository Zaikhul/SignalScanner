"use client";

import React, { useEffect, useState } from "react";
import {
  HardDrives,
  CheckCircle,
  WarningCircle,
  RadioButton,
  CircleNotch,
  ArrowsClockwise,
} from "@phosphor-icons/react";
import { apiClient } from "@/lib/apiClient";
import { useScannerStore } from "@/lib/store";
import { Collector, CollectorStatus } from "@/lib/types";

export function CollectorPicker() {
  const {
    selectedCollectorId,
    setSelectedCollectorId,
    setCollectors,
    collectors,
  } = useScannerStore();
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadCollectors = React.useCallback(async (isManual: boolean = false) => {
    if (isManual) setIsRefreshing(true);
    try {
      const list = await apiClient.listCollectors();
      setCollectors(list);
      // Ensure selected collector is strictly col_default (Local Host Collector)
      setSelectedCollectorId("col_default");
    } catch (e) {
      console.debug("Failed to poll collectors", e);
    } finally {
      if (isManual) {
        setTimeout(() => setIsRefreshing(false), 600);
      }
    }
  }, [setCollectors, setSelectedCollectorId]);

  useEffect(() => {
    let isMounted = true;
    loadCollectors(false);

    // Poll every 3 seconds for dynamic auto-discovery of local collector status
    const interval = setInterval(() => {
      if (isMounted) loadCollectors(false);
    }, 3000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [loadCollectors]);

  // Dedicated single Local Host Collector
  const localCollector = collectors.find((c) => c.id === "col_default") || collectors[0] || {
    id: "col_default",
    name: "Local Host Collector",
    platform: "windows",
    version: "1.0.0",
    status: "ready" as CollectorStatus,
    capabilities: {
      supported_modes: ["wifi", "bluetooth", "radio"],
      adapters: [],
      platform: "windows",
      version: "1.0.0",
      can_wifi: true,
      can_ble: true,
      can_sdr: true,
    },
    last_seen: new Date().toISOString(),
    created_at: new Date().toISOString(),
  };

  const rawStatus = (localCollector?.status || "ready") as CollectorStatus;

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
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider block">
          Perangkat Collector
        </label>
        <button
          type="button"
          onClick={() => loadCollectors(true)}
          disabled={isRefreshing}
          className="text-zinc-400 hover:text-zinc-200 transition flex items-center gap-1 text-[11px] disabled:opacity-50 cursor-pointer"
          title="Pindai ulang koneksi daemon collector lokal"
        >
          <ArrowsClockwise size={12} className={isRefreshing ? "animate-spin text-[var(--color-signal)]" : ""} />
          <span>Segarkan</span>
        </button>
      </div>

      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 space-y-2.5">
        {/* Collector Identity Card */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded bg-white/5 text-zinc-300">
              <HardDrives size={16} />
            </div>
            <div>
              <div className="text-xs font-semibold text-zinc-100 font-sans">
                {localCollector?.name || "Local Host Collector"}
              </div>
              <div className="text-[10px] font-mono text-zinc-500">
                ID: {localCollector?.id || "col_default"}
              </div>
            </div>
          </div>
          <div
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] font-mono font-medium ${badge.colorClass}`}
          >
            {badge.icon}
            <span>{badge.label}</span>
          </div>
        </div>

        {/* Local Hardware Adapters Summary */}
        <div className="grid grid-cols-3 gap-1 pt-1 text-[10px] font-mono text-zinc-400 border-t border-white/5">
          <div>
            <span className="text-zinc-500 block">Platform:</span>
            <span className="text-zinc-300 capitalize">{localCollector?.platform || "Windows"}</span>
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
