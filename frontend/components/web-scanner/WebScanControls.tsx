"use client";

import React, { useState } from "react";
import { Play, Stop, ShieldWarning, Sliders } from "@phosphor-icons/react";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { useWebScanStore } from "@/lib/webScanStore";
import { ProfileId, ScanConfiguration } from "@/lib/webScanTypes";

export function WebScanControls() {
  const { isScanning, activeJob, setActiveJob, setSnapshot, setError, reset } = useWebScanStore();

  const [target, setTarget] = useState("");
  const [profile, setProfile] = useState<ProfileId>("v2");
  const [authAcknowledged, setAuthAcknowledged] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [allowPrivate, setAllowPrivate] = useState(false);
  const [timeoutSec, setTimeoutSec] = useState(600);
  const [maxConcurrency, setMaxConcurrency] = useState(10000);
  const [rps, setRps] = useState(1000.0);
  const [submitting, setSubmitting] = useState(false);

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
      max_concurrency: maxConcurrency,
      requests_per_second: rps,
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

          <div className="w-full md:w-56">
            <label className="block text-xs font-medium text-zinc-300 mb-1.5">Scan Profile</label>
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value as ProfileId)}
              disabled={isScanning || submitting}
              className="w-full bg-zinc-950 border border-white/10 rounded-md px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-blue-500 disabled:opacity-50"
            >
              <option value="v2">v2 (Recon + 6 Headers + Cookies + Probes)</option>
              <option value="legacy_v47">legacy_v47 (V47 Heuristics & Stress)</option>
              <option value="legacy_v75">legacy_v75 (V75 14 Weights Audit)</option>
              <option value="comprehensive">Comprehensive (All 7 Modules)</option>
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
                <span>{submitting ? "Starting..." : "Start Audit"}</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={handleCancelScan}
                className="w-full md:w-auto px-5 py-2 rounded-md bg-red-600 hover:bg-red-500 text-white font-medium text-sm flex items-center justify-center gap-2 transition"
              >
                <Stop size={16} weight="fill" />
                <span>Cancel Audit</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className={`p-2 rounded-md border text-xs transition ${
                showAdvanced
                  ? "bg-zinc-800 border-zinc-600 text-zinc-200"
                  : "bg-zinc-950 border-white/10 text-zinc-400 hover:text-zinc-200"
              }`}
              title="Toggle Advanced Parameters"
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
            <span className="text-zinc-200 font-medium">Rules of Engagement Acknowledgement: </span>
            I certify that I have explicit authorization to perform diagnostic security assessments on this target. All scans adhere strictly to non-destructive diagnostic stimulus.
          </label>
        </div>

        {/* Advanced Configuration Accordion */}
        {showAdvanced && (
          <div className="pt-3 border-t border-white/5 grid grid-cols-1 sm:grid-cols-4 gap-4 text-xs">
            <div>
              <label className="block text-zinc-400 mb-1">Timeout (seconds)</label>
              <input
                type="number"
                min="1"
                max="3600"
                value={timeoutSec}
                onChange={(e) => setTimeoutSec(Number(e.target.value))}
                disabled={isScanning}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200"
              />
            </div>
            <div>
              <label className="block text-zinc-400 mb-1">Max Concurrency</label>
              <input
                type="number"
                min="1"
                max="10000"
                value={maxConcurrency}
                onChange={(e) => setMaxConcurrency(Number(e.target.value))}
                disabled={isScanning}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200"
              />
            </div>
            <div>
              <label className="block text-zinc-400 mb-1">Rate Limit (req/sec)</label>
              <input
                type="number"
                min="0.5"
                max="10000"
                step="1"
                value={rps}
                onChange={(e) => setRps(Number(e.target.value))}
                disabled={isScanning}
                className="w-full bg-zinc-950 border border-white/10 rounded px-2.5 py-1.5 text-zinc-200"
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
                Allow Private / RFC 1918 IPs
              </label>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
