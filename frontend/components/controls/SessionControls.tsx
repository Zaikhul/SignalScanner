"use client";

import React, { useState } from "react";
import {
  Play,
  Pause,
  Stop,
  BookmarkSimple,
  CircleNotch,
  WarningCircle,
  Cpu,
  CheckCircle,
  Copy,
  X,
} from "@phosphor-icons/react";
import { apiClient } from "@/lib/apiClient";
import { useScannerStore } from "@/lib/store";

export function SessionControls() {
  const {
    mode,
    selectedCollectorId,
    setSelectedCollectorId,
    collectors,
    setCollectors,
    activeSession,
    setActiveSession,
    updateSessionStatus,
    setMarkerModalOpen,
    resetLiveState,
  } = useScannerStore();

  const [loading, setLoading] = useState(false);
  const [spawningDaemon, setSpawningDaemon] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [collectorPrompt, setCollectorPrompt] = useState<{
    collectorName: string;
    mode: string;
  } | null>(null);
  const status = activeSession?.status || "draft";

  const handleSpawnDaemon = async () => {
    setSpawningDaemon(true);
    setErrorMessage(null);
    try {
      const res = await apiClient.spawnLocalDaemon("col_default", mode);
      setInfoMessage(res.message || "Daemon collector lokal berhasil dijalankan!");

      // Wait 1.5s for daemon to register and send initial heartbeat
      setTimeout(async () => {
        try {
          const fresh = await apiClient.listCollectors();
          setCollectors(fresh);
          const found = fresh.find((c) => c.id === "col_default");
          if (found && found.status !== "offline") {
            setCollectorPrompt(null);
          }
        } catch {}
      }, 1500);
    } catch (e: any) {
      setErrorMessage(e.message || "Gagal menyalakan daemon collector lokal.");
    } finally {
      setSpawningDaemon(false);
    }
  };

  const handleStart = async () => {
    setErrorMessage(null);
    setInfoMessage(null);
    setCollectorPrompt(null);
    setLoading(true);
    resetLiveState();

    try {
      // --- HARDWARE COLLECTOR REAL MEASUREMENT ---
      // Refresh collector list from API to get accurate online/offline status
      const freshCollectors = await apiClient.listCollectors();
      setCollectors(freshCollectors);

      // Dedicated Local Host Collector resolution
      const localCollector =
        freshCollectors.find((c) => c.id === "col_default") || freshCollectors[0];

      if (!localCollector || localCollector.status === "offline") {
        setCollectorPrompt({
          collectorName: localCollector?.name || "Local Host Collector",
          mode,
        });
        setLoading(false);
        return;
      }

      const session = await apiClient.createSession({
        name: `Sesi ${mode.toUpperCase()} [Hardware] - ${new Date().toLocaleTimeString()}`,
        mode,
        collector_id: "col_default",
        source_type: "collector",
        sample_interval_ms: 500,
        tags: [mode, "hardware", "native_scan"],
      });

      const started = await apiClient.startSession(session.id);
      setActiveSession(started);

      setInfoMessage(
        `Sesi pemindaian real '${started.id}' aktif. Perintah dikirim ke Local Host Collector.`
      );
      setTimeout(() => setInfoMessage(null), 6000);
    } catch (e: any) {
      console.error("Failed to start scan", e);
      setErrorMessage(e.message || "Gagal memulai pemindaian.");
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    if (!activeSession) return;
    setLoading(true);
    try {
      await apiClient.pauseSession(activeSession.id);
      updateSessionStatus("paused");
    } catch (e: any) {
      console.error("Failed to pause scan", e);
      setErrorMessage(e.message || "Gagal menjeda sesi.");
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async () => {
    if (!activeSession) return;
    setLoading(true);
    try {
      await apiClient.resumeSession(activeSession.id);
      updateSessionStatus("active");
    } catch (e: any) {
      console.error("Failed to resume scan", e);
      setErrorMessage(e.message || "Gagal melanjutkan sesi.");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    if (!activeSession) return;
    setLoading(true);
    try {
      const updated = await apiClient.stopSession(activeSession.id);
      setActiveSession(updated);
      setInfoMessage(`Sesi '${activeSession.id}' selesai.`);
      setTimeout(() => setInfoMessage(null), 4000);
    } catch (e: any) {
      console.error("Failed to stop scan", e);
      setErrorMessage(e.message || "Gagal menghentikan sesi.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider block">
          Kontrol Sesi
        </label>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
          <Cpu size={11} />
          PENGUKURAN REAL
        </span>
      </div>

      {/* Info Banner (Green/Emerald) */}
      {infoMessage && (
        <div className="p-3 rounded-[var(--radius-control)] bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 text-xs flex items-start gap-2 animate-fadeIn">
          <CheckCircle size={16} className="shrink-0 mt-0.5 text-emerald-400" weight="fill" />
          <div className="flex-1">
            <p className="font-mono text-[11px] whitespace-pre-wrap break-words">{infoMessage}</p>
          </div>
        </div>
      )}

      {/* Error Banner (Red/Rose) */}
      {errorMessage && (
        <div className="p-3 rounded-[var(--radius-control)] bg-rose-950/40 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
          <WarningCircle size={16} className="shrink-0 mt-0.5 text-rose-400" />
          <div className="flex-1">
            <pre className="font-mono text-[11px] whitespace-pre-wrap break-words">{errorMessage}</pre>
          </div>
        </div>
      )}

      {/* Collector Offline Banner with 1-Click Daemon Spawn */}
      {collectorPrompt && (
        <div className="p-3.5 rounded-[var(--radius-control)] bg-amber-500/10 border border-amber-500/25 space-y-2.5 text-xs animate-fadeIn">
          <div className="flex items-start gap-2.5 text-amber-300">
            <WarningCircle size={18} className="shrink-0 mt-0.5 text-amber-400" />
            <div className="space-y-1">
              <p className="font-semibold text-zinc-100">
                Daemon Hardware Belum Aktif
              </p>
              <p className="text-[11px] text-zinc-300 leading-relaxed">
                Kolektor &quot;{collectorPrompt.collectorName}&quot; belum terdeteksi aktif di sistem. Nyalakan daemon hardware untuk melakukan pemindaian nyata dengan pengukuran gelombang sinyal aktual.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              disabled={spawningDaemon}
              onClick={handleSpawnDaemon}
              className="px-3 py-1.5 rounded-[var(--radius-control)] bg-[var(--color-signal)] text-zinc-950 font-semibold text-xs flex items-center gap-1.5 hover:opacity-90 transition cursor-pointer disabled:opacity-50"
            >
              {spawningDaemon ? (
                <CircleNotch size={14} className="animate-spin" />
              ) : (
                <Play size={14} weight="fill" />
              )}
              <span>Nyalakan Daemon Lokal (1-Click)</span>
            </button>

            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(`python -m collector.app.main --mode ${collectorPrompt.mode}`);
                setInfoMessage("Perintah daemon CLI disalin ke clipboard!");
                setTimeout(() => setInfoMessage(null), 3000);
              }}
              className="px-2.5 py-1.5 rounded-[var(--radius-control)] border border-white/10 hover:bg-white/5 text-zinc-300 text-xs flex items-center gap-1.5 transition cursor-pointer"
              title="Salin perintah untuk menjalankan collector daemon secara manual"
            >
              <Copy size={13} />
              <span>Salin Perintah CLI</span>
            </button>

            <button
              type="button"
              onClick={() => setCollectorPrompt(null)}
              className="p-1 ml-auto text-zinc-400 hover:text-zinc-200 transition cursor-pointer"
              title="Tutup pesan"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {status === "draft" || status === "completed" || status === "stopped" ? (
          <button
            type="button"
            disabled={loading}
            onClick={handleStart}
            className="w-full min-h-11 inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] bg-[var(--color-signal)] px-4 font-semibold text-zinc-950 transition active:scale-[0.98] hover:opacity-95 cursor-pointer disabled:opacity-50"
          >
            {loading ? (
              <CircleNotch size={18} className="animate-spin" />
            ) : (
              <Play size={18} weight="fill" />
            )}
            <span>Mulai Pemindaian Real</span>
          </button>
        ) : status === "active" ? (
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={loading}
              onClick={handlePause}
              className="min-h-11 inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] border border-white/15 bg-[var(--color-surface)] px-3 text-xs font-medium text-zinc-200 hover:bg-white/5 transition active:scale-[0.98] cursor-pointer"
            >
              <Pause size={16} weight="fill" />
              <span>Jeda</span>
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={handleStop}
              className="min-h-11 inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] border border-rose-500/40 bg-rose-500/10 px-3 text-xs font-medium text-rose-300 hover:bg-rose-500/20 transition active:scale-[0.98] cursor-pointer"
            >
              <Stop size={16} weight="fill" />
              <span>Selesai</span>
            </button>
          </div>
        ) : status === "paused" ? (
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={loading}
              onClick={handleResume}
              className="min-h-11 inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] bg-[var(--color-signal)] px-3 text-xs font-semibold text-zinc-950 transition active:scale-[0.98] cursor-pointer"
            >
              <Play size={16} weight="fill" />
              <span>Lanjut</span>
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={handleStop}
              className="min-h-11 inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] border border-rose-500/40 bg-rose-500/10 px-3 text-xs font-medium text-rose-300 hover:bg-rose-500/20 transition active:scale-[0.98] cursor-pointer"
            >
              <Stop size={16} weight="fill" />
              <span>Selesai</span>
            </button>
          </div>
        ) : null}

        {/* Add Marker Button */}
        {status === "active" && (
          <button
            type="button"
            onClick={() => setMarkerModalOpen(true)}
            className="w-full py-2.5 inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] border border-white/10 bg-white/5 text-xs text-zinc-300 hover:text-zinc-100 hover:bg-white/10 transition cursor-pointer"
          >
            <BookmarkSimple size={15} />
            <span>Tambah Marker Kejadian</span>
          </button>
        )}

        {/* Diagnostics & Provenance Action Buttons */}
        <div className="grid grid-cols-2 gap-2 pt-1">
          <button
            type="button"
            onClick={() => useScannerStore.getState().setPreflightModalOpen(true)}
            className="py-2 inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-control)] border border-cyan-500/30 bg-cyan-500/10 text-[11px] font-medium text-cyan-300 hover:bg-cyan-500/20 transition cursor-pointer"
          >
            <span>Uji Preflight</span>
          </button>

          <button
            type="button"
            onClick={() => useScannerStore.getState().setProvenanceModalOpen(true)}
            className="py-2 inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-control)] border border-emerald-500/30 bg-emerald-500/10 text-[11px] font-medium text-emerald-300 hover:bg-emerald-500/20 transition cursor-pointer"
          >
            <span>Manifest Sesi</span>
          </button>
        </div>
      </div>
    </div>
  );
}
