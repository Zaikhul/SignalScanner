"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Broadcast,
  Clock,
  ShieldCheck,
  HardDrives,
  ListChecks,
  Sparkle,
  List,
  X,
} from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";

export function Header() {
  const pathname = usePathname();
  const { activeSession, connectionState } = useScannerStore();
  const [elapsed, setElapsed] = useState<string>("00:00:00");
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);

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

  const navItems = [
    { href: "/", label: "Live Scan", icon: Broadcast },
    { href: "/channel-health", label: "Channel Health", icon: Sparkle },
    { href: "/sessions", label: "Riwayat Sesi", icon: ListChecks },
    { href: "/collectors", label: "Collector", icon: HardDrives },
    { href: "/web-scanner", label: "Web Scanner", icon: ShieldCheck },
  ];

  const isLinkActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname.startsWith(href);
  };

  const isWebScanner = pathname.startsWith("/web-scanner");

  return (
    <header className="relative border-b border-white/10 bg-zinc-950 px-4 lg:px-6 z-20">
      <div className="h-14 flex items-center justify-between">
        {/* Brand & System Title */}
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)]">
            <Broadcast size={18} weight="bold" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold tracking-tight text-sm text-zinc-100">
                SignalScanner
              </span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-raised)] border border-white/10 text-[var(--color-signal)] font-semibold">
                v1.2
              </span>
            </div>
            <span className="text-[11px] text-zinc-400 block -mt-0.5">
              Sistem Pengukuran Sinyal & Pemindaian Web
            </span>
          </div>
        </div>

        {/* Desktop Navigation links */}
        <nav className="hidden md:flex items-center gap-1 text-xs" aria-label="Navigasi Utama">
          {navItems.map((item) => {
            const active = isLinkActive(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`px-3 py-1.5 rounded-[var(--radius-control)] transition flex items-center gap-1.5 border ${
                  active
                    ? "bg-white/10 text-zinc-100 font-medium border-white/10 shadow-xs"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-white/5 border-transparent"
                }`}
              >
                <Icon
                  size={14}
                  className={active ? "text-[var(--color-signal)]" : undefined}
                />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Live Status, Source Badge & Clock */}
        <div className="flex items-center gap-2">
          {activeSession && (
            <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-control)] border border-emerald-500/30 bg-emerald-950/40 text-[11px] font-mono text-emerald-300">
              HARDWARE: {activeSession.collector_id}
            </div>
          )}

          {activeSession && (
            <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 text-xs">
              <Clock size={14} className="text-zinc-400" />
              <span className="font-mono tabular-nums text-zinc-200">{elapsed}</span>
            </div>
          )}

          {/* Connection status indicator with clear origin differentiation */}
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--radius-control)] bg-[var(--color-surface)] border border-white/10 text-xs"
            title={
              isWebScanner
                ? "Status koneksi RF hardware (modul live scan)"
                : "Status koneksi sinyal RF"
            }
          >
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
              {isWebScanner
                ? `RF: ${connectionState === "connected" ? "Ready" : connectionState}`
                : connectionState === "connected"
                ? "Live Stream"
                : connectionState}
            </span>
          </div>

          {/* Mobile Menu Toggle Button */}
          <button
            onClick={() => setMobileMenuOpen((o) => !o)}
            aria-label={mobileMenuOpen ? "Tutup menu navigasi" : "Buka menu navigasi"}
            aria-expanded={mobileMenuOpen}
            className="md:hidden p-1.5 rounded-lg bg-zinc-900 border border-white/10 text-zinc-300 hover:text-white hover:bg-zinc-800 transition focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {mobileMenuOpen ? <X size={18} /> : <List size={18} />}
          </button>
        </div>
      </div>

      {/* Mobile Navigation Dropdown */}
      {mobileMenuOpen && (
        <nav
          aria-label="Navigasi Seluler"
          className="md:hidden py-3 border-t border-white/5 space-y-1 text-xs"
        >
          {navItems.map((item) => {
            const active = isLinkActive(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-md transition ${
                  active
                    ? "bg-white/10 text-zinc-100 font-medium border border-white/10"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
                }`}
              >
                <Icon
                  size={16}
                  className={active ? "text-[var(--color-signal)]" : undefined}
                />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      )}
    </header>
  );
}
