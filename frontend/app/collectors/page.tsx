"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/Header";
import { apiClient } from "@/lib/apiClient";
import { Collector } from "@/lib/types";
import { ArrowLeft, HardDrives, CheckCircle, Wrench, ShieldCheck, Cpu } from "@phosphor-icons/react";

export default function CollectorsPage() {
  const [collectors, setCollectors] = useState<Collector[]>([]);
  const [loading, setLoading] = useState(true);
  const [diagResult, setDiagResult] = useState<any | null>(null);
  const [runningDiag, setRunningDiag] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const list = await apiClient.listCollectors();
        setCollectors(list);
      } catch (e) {
        console.error("Failed to load collectors", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleRunDiagnostics = async (collectorId: string) => {
    setRunningDiag(true);
    setDiagResult(null);
    try {
      const res = await apiClient.runDiagnostic(collectorId);
      setDiagResult(res);
    } catch (e: any) {
      setDiagResult({ error: e.message || "Failed to run diagnostics" });
    } finally {
      setRunningDiag(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <Header />

      <main className="flex-1 max-w-5xl w-full mx-auto p-4 lg:p-8 space-y-6">
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
            <h1 className="text-lg font-semibold text-zinc-100">Status Collector & Adapter</h1>
            <p className="text-xs text-zinc-400">
              Inventaris daemon lokal, izin akses radio, dan modul diagnostik adapter
            </p>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-16 text-xs text-zinc-500">Memuat status collector...</div>
        ) : (
          <div className="space-y-6">
            {collectors.length === 0 ? (
              <div className="p-6 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] text-center text-xs text-zinc-400 space-y-2">
                <p>Belum ada collector terdaftar. Jalankan daemon collector pada host lokal.</p>
                <code className="text-[11px] font-mono text-[var(--color-signal)] bg-zinc-900 px-3 py-1.5 rounded block max-w-md mx-auto">
                  python -m collector.app.main --mode wifi
                </code>
              </div>
            ) : (
              collectors.map((c) => (
                <div
                  key={c.id}
                  className="p-5 rounded-[var(--radius-panel)] border border-white/10 bg-[var(--color-surface)] space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-[var(--color-surface-raised)] border border-white/10 flex items-center justify-center text-[var(--color-signal)]">
                        <HardDrives size={20} />
                      </div>
                      <div>
                        <h3 className="font-semibold text-sm text-zinc-100">{c.name}</h3>
                        <span className="text-[11px] font-mono text-zinc-500">
                          ID: {c.id} | Platform: {c.platform}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-[var(--radius-control)] bg-[var(--color-signal)]/10 text-[var(--color-signal)] border border-[var(--color-signal)]/30 text-xs">
                        <CheckCircle size={13} weight="fill" />
                        <span>Ready</span>
                      </span>
                      <button
                        type="button"
                        disabled={runningDiag}
                        onClick={() => handleRunDiagnostics(c.id)}
                        className="px-3 py-1.5 rounded-[var(--radius-control)] bg-white/5 border border-white/10 text-xs text-zinc-200 hover:bg-white/10 transition flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                      >
                        <Wrench size={14} />
                        <span>{runningDiag ? "Memeriksa..." : "Uji Diagnostik"}</span>
                      </button>
                    </div>
                  </div>

                  {/* Capabilities breakdown */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                    <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface-raised)] border border-white/5 space-y-1">
                      <div className="flex items-center gap-1.5 text-zinc-300 font-medium">
                        <Cpu size={14} />
                        <span>Adapter WiFi Native</span>
                      </div>
                      <p className="text-[11px] text-zinc-500">
                        {c.capabilities.can_wifi ? "Didukung (WlanScan / Netsh)" : "Tidak Tersedia"}
                      </p>
                    </div>

                    <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface-raised)] border border-white/5 space-y-1">
                      <div className="flex items-center gap-1.5 text-zinc-300 font-medium">
                        <ShieldCheck size={14} />
                        <span>Adapter Bluetooth LE</span>
                      </div>
                      <p className="text-[11px] text-zinc-500">
                        {c.capabilities.can_ble ? "Didukung (Bleak Async Scanner)" : "Tidak Tersedia"}
                      </p>
                    </div>

                    <div className="p-3 rounded-[var(--radius-control)] bg-[var(--color-surface-raised)] border border-white/5 space-y-1">
                      <div className="flex items-center gap-1.5 text-zinc-300 font-medium">
                        <HardDrives size={14} />
                        <span>Radio SDR Spektrum</span>
                      </div>
                      <p className="text-[11px] text-zinc-500">
                        {c.capabilities.can_sdr ? "SoapySDR / Virtual Simulator" : "Mock Fallback"}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}

            {/* Diagnostics Output */}
            {diagResult && (
              <div className="p-5 rounded-[var(--radius-panel)] border border-[var(--color-signal)]/30 bg-[var(--color-surface)] space-y-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-[var(--color-signal)]">
                  <CheckCircle size={16} />
                  <span>Hasil Diagnostik Hardware & Izin Sistem</span>
                </div>
                <pre className="p-3 rounded-lg bg-zinc-950 border border-white/10 font-mono text-[11px] text-zinc-300 overflow-x-auto">
                  {JSON.stringify(diagResult, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
