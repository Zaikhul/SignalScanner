"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { useWebScanStore } from "@/lib/webScanStore";
import { WebScanStatusBadge } from "./WebScanStatusBadge";
import { ArrowClockwise, ArrowRight } from "@phosphor-icons/react";

export function WebScanHistory() {
  const { history, historyTotal, setHistory, setActiveJob, setSnapshot } = useWebScanStore();
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const page = await webScanApiClient.listScans(statusFilter || undefined, 20, 0);
      setHistory(page.items, page.total);
    } catch (err) {
      console.warn("Failed to load scan history:", err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, setHistory]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg overflow-hidden shadow-sm">
      <div className="p-4 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-zinc-100">Scan Job History</h3>
          <span className="text-xs text-zinc-500 font-mono">({historyTotal} total)</span>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1 text-xs text-zinc-300 focus:outline-none"
          >
            <option value="">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="scanning">Scanning</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>

          <button
            onClick={loadHistory}
            disabled={loading}
            className="p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition"
            title="Refresh history"
          >
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-zinc-300">
          <thead className="bg-zinc-950/60 text-zinc-400 font-mono text-[11px] uppercase tracking-wider border-b border-white/5">
            <tr>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Target</th>
              <th className="py-3 px-4">Profile</th>
              <th className="py-3 px-4">Created At</th>
              <th className="py-3 px-4">Duration</th>
              <th className="py-3 px-4 text-right">View</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {history.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-zinc-500">
                  {loading ? "Loading scan history..." : "No scan jobs found in history."}
                </td>
              </tr>
            ) : (
              history.map((job) => {
                let durationStr = "N/A";
                if (job.started_at && job.ended_at) {
                  const sec = Math.round(
                    (new Date(job.ended_at).getTime() - new Date(job.started_at).getTime()) / 1000
                  );
                  durationStr = `${sec}s`;
                }

                return (
                  <tr key={job.id} className="hover:bg-zinc-800/40 transition">
                    <td className="py-3 px-4">
                      <WebScanStatusBadge status={job.status} size="sm" />
                    </td>
                    <td className="py-3 px-4 font-mono font-medium text-zinc-100">
                      {job.target_display}
                    </td>
                    <td className="py-3 px-4 font-mono text-zinc-400">
                      {job.requested_configuration?.profile || "v2"}
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      {job.created_at ? new Date(job.created_at).toLocaleString() : "N/A"}
                    </td>
                    <td className="py-3 px-4 font-mono text-zinc-400">{durationStr}</td>
                    <td className="py-3 px-4 text-right">
                      <Link
                        href={`/web-scanner/${job.id}`}
                        className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 font-medium"
                      >
                        <span>Inspect</span>
                        <ArrowRight size={12} />
                      </Link>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
