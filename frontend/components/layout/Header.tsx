"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Broadcast, Clock, ShieldCheck, HardDrives, ListChecks, Gear, Sparkle } from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";

export function Header() {
  const { activeSession, connectionState } = useScannerStore();
  const [elapsed, setElapsed] = useState<string>("00:00:00");

  useEffect(() => {
    if (!activeSession || activeSession.status !== "active" || !activeSession.started_at) {
      return;
    }

    const startTs = new Date(activeSession.started_at).getTime();
    const interval = setInterval(() => {
      const diff = Math.max(0, Math.floor((Date.now() - startTs) / 1000));
      const hrs = String(Math.floor(diff / 3600)).padStart(2, "0");
      const mins = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
      const secs = String(diff % 60).padStart(2, "0");
      setElapsed(`${hrs}:${mins}:${secs}`);
    }, 1000);

    return () => clearInterval(interval);
  }, [activeSession]);

  return (
    <header className="h-14 border-b border-white/10 bg-zinc-950 px-4 lg:px-6 flex items-center justify-between z-20">
      {/* Brand & System Title */}
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)]">
          <Broadcast size={18} weight="bold" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold tracking-tight text-sm text-zinc-100">Pemindai Area</span>
            <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)] font-semibold">
              v1.2
            </span>
          </div>
          <span className="text-[11px] text-zinc-400 block -mt-0.5">Sistem Pengukuran Kekuatan Sinyal Multi-Mode</span>
        </div>
      </div>

      {/* Navigation links */}
      <nav className="hidden md:flex items-center gap-1 text-xs">
        <Link
          href="/"
          className="px-3 py-1.5 rounded-[var(--radius-control)] text-zinc-400 hover:text-zinc-200 hover:bg-white/5 transition flex items-center gap-1.5"
        >
          <Broadcast size={14} />
          Live Scan
        </Link>
        <Link
          href="/channel-health"
          className="px-3 py-1.5 rounded-[var(--radius-control)] bg-white/5 text-zinc-100 font-medium border border-white/10 flex items-center gap-1.5"
        >
          <Sparkle size={14} className="text-[var(--color-signal)]" />
          Channel Health
        </Link>
        <Link
          href="/sessions"
          className="px-3 py-1.5 rounded-[var(--radius-control)] text-zinc-400 hover:text-zinc-200 hover:bg-white/5 transition flex items-center gap-1.5"
        >
          <ListChecks size={14} />
          Riwayat Sesi
        </Link>
        <Link
          href="/collectors"
          className="px-3 py-1.5 rounded-[var(--radius-control)] text-zinc-400 hover:text-zinc-200 hover:bg-white/5 transition flex items-center gap-1.5"
        >
          <HardDrives size={14} />
          Collector
        </Link>
      </nav>

      {/* Live Status, Source Badge & Clock */}
      <div className="flex items-center gap-2.5">
        {activeSession && (
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-control)] border text-[11px] font-mono">
            {activeSession.source_type === "simulator" ? (
              <span className="text-purple-300 bg-purple-950/40 border border-purple-500/30 px-2 py-0.5 rounded">
                SIMULATOR
              </span>
            ) : (
              <span className="text-emerald-300 bg-emerald-950/40 border border-emerald-500/30 px-2 py-0.5 rounded">
                HARDWARE: {activeSession.collector_id}
              </span>
            )}
          </div>
        )}

        {activeSession && (
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 text-xs">
            <Clock size={14} className="text-zinc-400" />
            <span className="font-mono tabular-nums text-zinc-200">{elapsed}</span>
          </div>
        )}

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              connectionState === "connected"
                ? "bg-[var(--color-signal)]"
                : connectionState === "reconnecting"
                ? "bg-amber-400 animate-pulse"
                : "bg-zinc-600"
            }`}
          />
          <span className="text-[11px] font-mono text-zinc-300 capitalize">
            {connectionState === "connected" ? "Live Stream" : connectionState}
          </span>
        </div>
      </div>
    </header>
  );
}
