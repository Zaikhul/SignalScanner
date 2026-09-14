"use client";

import React, { useState } from "react";
import { Plugs, PlugsConnected, Warning, Lock, LockOpen } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";
import { TargetSummary } from "@/lib/types";

interface ConnectActionProps {
  target: TargetSummary;
}

export function ConnectAction({ target }: ConnectActionProps) {
  const {
    activeSession,
    activeAssociation,
    setCredentialModalOpen,
    setTargetToAssociate,
    updateAssociationState,
  } = useScannerStore();

  const [isDisconnecting, setIsDisconnecting] = useState(false);

  // Determine security type
  const rawSecurity = target.extra?.security || target.extra?.auth || "WPA2";
  const isEnterprise =
    rawSecurity.toLowerCase().includes("enterprise") ||
    rawSecurity.toLowerCase().includes("802.1x");
  const isOpen =
    rawSecurity.toLowerCase().includes("open") ||
    rawSecurity.toLowerCase().includes("none");

  // Check if currently connected to THIS target
  const isCurrentlyAssociated =
    activeAssociation &&
    (activeAssociation.state === "connected" || activeAssociation.state === "associating") &&
    (activeAssociation.target_id === target.target_id || activeAssociation.ssid === target.display_name);

  const handleConnectClick = () => {
    setTargetToAssociate(target);
    setCredentialModalOpen(true);
  };

  const handleDisconnect = async () => {
    if (!activeAssociation) return;
    setIsDisconnecting(true);
    try {
      await apiClient.disconnectAssociation(activeAssociation.id, true);
      updateAssociationState("idle");
    } catch (e) {
      console.error("Failed to disconnect", e);
    } finally {
      setIsDisconnecting(false);
    }
  };

  if (target.mode !== "wifi") {
    return null;
  }

  return (
    <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
          Aksi Asosiasi Jaringan
        </span>
        <span className="flex items-center gap-1 text-[11px] font-mono text-zinc-400">
          {isOpen ? (
            <>
              <LockOpen size={13} className="text-zinc-400" /> Open
            </>
          ) : isEnterprise ? (
            <>
              <Warning size={13} className="text-amber-400" /> Enterprise
            </>
          ) : (
            <>
              <Lock size={13} className="text-[var(--color-signal)]" /> {rawSecurity}
            </>
          )}
        </span>
      </div>

      {isEnterprise ? (
        <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-center gap-2">
          <Warning size={16} className="shrink-0 text-amber-400" />
          <span>Jaringan Enterprise (802.1X) belum didukung pada versi ini.</span>
        </div>
      ) : isCurrentlyAssociated ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-[var(--color-signal)] font-medium">
            <PlugsConnected size={16} />
            <span>Terhubung ke access point ini</span>
          </div>
          <button
            type="button"
            onClick={handleDisconnect}
            disabled={isDisconnecting}
            className="w-full py-2 px-3 rounded-[var(--radius-control)] bg-red-950/40 hover:bg-red-900/50 border border-red-500/30 text-red-300 text-xs font-medium flex items-center justify-center gap-1.5 transition disabled:opacity-50"
          >
            <Plugs size={15} />
            {isDisconnecting ? "Memutuskan..." : "Putuskan"}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={handleConnectClick}
          disabled={!activeSession}
          className="w-full py-2 px-3 rounded-[var(--radius-control)] bg-[var(--color-signal)] hover:bg-[var(--color-signal)]/90 text-zinc-950 text-xs font-semibold flex items-center justify-center gap-1.5 transition disabled:opacity-50"
        >
          <PlugsConnected size={16} weight="bold" />
          Hubungkan
        </button>
      )}

      <p className="text-[10px] text-zinc-500 leading-tight">
        Menghubungkan adapter collector ke SSID ini untuk menjalankan inventaris host LAN.
      </p>
    </div>
  );
}
