"use client";

import React from "react";
import { Network, Globe, Broadcast, Dna, HardDrives } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";

export function InterfaceSummary() {
  const { activeAssociation } = useScannerStore();

  if (!activeAssociation || activeAssociation.state !== "connected") {
    return null;
  }

  const dnsStr = activeAssociation.dns && activeAssociation.dns.length > 0
    ? activeAssociation.dns.join(", ")
    : "--";

  return (
    <div className="p-3.5 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 space-y-2.5 text-xs animate-fade-in">
      <div className="flex items-center justify-between border-b border-white/10 pb-2">
        <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
          <Network size={14} className="text-[var(--color-signal)]" />
          Konfigurasi Antarmuka LAN
        </span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          Attached Subnet
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2">
        <div className="flex items-center justify-between">
          <span className="text-zinc-500 flex items-center gap-1.5">
            <HardDrives size={13} /> IP Collector:
          </span>
          <span className="font-mono text-zinc-100 font-semibold tabular-nums">
            {activeAssociation.ipv4 || "--"}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-zinc-500 flex items-center gap-1.5">
            <Network size={13} /> Subnet Prefix:
          </span>
          <span className="font-mono text-zinc-300 tabular-nums">
            {activeAssociation.prefix || "--"}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-zinc-500 flex items-center gap-1.5">
            <Broadcast size={13} /> Gateway Router:
          </span>
          <span className="font-mono text-zinc-300 tabular-nums">
            {activeAssociation.gateway || "--"}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-zinc-500 flex items-center gap-1.5">
            <Globe size={13} /> Server DNS:
          </span>
          <span className="font-mono text-zinc-300 truncate max-w-[150px] text-right tabular-nums">
            {dnsStr}
          </span>
        </div>

        {activeAssociation.dhcp_server && (
          <div className="flex items-center justify-between">
            <span className="text-zinc-500 flex items-center gap-1.5">
              <Dna size={13} /> Server DHCP:
            </span>
            <span className="font-mono text-zinc-300 tabular-nums">
              {activeAssociation.dhcp_server}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
