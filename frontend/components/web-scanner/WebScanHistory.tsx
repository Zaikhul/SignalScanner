"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { useWebScanStore } from "@/lib/webScanStore";
import { WebScanStatusBadge } from "./WebScanStatusBadge";
import {
  ArrowClockwise,
  ArrowRight,
  CaretLeft,
  CaretRight,
  Warning,
} from "@phosphor-icons/react";

const PAGE_SIZE = 15;

export function WebScanHistory() {
  const { history, historyTotal, setHistory } = useWebScanStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const offset = (currentPage - 1) * PAGE_SIZE;
      const page = await webScanApiClient.listScans(
        statusFilter || undefined,
        PAGE_SIZE,
        offset
      );
      setHistory(page.items, page.total);
    } catch (err: any) {
      setError(err.message || "Gagal memuat riwayat pemindaian.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, currentPage, setHistory]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const totalPages = Math.max(1, Math.ceil(historyTotal / PAGE_SIZE));
  const startIndex = (currentPage - 1) * PAGE_SIZE;

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg overflow-hidden shadow-sm">
      <div className="p-4 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-zinc-100">Riwayat Pemindaian</h3>
          <span className="text-xs text-zinc-500 font-mono">({historyTotal} total)</span>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1 text-xs text-zinc-300 focus:outline-none focus:border-blue-500"
          >
            <option value="">Semua Status</option>
            <option value="completed">Completed</option>
            <option value="partial">Partial</option>
            <option value="scanning">Scanning</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>

          <button
            onClick={loadHistory}
            disabled={loading}
            className="p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition focus:outline-none focus:ring-1 focus:ring-blue-500"
            title="Segarkan riwayat"
            aria-label="Segarkan riwayat"
          >
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-950/40 border-b border-red-500/20 flex items-center justify-between gap-2 text-xs text-red-300">
          <div className="flex items-center gap-2">
            <Warning size={14} className="text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={loadHistory}
            className="px-2.5 py-1 rounded bg-red-900/60 hover:bg-red-800/80 text-white font-mono text-[11px] transition"
          >
            Coba Lagi
          </button>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-zinc-300">
          <thead className="bg-zinc-950/60 text-zinc-400 font-mono text-[11px] uppercase tracking-wider border-b border-white/5">
            <tr>
              <th scope="col" className="py-3 px-4">Status</th>
              <th scope="col" className="py-3 px-4">Target</th>
              <th scope="col" className="py-3 px-4">Profil</th>
              <th scope="col" className="py-3 px-4">Waktu Dibuat</th>
              <th scope="col" className="py-3 px-4">Durasi</th>
              <th scope="col" className="py-3 px-4 text-right">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {history.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-zinc-500">
                  {loading ? "Memuat riwayat pemindaian..." : "Tidak ada catatan scan dalam riwayat."}
                </td>
              </tr>
            ) : (
              history.map((job) => {
                let durationStr = "—";
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
                      {job.created_at ? new Date(job.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="py-3 px-4 font-mono text-zinc-400">{durationStr}</td>
                    <td className="py-3 px-4 text-right">
                      <Link
                        href={`/web-scanner/${job.id}`}
                        className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 font-medium focus:outline-none focus:underline"
                      >
                        <span>Inspeksi</span>
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

      {/* Pagination Footer */}
      {historyTotal > PAGE_SIZE && (
        <div className="p-3 border-t border-white/10 bg-zinc-950/40 flex items-center justify-between text-xs text-zinc-400 font-mono">
          <span>
            Menampilkan {startIndex + 1}–{Math.min(startIndex + PAGE_SIZE, historyTotal)} dari{" "}
            {historyTotal} riwayat
          </span>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1 || loading}
              aria-label="Halaman Sebelumnya"
              className="p-1.5 rounded bg-zinc-900 border border-white/10 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <CaretLeft size={14} />
            </button>
            <span className="px-2 text-zinc-400">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages || loading}
              aria-label="Halaman Selanjutnya"
              className="p-1.5 rounded bg-zinc-900 border border-white/10 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <CaretRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
