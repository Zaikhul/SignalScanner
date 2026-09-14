"use client";

import React from "react";
import { useScannerStore } from "@/lib/store";

export function SweepArmOverlay() {
  const { activeSession } = useScannerStore();
  const isScanning = activeSession?.status === "active";

  if (!isScanning) return null;

  return (
    <div className="absolute inset-0 pointer-events-none z-10 flex items-center justify-center">
      <div className="relative w-full h-full animate-radar-sweep flex items-center justify-center">
        {/* Sweep line gradient radiating from center */}
        <div
          className="absolute top-1/2 left-1/2 w-1/2 h-[2px] origin-left bg-gradient-to-r from-[var(--color-signal)] via-[var(--color-signal)]/60 to-transparent shadow-[0_0_8px_rgba(168,217,79,0.3)]"
          style={{ transform: "translateY(-50%)" }}
        />
        {/* Trailing wedge sweep gradient */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background:
              "conic-gradient(from 0deg at 50% 50%, rgba(168, 217, 79, 0.12) 0deg, rgba(168, 217, 79, 0.03) 30deg, transparent 60deg)",
          }}
        />
      </div>
    </div>
  );
}
