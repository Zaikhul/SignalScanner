"use client";

import React from "react";
import { WifiHigh, Bluetooth, Radio, Sparkle } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { ScanMode } from "@/lib/types";

export function ModeRail() {
  const { mode, setMode, activeSession, simulationMode, setSimulationMode } = useScannerStore();
  const isScanning = activeSession?.status === "active";

  const modes: { id: ScanMode; label: string; icon: React.ReactNode; desc: string }[] = [
    {
      id: "wifi",
      label: "WiFi 802.11",
      icon: <WifiHigh size={20} weight={mode === "wifi" ? "bold" : "regular"} />,
      desc: "Access points & occupancy",
    },
    {
      id: "bluetooth",
      label: "Bluetooth LE",
      icon: <Bluetooth size={20} weight={mode === "bluetooth" ? "bold" : "regular"} />,
      desc: "BLE beacons & proximity",
    },
    {
      id: "radio",
      label: "Radio SDR",
      icon: <Radio size={20} weight={mode === "radio" ? "bold" : "regular"} />,
      desc: "Spectrum & waterfall",
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider block mb-2">
          Mode Pemindaian
        </label>
        <div className="grid grid-cols-1 gap-1.5">
          {modes.map((m) => {
            const isSelected = mode === m.id;
            return (
              <button
                key={m.id}
                type="button"
                disabled={isScanning}
                onClick={() => setMode(m.id)}
                className={`w-full flex items-center gap-3 p-2.5 rounded-[var(--radius-control)] border text-left transition ${
                  isSelected
                    ? "bg-[var(--color-surface-raised)] border-[var(--color-signal)] text-zinc-100 shadow-[0_0_15px_rgba(168,217,79,0.08)]"
                    : "bg-[var(--color-surface)] border-white/10 text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
                } ${isScanning ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
              >
                <div
                  className={`p-2 rounded-lg ${
                    isSelected
                      ? "bg-[var(--color-signal)] text-zinc-950"
                      : "bg-white/5 text-zinc-400"
                  }`}
                >
                  {m.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-zinc-200 truncate">{m.label}</div>
                  <div className="text-[11px] text-zinc-500 truncate">{m.desc}</div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Simulator / Hardware Toggle */}
      <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkle size={16} className={simulationMode ? "text-[var(--color-signal)]" : "text-zinc-500"} />
          <div>
            <div className="text-xs font-medium text-zinc-200">Mode Simulasi</div>
            <div className="text-[10px] text-zinc-500">Virtual RF & beacon generator</div>
          </div>
        </div>
        <button
          type="button"
          disabled={isScanning}
          onClick={() => setSimulationMode(!simulationMode)}
          className={`w-9 h-5 rounded-full p-0.5 transition-colors ${
            simulationMode ? "bg-[var(--color-signal)]" : "bg-zinc-800 border border-white/10"
          }`}
        >
          <div
            className={`w-4 h-4 rounded-full bg-zinc-950 transition-transform ${
              simulationMode ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
      </div>
    </div>
  );
}
