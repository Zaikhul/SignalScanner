"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/Header";
import { apiClient } from "@/lib/apiClient";
import { ScanMode, ScanSession, SessionStatus } from "@/lib/types";
import { DownloadSimple, ArrowLeft, MagnifyingGlass, Clock, PushPin } from "@phosphor-icons/react";

export default function SessionsHistoryPage() {
  const [sessions, setSessions] = useState<ScanSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [modeFilter, setModeFilter] = useState<ScanMode | "all">("all");
  const [exportingId, setExportingId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await apiClient.listSessions({
          mode: modeFilter === "all" ? undefined : modeFilter,
        });
        setSessions(res.items);
      } catch (e) {
        console.error("Failed to load sessions", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [modeFilter]);

  const handleExport = async (sessionId: string, format: "json" | "csv") => {
    setExportingId(sessionId);
    try {
      const exp = await apiClient.createExport(sessionId, format);
      // Trigger authenticated download
      await apiClient.downloadExportFile(exp.id);
    } catch (e) {
      console.error("Failed to export session", e);
    } finally {
      setExportingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <Header />

      <main className="flex-1 max-w-6xl w-full mx-auto p-4 lg:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Link
                href="/"
                className="text-xs text-zinc-400 hover:text-zinc-100 flex items-center gap-1 transition"
              >
                <ArrowLeft size={14} />
                Kembali ke Live Scan
              </Link>
            </div>
            <h1 className="text-lg font-semibold text-zinc-100">Riwayat Sesi Pemindaian</h1>
            <p className="text-xs text-zinc-400">
              Audit log pengukuran tersimpan, ringkasan sinyal, dan ekspor dataset
            </p>
          </div>

          {/* Mode Filters */}
          <div className="flex items-center gap-1 p-1 rounded-lg bg-[var(--color-surface)] border border-white/10 text-xs">
            {(["all", "wifi", "bluetooth", "radio"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setModeFilter(m)}
                className={`px-3 py-1.5 rounded-[var(--radius-control)] capitalize font-medium transition ${
                  modeFilter === m
                    ? "bg-[var(--color-signal)] text-zinc-950"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {m === "all" ? "Semua Mode" : m}
              </button>
            ))}
          </div>
        </div>

        {/* Sessions List */}
        {loading ? (
          <div className="text-center py-16 text-xs text-zinc-500">Memuat riwayat sesi...</div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-16 text-xs text-zinc-500 border border-dashed border-white/10 rounded-[var(--radius-panel)] p-8">
            Belum ada sesi pemindaian yang tersimpan untuk filter ini.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {sessions.map((s) => (
              <div
                key={s.id}
                className="p-4 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] flex flex-col md:flex-row md:items-center justify-between gap-4 hover:border-white/20 transition"
              >
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-zinc-100 truncate">{s.name}</span>
                    <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-raised)] border border-white/10 text-zinc-300">
                      {s.mode}
                    </span>
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                        s.status === "completed"
                          ? "bg-[var(--color-signal)]/10 text-[var(--color-signal)] border border-[var(--color-signal)]/30"
                          : "bg-zinc-800 text-zinc-400"
                      }`}
                    >
                      {s.status}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-400 font-mono">
                    <span>ID: {s.id}</span>
                    <span>•</span>
                    <span>Waktu: {new Date(s.created_at).toLocaleString()}</span>
                    {s.summary && (
                      <>
                        <span>•</span>
                        <span>Sampel: {s.summary.total_samples} frames</span>
                        <span>•</span>
                        <span>Target: {s.summary.unique_targets} emitters</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Export & Action Buttons */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    disabled={exportingId === s.id}
                    onClick={() => handleExport(s.id, "json")}
                    className="px-3 py-1.5 rounded-[var(--radius-control)] border border-white/10 bg-white/5 text-xs text-zinc-200 hover:bg-white/10 transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <DownloadSimple size={14} />
                    JSON
                  </button>
                  <button
                    type="button"
                    disabled={exportingId === s.id}
                    onClick={() => handleExport(s.id, "csv")}
                    className="px-3 py-1.5 rounded-[var(--radius-control)] border border-white/10 bg-white/5 text-xs text-zinc-200 hover:bg-white/10 transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    <DownloadSimple size={14} />
                    CSV
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
