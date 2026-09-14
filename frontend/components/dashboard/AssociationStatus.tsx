"use client";

import React from "react";
import { CircleNotch, CheckCircle, WarningCircle, PlugsConnected, Plugs } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";

export function AssociationStatus() {
  const { activeAssociation } = useScannerStore();

  if (!activeAssociation || activeAssociation.state === "idle") {
    return null;
  }

  const state = activeAssociation.state;

  const stateConfigs: Record<
    string,
    { label: string; icon: React.ReactNode; colorClass: string; bgClass: string }
  > = {
    requesting_permission: {
      label: "Meminta Izin Sistem...",
      icon: <CircleNotch size={14} className="animate-spin" />,
      colorClass: "text-amber-400 border-amber-500/30",
      bgClass: "bg-amber-950/40",
    },
    associating: {
      label: "Menghubungkan Radio...",
      icon: <CircleNotch size={14} className="animate-spin" />,
      colorClass: "text-sky-400 border-sky-500/30",
      bgClass: "bg-sky-950/40",
    },
    authenticating: {
      label: "Autentikasi Keamanan...",
      icon: <CircleNotch size={14} className="animate-spin" />,
      colorClass: "text-sky-400 border-sky-500/30",
      bgClass: "bg-sky-950/40",
    },
    obtaining_address: {
      label: "Memperoleh Alamat IP (DHCP)...",
      icon: <CircleNotch size={14} className="animate-spin" />,
      colorClass: "text-yellow-400 border-yellow-500/30",
      bgClass: "bg-yellow-950/40",
    },
    connected: {
      label: "Terhubung ke Jaringan",
      icon: <CheckCircle size={14} weight="fill" />,
      colorClass: "text-[var(--color-signal)] border-[var(--color-signal)]/30",
      bgClass: "bg-emerald-950/30",
    },
    disconnecting: {
      label: "Memutuskan Jaringan...",
      icon: <CircleNotch size={14} className="animate-spin" />,
      colorClass: "text-zinc-400 border-zinc-500/30",
      bgClass: "bg-zinc-950/40",
    },
    failed: {
      label: "Koneksi Gagal",
      icon: <WarningCircle size={14} weight="fill" />,
      colorClass: "text-red-400 border-red-500/30",
      bgClass: "bg-red-950/40",
    },
  };

  const current = stateConfigs[state] || {
    label: state,
    icon: <Plugs size={14} />,
    colorClass: "text-zinc-400 border-zinc-500/30",
    bgClass: "bg-zinc-950",
  };

  return (
    <div
      className={`px-3 py-1.5 rounded-[var(--radius-control)] border text-xs flex items-center justify-between gap-2 ${current.colorClass} ${current.bgClass}`}
    >
      <div className="flex items-center gap-2">
        {current.icon}
        <span className="font-medium">{current.label}</span>
      </div>
      {activeAssociation.ssid && (
        <span className="font-mono text-[11px] opacity-80 truncate max-w-[140px]">
          {activeAssociation.ssid}
        </span>
      )}
    </div>
  );
}
