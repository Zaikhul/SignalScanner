"use client";

import React, { useState } from "react";
import { Warning, Plugs, Broadcast } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";

export function AdapterConflictBanner() {
  const {
    activeAssociation,
    adapterConflictNotice,
    updateAssociationState,
  } = useScannerStore();

  const [isDisconnecting, setIsDisconnecting] = useState(false);

  // Visible if associated or conflict notice exists
  const isVisible =
    Boolean(adapterConflictNotice) ||
    (activeAssociation &&
      (activeAssociation.state === "connected" ||
        activeAssociation.state === "associating" ||
        activeAssociation.state === "obtaining_address"));

  if (!isVisible) {
    return null;
  }

  const ssid = activeAssociation?.ssid || "Jaringan WiFi";

  const handleDisconnect = async () => {
    if (!activeAssociation) return;
    setIsDisconnecting(true);
    try {
      await apiClient.disconnectAssociation(activeAssociation.id, true);
      updateAssociationState("idle");
    } catch (e) {
      console.error("Disconnect error", e);
    } finally {
      setIsDisconnecting(false);
    }
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-amber-950/80 border-b border-amber-500/30 px-4 py-2 text-amber-200 text-xs flex flex-wrap items-center justify-between gap-3 backdrop-blur-md animate-fade-in"
    >
      <div className="flex items-center gap-2.5">
        <div className="p-1 rounded bg-amber-500/20 text-amber-400">
          <Broadcast size={16} />
        </div>
        <div>
          <span className="font-semibold text-amber-100 mr-1.5">
            Pemindaian AP Dijeda:
          </span>
          <span className="text-amber-300">
            Radio adapter sedang terhubung ke <strong>{ssid}</strong>. Pemindaian live AP dijeda untuk menghindari konflik frekuensi radio.
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleDisconnect}
          disabled={isDisconnecting}
          className="py-1 px-3 rounded-[var(--radius-control)] bg-amber-500 hover:bg-amber-400 text-zinc-950 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
        >
          <Plugs size={14} />
          {isDisconnecting ? "Memutuskan..." : "Putuskan"}
        </button>
      </div>
    </div>
  );
}
