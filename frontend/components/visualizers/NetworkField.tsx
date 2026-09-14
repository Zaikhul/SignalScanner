"use client";

import React, { useMemo } from "react";
import { useScannerStore } from "@/lib/store";
import { Info, Laptop, Broadcast } from "@phosphor-icons/react";

export function NetworkField() {
  const { activeAssociation, lanHosts } = useScannerStore();

  const isAssociated =
    activeAssociation && activeAssociation.state === "connected";

  // Compute deterministic visual positions (polar layout) based on IP hash
  const positionedHosts = useMemo(() => {
    const total = lanHosts.length;
    if (total === 0) return [];

    return lanHosts.map((host, idx) => {
      // Hash-like angle based on IP segments or index
      const ipParts = host.ip.split(".").map(Number);
      const seed = ipParts[3] || (idx + 1);
      const angle = (idx / total) * 2 * Math.PI + (seed % 10) * 0.05;

      // Distance from center: gateway closest, self next, others orbiting
      let r = 0.55;
      if (host.is_gateway) r = 0.2;
      else if (host.is_self) r = 0.35;
      else {
        // Distribute slightly based on RTT latency or reachability
        const latencyFactor = Math.min(1.0, (host.rtt_ms || 5) / 50);
        r = 0.5 + latencyFactor * 0.35;
      }

      const x = 50 + r * 45 * Math.cos(angle);
      const y = 50 + r * 45 * Math.sin(angle);

      return {
        ...host,
        x,
        y,
      };
    });
  }, [lanHosts]);

  if (!isAssociated) {
    return null;
  }

  return (
    <div className="relative w-full aspect-square max-w-[540px] mx-auto rounded-[var(--radius-panel)] bg-zinc-950 border border-white/10 overflow-hidden flex flex-col items-center justify-center p-4">
      {/* Visual Disclaimer Tooltip (PRD FR-INV-06 & Section 13.3) */}
      <div className="absolute top-3 left-3 z-10 flex items-center gap-1.5 text-[10px] text-zinc-500 bg-zinc-900/90 border border-white/10 px-2 py-1 rounded-[var(--radius-control)]">
        <Info size={13} className="text-zinc-400" />
        <span>Posisi adalah representasi relasional, bukan koordinat fisik atau meter.</span>
      </div>

      {/* Grid Rings */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none stroke-white/5 fill-none">
        <circle cx="50%" cy="50%" r="20%" strokeDasharray="3 3" />
        <circle cx="50%" cy="50%" r="35%" strokeDasharray="3 3" />
        <circle cx="50%" cy="50%" r="45%" />
        <line x1="50%" y1="5%" x2="50%" y2="95%" />
        <line x1="5%" y1="50%" x2="95%" y2="50%" />
      </svg>

      {/* Central Hub Label */}
      <div className="absolute z-0 flex flex-col items-center justify-center text-center pointer-events-none opacity-40">
        <span className="text-[10px] font-mono uppercase text-zinc-500">Subnet LAN</span>
        <span className="text-xs font-mono font-semibold text-zinc-300">
          {activeAssociation.prefix || "Attached"}
        </span>
      </div>

      {/* Discovered Host Beacons */}
      {positionedHosts.map((host, i) => {
        const isGw = host.is_gateway;
        const isSelf = host.is_self;

        const colorClasses = isGw
          ? "bg-amber-500 text-zinc-950 border-amber-300"
          : isSelf
          ? "bg-[var(--color-signal)] text-zinc-950 border-[var(--color-signal)]"
          : "bg-zinc-800 text-zinc-200 border-white/20";

        return (
          <div
            key={`${host.ip}_${i}`}
            style={{ left: `${host.x}%`, top: `${host.y}%` }}
            className="absolute -translate-x-1/2 -translate-y-1/2 group cursor-pointer z-10 transition-transform duration-300 hover:scale-125"
          >
            <div
              className={`w-7 h-7 rounded-full border flex items-center justify-center text-xs font-semibold shadow-lg ${colorClasses}`}
            >
              {isGw ? (
                <Broadcast size={14} weight="bold" />
              ) : isSelf ? (
                <Laptop size={14} weight="bold" />
              ) : (
                <span className="text-[10px] font-mono">{host.ip.split(".")[3] || "?"}</span>
              )}
            </div>

            {/* Hover Card */}
            <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 hidden group-hover:flex flex-col gap-1 w-44 p-2.5 rounded-[var(--radius-control)] bg-zinc-900 border border-white/20 text-zinc-200 text-[11px] shadow-2xl z-20 pointer-events-none">
              <div className="font-semibold text-zinc-100 flex items-center justify-between">
                <span>{host.ip}</span>
                {isGw && (
                  <span className="text-[9px] px-1 rounded bg-amber-500/20 text-amber-300">
                    Gateway
                  </span>
                )}
                {isSelf && (
                  <span className="text-[9px] px-1 rounded bg-[var(--color-signal)]/20 text-[var(--color-signal)]">
                    Self
                  </span>
                )}
              </div>
              {host.hostname && (
                <div className="text-zinc-400 truncate">{host.hostname}</div>
              )}
              <div className="text-[10px] text-zinc-500 font-mono">
                {host.oui_vendor || "Unknown Vendor"}
              </div>
              <div className="flex items-center justify-between text-[10px] text-zinc-400 pt-1 border-t border-white/10">
                <span>Status: {host.reachability === "up" ? "Hidup" : host.reachability}</span>
                {host.rtt_ms !== null && host.rtt_ms !== undefined && (
                  <span>{host.rtt_ms.toFixed(1)} ms</span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
