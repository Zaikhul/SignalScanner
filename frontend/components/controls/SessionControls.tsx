"use client";

import React, { useState } from "react";
import { Play, Pause, Stop, BookmarkSimple, CircleNotch, Sparkle, WarningCircle, Cpu, CheckCircle } from "@phosphor-icons/react";
import { apiClient, API_BASE } from "@/lib/apiClient";
import { useScannerStore } from "@/lib/store";

export function SessionControls() {
  const {
    mode,
    selectedCollectorId,
    collectors,
    setCollectors,
    activeSession,
    setActiveSession,
    updateSessionStatus,
    setMarkerModalOpen,
    resetLiveState,
    simulationMode,
  } = useScannerStore();

  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const status = activeSession?.status || "draft";

  const handleStart = async () => {
    setLoading(true);
    setErrorMessage(null);
    setInfoMessage(null);
    resetLiveState();

    try {
      if (simulationMode) {
        // --- 1. SIMULATOR MODE (EXPLICIT) ---
        const session = await apiClient.createSession({
          name: `Simulasi ${mode.toUpperCase()} - ${new Date().toLocaleTimeString()}`,
          mode,
          collector_id: "col_virtual_simulator",
          source_type: "simulator",
          sample_interval_ms: 500,
          tags: [mode, "simulator", "virtual_engine"],
        });

        const started = await apiClient.startSession(session.id);
        setActiveSession(started);

        // Run in-browser simulator explicitly for virtual testing
        startSimulator(started.id, mode);
        setInfoMessage(`Sesi simulasi '${started.id}' aktif.`);
        setTimeout(() => setInfoMessage(null), 6000);
      } else {
        // --- 2. HARDWARE COLLECTOR MODE ---
        // Refresh collector list from API to get accurate online/offline status
        const freshCollectors = await apiClient.listCollectors();
        setCollectors(freshCollectors);

        // Find a collector that is actually alive (status ready or busy)
        const activeCollector = freshCollectors.find(
          (c) => c.status === "ready" || c.status === "busy"
        );

        if (!activeCollector) {
          throw new Error(
            "Collector Hardware tidak terhubung atau offline.\n\n" +
            "Jalankan daemon collector lokal terlebih dahulu:\n" +
            `  python -m collector.app.main --mode ${mode}\n\n` +
            "atau aktifkan toggle 'Mode Simulasi' di panel kiri."
          );
        }

        const collectorId = activeCollector.id;

        const session = await apiClient.createSession({
          name: `Sesi ${mode.toUpperCase()} [Hardware] - ${new Date().toLocaleTimeString()}`,
          mode,
          collector_id: collectorId,
          source_type: "collector",
          sample_interval_ms: 500,
          tags: [mode, "hardware", "native_scan"],
        });

        const started = await apiClient.startSession(session.id);
        setActiveSession(started);

        // Inform user that the backend has dispatched the scan command to the daemon
        setInfoMessage(
          `Sesi '${started.id}' aktif. Perintah scan dikirim ke collector '${collectorId}'.`
        );
        setTimeout(() => setInfoMessage(null), 6000);
      }
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
      const updated = await apiClient.pauseSession(activeSession.id);
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
      const updated = await apiClient.resumeSession(activeSession.id);
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
    stopSimulator();
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
        {/* Source Badge */}
        {simulationMode ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/10 border border-purple-500/30 text-purple-300">
            <Sparkle size={11} />
            SIMULATOR
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
            <Cpu size={11} />
            HARDWARE
          </span>
        )}
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
            <span>Mulai Pemindaian</span>
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

// In-Browser Simulator Engine (Explicit Simulator Mode Only)
let simInterval: any = null;
let simSeq = 0;

function stopSimulator() {
  if (simInterval) {
    clearInterval(simInterval);
    simInterval = null;
  }
}

function startSimulator(sessionId: string, mode: string) {
  stopSimulator();
  simSeq = 0;

  simInterval = setInterval(async () => {
    simSeq++;
    const state = useScannerStore.getState();
    if (!state.activeSession || state.activeSession.status !== "active") {
      stopSimulator();
      return;
    }

    const now = new Date().toISOString();
    let measurements: any[] = [];

    if (mode === "wifi") {
      const aps = [
        { ssid: "Office_HQ_5G", mac: "00:1A:2B:3C:4D:01", ch: 36, band: "5GHz", base: -52 },
        { ssid: "Office_HQ_2.4G", mac: "00:1A:2B:3C:4D:02", ch: 6, band: "2.4GHz", base: -48 },
        { ssid: "Guest_Portal", mac: "00:1A:2B:3C:4D:03", ch: 1, band: "2.4GHz", base: -65 },
        { ssid: "IoT_Mesh_Node_9", mac: "00:1A:2B:3C:4D:04", ch: 11, band: "2.4GHz", base: -74 },
        { ssid: "Lab_WiFi6_AX", mac: "00:1A:2B:3C:4D:07", ch: 149, band: "5GHz", base: -55 },
      ];
      measurements = aps.map((ap) => {
        const drift = 3.5 * Math.sin(simSeq * 0.15 + ap.base);
        const rssi = Math.round((ap.base + drift + (Math.random() * 2 - 1)) * 10) / 10;
        return {
          schema_version: "1.0",
          session_id: sessionId,
          collector_id: "col_virtual_simulator",
          sequence: simSeq,
          captured_at: now,
          mode: "wifi",
          target_id: ap.mac,
          display_name: ap.ssid,
          signal: { value: rssi, unit: "dBm", noise: -94.0 },
          radio: { channel: ap.ch, band: ap.band },
          quality: { calibrated: false, permission_limited: false, throttled: false },
        };
      });
    } else if (mode === "bluetooth") {
      const bles = [
        { name: "iBeacon_Proximity", mac: "C0:EE:40:11:22:01", base: -50, mfg: "Apple Inc." },
        { name: "Nordic_Smart_Tag", mac: "C0:EE:40:11:22:02", base: -62, mfg: "Nordic Semi" },
        { name: "ESP32_Sensor_Node", mac: "C0:EE:40:11:22:03", base: -76, mfg: "Espressif" },
        { name: "BLE_HeartRate_04", mac: "C0:EE:40:11:22:05", base: -68, mfg: "Garmin" },
      ];
      measurements = bles.map((b) => {
        const drift = 4.0 * Math.sin(simSeq * 0.2 + b.base);
        const rssi = Math.round((b.base + drift + (Math.random() * 2 - 1)) * 10) / 10;
        return {
          schema_version: "1.0",
          session_id: sessionId,
          collector_id: "col_virtual_simulator",
          sequence: simSeq,
          captured_at: now,
          mode: "bluetooth",
          target_id: b.mac,
          display_name: b.name,
          signal: { value: rssi, unit: "dBm", noise: -96.0 },
          radio: null,
          quality: { calibrated: false, permission_limited: false, throttled: false },
          extra_metadata: { manufacturer: b.mfg },
        };
      });
    } else {
      // Radio SDR mode
      const bins = Array.from({ length: 256 }, (_, i) => {
        const noise = -92 + (Math.random() * 3 - 1.5);
        if (Math.abs(i - 128) < 3) return -38 + 2 * Math.sin(simSeq * 0.3) - Math.abs(i - 128) * 4;
        if (Math.abs(i - 180) < 2) return -54 - Math.abs(i - 180) * 3;
        return noise;
      });
      measurements = [
        {
          schema_version: "1.0",
          session_id: sessionId,
          collector_id: "col_virtual_simulator",
          sequence: simSeq,
          captured_at: now,
          mode: "radio",
          target_id: "rf_433.92mhz",
          display_name: "RF 433.92 MHz ISM Carrier",
          signal: { value: -38.0, unit: "dBFS", noise: -92.0 },
          radio: {
            center_frequency_hz: 433920000,
            span_hz: 2000000,
            fft_size: 256,
            fft_bins: bins,
          },
          quality: { calibrated: false, permission_limited: false, throttled: false },
        },
      ];
    }

    try {
      await fetch(`${API_BASE}/api/v1/collector-ingest/batches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          schema_version: "1.0",
          session_id: sessionId,
          collector_id: "col_virtual_simulator",
          source_type: "simulator",
          sequence_from: simSeq,
          sequence_to: simSeq,
          measurements,
        }),
      });
    } catch {
      // Ignore if server unreachable
    }
  }, 500);
}
