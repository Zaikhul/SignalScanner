"use client";

import React, { useEffect, useState } from "react";
import { useScannerStore } from "@/lib/store";
import { isScanActivelyMoving } from "@/lib/scanfieldMath";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";

export function SweepArmOverlay() {
  const {
    activeSession,
    connectionState,
    adapterConflictNotice,
    lastActivityTimestamp,
    latestQuality,
  } = useScannerStore();

  const prefersReducedMotion = usePrefersReducedMotion();
  const [now, setNow] = useState<number>(Date.now());

  // Watchdog ticker every 1000ms
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  const isSessionActive = activeSession?.status === "active";
  if (!isSessionActive && !activeSession?.status?.includes("starting")) {
    return null;
  }

  const isMoving = isScanActivelyMoving({
    sessionStatus: activeSession?.status,
    connectionState,
    hasAdapterConflict: !!adapterConflictNotice,
    lastActivityTimestamp,
    actualIntervalMs: latestQuality?.actual_interval_ms,
    nowMs: now,
  });

  // If user prefers reduced motion, sweep arm is static
  const shouldAnimate = isMoving && !prefersReducedMotion;

  return (
    <div
      className="absolute inset-0 pointer-events-none z-10 flex items-center justify-center overflow-hidden"
      aria-hidden="true"
    >
      <div
        className={`relative w-full h-full flex items-center justify-center ${
          shouldAnimate ? "animate-radar-sweep" : ""
        }`}
        style={!shouldAnimate ? { transform: "rotate(0deg)" } : undefined}
      >
        {/*
          Pure Vector SVG Sweep Geometry
          Center is (50, 50).
          r_inner = 50 * 0.08 = 4
          r_outer = 50 * 0.86 = 43
          Trailing sector: 12 degrees behind sweep line (angle -12° to 0° from top).
          Flat opacity 6% (0.06), solid #a8d94f, NO gradients, NO AI slop.
        */}
        <svg
          viewBox="0 0 100 100"
          className="w-full h-full"
          style={{ overflow: "visible" }}
        >
          {isMoving && (
            <path
              d="M 50 7 A 43 43 0 0 0 41.06 7.94 L 49.17 46.09 A 4 4 0 0 1 50 46 Z"
              fill="#a8d94f"
              fillOpacity={0.06}
            />
          )}

          {/* Crisp radial sweep line (1px stroke equivalent) */}
          <line
            x1="50"
            y1="46"
            x2="50"
            y2="7"
            stroke={isMoving ? "#a8d94f" : "#78837f"}
            strokeWidth="0.5"
            strokeOpacity={isMoving ? 0.8 : 0.4}
            strokeDasharray={isMoving ? undefined : "1 1"}
          />
        </svg>
      </div>

      {/* Reduced Motion or Watchdog Halted Indicator Badge */}
      {prefersReducedMotion && isMoving && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-[var(--color-line)] text-[9px] font-mono text-[var(--color-signal-lime)]">
          MEMINDAI (STATIS)
        </div>
      )}
      {!isMoving && isSessionActive && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-[var(--color-status-warning)] text-[9px] font-mono text-[var(--color-status-warning)]">
          MENUNGGU PEMBARUAN
        </div>
      )}
    </div>
  );
}
