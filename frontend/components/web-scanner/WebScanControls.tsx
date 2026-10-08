"use client";

import React, { useEffect, useState } from "react";
import { Play, Stop, Sliders, Warning, Info, CircleNotch } from "@phosphor-icons/react";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { useWebScanStore } from "@/lib/webScanStore";
import { Capabilities, ProfileId, ScanConfiguration } from "@/lib/webScanTypes";

export function WebScanControls() {
  const { isScanning, activeJob, setActiveJob, setError, reset } = useWebScanStore();

  const [target, setTarget] = useState("");
  const [profile, setProfile] = useState<ProfileId>("v2");
  const [authAcknowledged, setAuthAcknowledged] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [allowPrivate, setAllowPrivate] = useState(false);
  const [timeoutSec, setTimeoutSec] = useState(600);
  const [maxConcurrency, setMaxConcurrency] = useState(100);
  const [rps, setRps] = useState(50);
  const [maxRequests, setMaxRequests] = useState(10000);
  const [submitting, setSubmitting] = useState(false);

  // Server capabilities state
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capsLoading, setCapsLoading] = useState(true);
  const [capsError, setCapsError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    webScanApiClient
      .getCapabilities()
      .then((caps) => {
        if (!mounted) return;
        setCapabilities(caps);
        setCapsLoading(false);
        if (caps.defaults) {
          if (caps.defaults.timeout_seconds) setTimeoutSec(caps.defaults.timeout_seconds);
          if (caps.defaults.max_concurrency) setMaxConcurrency(caps.defaults.max_concurrency);
          if (caps.defaults.requests_per_second) setRps(caps.defaults.requests_per_second);
          if (caps.defaults.max_requests) setMaxRequests(caps.defaults.max_requests);
        }
      })
      .catch((err) => {
        if (!mounted) return;
        setCapsError(err.message || "Gagal memuat kapabilitas server scanner");
        setCapsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  async function handleStartScan(e: React.FormEvent) {
    e.preventDefault();
    if (!target.trim() || !authAcknowledged) return;

    setSubmitting(true);
    setError(null);
    reset();

    const config: Partial<ScanConfiguration> = {
      profile,
      timeout_seconds: timeoutSec,
      allow_private: allowPrivate,
      allow_loopback: allowPrivate,
      max_concurrency: maxConcurrency,
      requests_per_second: rps,
      max_requests: maxRequests,
    };

    try {
      const job = await webScanApiClient.createScan({
        target: target.trim(),
        configuration: config as any,
        authorization_acknowledged: true,
      });

      setActiveJob(job);
    } catch (err: any) {
      setError(err.message || "Failed to initiate web scan");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCancelScan() {
    if (!activeJob) return;
    try {
      const cancelledJob = await webScanApiClient.cancelScan(activeJob.id);
      setActiveJob(cancelledJob);
    } catch (err: any) {
      setError(err.message || "Failed to cancel web scan");
    }
  }

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg p-5 mb-6 shadow-sm">
      {/* Capabilities Notice Banner */}
      {capsLoading && (
        <div className="mb-4 p-2.5 rounded bg-zinc-950 border border-white/5 flex items-center gap-2 text-xs text-zinc-400">
          <CircleNotch size={14} className="animate-spin text-blue-400" />
          <span>Memuat konfigurasi kapabilitas server pemindai...</span>
        </div>
      )}

      {capsError && (
        <div className="mb-4 p-2.5 rounded bg-amber-950/30 border border-amber-500/20 flex items-center gap-2 text-xs text-amber-300">
          <Warning size={14} className="shrink-0 text-amber-400" />
          <span>
            Peringatan: Gagal memuat kapabilitas backend ({capsError}). Parameter standar lokal diterapkan.
          </span>
        </div>
      )}

      <form onSubmit={handleStartScan} className="space-y-4">
        {/* Main Input Row */}
        <div className="flex flex-col md:flex-row gap-3">
          <div className="flex-1">
            <label className="block text-xs font-medium text-zinc-300 mb-1.5">
              Target URL / Hostname
            </label>
            <input
              type="text"
              placeholder="e.g. https://example.com or http://target-app.internal"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              disabled={isScanning || submitting}
              className="w-full bg-zinc-950 border border-white/10 rounded-md px-3.5 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
            />
          </div>

          <div className="w-full md:w-64">
            <label className="block text-xs font-medium text-zinc-300 mb-1.5">Profil Pemindaian</label>
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value as ProfileId)}
              disabled={isScanning || submitting}
              className="w-full bg-zinc-950 border border-white/10 rounded-md px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-blue-500 disabled:opacity-50"
            >
              <option value="v2">v2 (Recon + 6 Headers + Cookies + Probes)</option>
              <option value="legacy_v47">legacy_v47 (V47 Heuristics & Stress)</option>
              <option value="legacy_v75">legacy_v75 (V75 14 Weights Audit)</option>
              <option value="comprehensive">Comprehensive (Semua 7 Modul)</option>
            </select>
          </div>

          <div className="flex items-end gap-2">
            {!isScanning ? (
              <button
                type="submit"
                disabled={!target.trim() || !authAcknowledged || submitting}
                className="w-full md:w-auto px-5 py-2 rounded-md bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white font-medium text-sm flex items-center justify-center gap-2 transition"
              >
                <Play size={16} weight="fill" />
                <span>{submitting ? "Memulai..." : "Mulai Audit"}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={handleCancelScan}
                className="w-full md:w-auto px-5 py-2 rounded-md bg-red-600 hover:bg-red-500 text-white font-medium text-sm flex items-center justify-center gap-2 transition"
              >
                <Stop size={16} weight="fill" />
                <span>Batalkan Audit</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              aria-label="Tampilkan atau sembunyikan konfigurasi parameter lanjutan"
              aria-expanded={showAdvanced}
              className={`p-2 rounded-md border text-xs transition ${
                showAdvanced
                  ? "bg-zinc-800 border-zinc-600 text-zinc-200"
                  : "bg-zinc-950 border-white/10 text-zinc-400 hover:text-zinc-200"
              }`}
              title="Atur Parameter Lanjutan"
            >
              <Sliders size={18} />
            </button>
          </div>
        </div>

        {/* Authorization checkbox (strict PRD requirement) */}
        <div className="flex items-start gap-2.5 pt-1">
          <input
            type="checkbox"
            id="auth-ack"
            checked={authAcknowledged}
            onChange={(e) => setAuthAcknowledged(e.target.checked)}
            disabled={isScanning || submitting}
            className="mt-0.5 rounded border-zinc-700 bg-zinc-950 text-blue-600 focus:ring-blue-500"
          />
          <label htmlFor="auth-ack" className="text-xs text-zinc-400 leading-relaxed cursor-pointer select-none">
            <span className="text-zinc-200 font-medium">Persetujuan Rules of Engagement: </span>
            Saya menyatakan secara sah memiliki otorisasi tertulis untuk melakukan uji keamanan diagnostik pada target ini. Seluruh stimulus dilakukan secara non-destruktif dan terkendali.
          </label>
        </div>

        {/* Effective Budget Information */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-[11px] font-mono text-zinc-400">
          <span className="flex items-center gap-1">
            <Info size={13} className="text-blue-400" />
            <span>Budget Efektif:</span>
          </span>
          <span>Batas: {maxRequests.toLocaleString()} req</span>
          <span className="text-zinc-600">•</span>
          <span>Kecepatan: {rps} req/dtk</span>
          <span className="text-zinc-600">•</span>
          <span>Konkurensi: {maxConcurrency}</span>
          <span className="text-zinc-600">•</span>
          <span>Batas Waktu: {timeoutSec}s</span>
        </div>

        {/* Advanced Configuration Accordion */}
        {showAdvanced && (
          <div className="pt-3 border-t border-white/5 grid grid-cols-1 sm:grid-cols-5 gap-4 text-xs">
            <div>
              <label className="block text-zinc-400 mb-1">Timeout (detik)</label>
              <input
                type="number"
                min="1"
                max={capabilities?.hard_caps?.max_timeout_seconds || 3600}
                value={timeoutSec}
                onChange={(e) => setTimeoutSec(Number(e.target.value))}
                disabled={isScanning}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-zinc-400 mb-1">Maks. Konkurensi</label>
              <input
                type="number"
                min="1"
                max={capabilities?.hard_caps?.max_concurrency || 500}
                value={maxConcurrency}
                onChange={(e) => setMaxConcurrency(Number(e.target.value))}
                disabled={isScanning}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-zinc-400 mb-1">Rate Limit (req/dtk)</label>
              <input
                type="number"
                min="1"
                max={capabilities?.hard_caps?.max_requests_per_second || 200}
                step="1"
                value={rps}
                onChange={(e) => setRps(Number(e.target.value))}
                disabled={isScanning}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-zinc-400 mb-1">Maks. Permintaan (Budget)</label>
              <input
                type="number"
                min="10"
                max={capabilities?.hard_caps?.max_requests_budget || 100000}
                step="500"
                value={maxRequests}
                onChange={(e) => setMaxRequests(Number(e.target.value))}
                disabled={isScanning}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="flex items-center gap-2 pt-4">
              <input
                type="checkbox"
                id="allow-private"
                checked={allowPrivate}
                onChange={(e) => setAllowPrivate(e.target.checked)}
                disabled={isScanning}
                className="rounded border-zinc-700 bg-zinc-950 text-blue-600 focus:ring-blue-500"
              />
              <label htmlFor="allow-private" className="text-zinc-400 cursor-pointer">
                Izinkan IP Privat (RFC 1918)
              </label>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
