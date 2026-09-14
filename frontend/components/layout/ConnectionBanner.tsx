"use client";

import React from "react";
import { Warning, WifiSlash, ArrowsClockwise } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";

export function ConnectionBanner() {
  const { connectionState, droppedFrames, activeSession } = useScannerStore();

  if (!activeSession || connectionState === "connected" || connectionState === "idle") {
    if (droppedFrames > 0) {
      return (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-1.5 flex items-center justify-between text-xs text-amber-300">
          <div className="flex items-center gap-2">
            <Warning size={14} className="text-amber-400" />
            <span>Terdeteksi frame tertunda ({droppedFrames} frames). Sistem sedang menyelaraskan sequence data live.</span>
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="bg-rose-500/15 border-b border-rose-500/30 px-4 py-2 flex items-center justify-between text-xs text-rose-200">
      <div className="flex items-center gap-2">
        {connectionState === "reconnecting" ? (
          <>
            <ArrowsClockwise size={15} className="animate-spin text-rose-400" />
            <span>Koneksi WebSocket terputus. Mencoba menghubungkan kembali ke collector...</span>
          </>
        ) : (
          <>
            <WifiSlash size={15} className="text-rose-400" />
            <span>Collector tidak terhubung. Data baru akan muncul setelah koneksi pulih.</span>
          </>
        )}
      </div>
      <span className="font-mono text-[10px] text-rose-300/80 uppercase">Offline Buffer Aktif</span>
    </div>
  );
}
