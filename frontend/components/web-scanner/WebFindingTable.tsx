"use client";

import React, { useMemo, useState } from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { Severity } from "@/lib/webScanTypes";
import {
  MagnifyingGlass,
  Funnel,
  CaretRight,
  CaretLeft,
} from "@phosphor-icons/react";

const PAGE_SIZE = 15;

export function WebFindingTable() {
  const { findings, setSelectedFinding } = useWebScanStore();

  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [moduleFilter, setModuleFilter] = useState<string>("all");
  const [search, setSearch] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);

  const filtered = useMemo(() => {
    return findings.filter((f) => {
      if (severityFilter !== "all" && f.severity !== severityFilter) return false;
      if (moduleFilter !== "all" && f.module !== moduleFilter) return false;
      if (search) {
        const query = search.toLowerCase();
        const matchesTitle = f.title.toLowerCase().includes(query);
        const matchesCheck = f.check_id.toLowerCase().includes(query);
        const matchesDesc = f.description.toLowerCase().includes(query);
        if (!matchesTitle && !matchesCheck && !matchesDesc) return false;
      }
      return true;
    });
  }, [findings, severityFilter, moduleFilter, search]);

  // Reset to page 1 when filter/search changes
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const activePage = Math.min(currentPage, totalPages);
  const startIndex = (activePage - 1) * PAGE_SIZE;
  const paginatedFindings = filtered.slice(startIndex, startIndex + PAGE_SIZE);

  const severityBadges: Record<Severity, string> = {
    critical: "bg-red-950/60 text-red-400 border-red-500/30",
    high: "bg-orange-950/60 text-orange-400 border-orange-500/30",
    medium: "bg-amber-950/60 text-amber-400 border-amber-500/30",
    low: "bg-blue-950/60 text-blue-400 border-blue-500/30",
    info: "bg-zinc-800 text-zinc-300 border-zinc-700",
  };

  return (
    <div
      role="region"
      aria-label="Tabel Temuan Keamanan"
      className="bg-zinc-900 border border-white/10 rounded-lg overflow-hidden shadow-sm"
    >
      {/* Table Toolbar */}
      <div className="p-4 border-b border-white/10 flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex items-center gap-2 w-full sm:w-72 relative">
          <MagnifyingGlass size={16} className="absolute left-3 text-zinc-500 pointer-events-none" />
          <input
            type="text"
            aria-label="Cari temuan berdasarkan judul atau check ID"
            placeholder="Cari temuan keamanan..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
            }}
            className="w-full pl-9 pr-3 py-1.5 bg-zinc-950 border border-white/10 rounded-md text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Funnel size={14} className="text-zinc-500" />
          <select
            aria-label="Filter berdasarkan tingkat keparahan (severity)"
            value={severityFilter}
            onChange={(e) => {
              setSeverityFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-blue-500 transition"
          >
            <option value="all">Semua Severity</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </select>

          <select
            aria-label="Filter berdasarkan modul pemeriksaan"
            value={moduleFilter}
            onChange={(e) => {
              setModuleFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-blue-500 transition"
          >
            <option value="all">Semua Modul</option>
            <option value="recon">Recon</option>
            <option value="headers">Headers</option>
            <option value="cookies">Cookies</option>
            <option value="forms">Forms</option>
            <option value="parameters">Parameters</option>
            <option value="header_probes">Header Probes</option>
            <option value="stress">Stress / Load</option>
          </select>
        </div>
      </div>

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-zinc-300">
          <thead className="bg-zinc-950/60 text-zinc-400 font-mono text-[11px] uppercase tracking-wider border-b border-white/5">
            <tr>
              <th scope="col" className="py-3 px-4">Severity</th>
              <th scope="col" className="py-3 px-4">Check ID</th>
              <th scope="col" className="py-3 px-4">Judul Temuan</th>
              <th scope="col" className="py-3 px-4">Confidence</th>
              <th scope="col" className="py-3 px-4">Jumlah</th>
              <th scope="col" className="py-3 px-4 text-right">Aksi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-zinc-500">
                  {findings.length === 0
                    ? "Belum ada temuan keamanan yang tercatat pada scan ini."
                    : "Tidak ada temuan keamanan yang sesuai dengan filter atau kata kunci."}
                </td>
              </tr>
            ) : (
              paginatedFindings.map((finding) => (
                <tr
                  key={finding.id}
                  tabIndex={0}
                  role="button"
                  aria-label={`Lihat rincian temuan ${finding.title}, severity ${finding.severity}`}
                  onClick={() => setSelectedFinding(finding)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectedFinding(finding);
                    }
                  }}
                  className="hover:bg-zinc-800/50 cursor-pointer transition focus:outline-none focus:bg-zinc-800/60 focus:ring-1 focus:ring-inset focus:ring-blue-500"
                >
                  <td className="py-3 px-4">
                    <span
                      className={`inline-block px-2 py-0.5 rounded font-mono uppercase text-[10px] font-semibold border ${
                        severityBadges[finding.severity]
                      }`}
                    >
                      {finding.severity}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-mono text-zinc-400">{finding.check_id}</td>
                  <td className="py-3 px-4 font-medium text-zinc-100">{finding.title}</td>
                  <td className="py-3 px-4 capitalize font-mono text-[11px] text-zinc-400">
                    {finding.confidence.replace("_", " ")}
                  </td>
                  <td className="py-3 px-4 font-mono text-zinc-400">{finding.occurrence_count}</td>
                  <td className="py-3 px-4 text-right">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedFinding(finding);
                      }}
                      aria-label={`Buka detail temuan: ${finding.title}`}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-white/10 transition focus:outline-none focus:ring-1 focus:ring-blue-500 text-[11px]"
                    >
                      <span>Buka</span>
                      <CaretRight size={12} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Table Pagination & Provenance Footer */}
      <div className="p-3 border-t border-white/10 bg-zinc-950/40 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-zinc-400">
        <div className="font-mono text-[11px]">
          {filtered.length === 0 ? (
            <span>0 temuan</span>
          ) : (
            <span>
              Menampilkan {startIndex + 1}–{Math.min(startIndex + PAGE_SIZE, filtered.length)} dari{" "}
              {filtered.length} temuan tersaring
              {filtered.length !== findings.length && ` (Total scan: ${findings.length})`}
            </span>
          )}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center gap-1.5 font-mono text-xs">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={activePage <= 1}
              aria-label="Halaman Sebelumnya"
              className="p-1.5 rounded bg-zinc-900 border border-white/10 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <CaretLeft size={14} />
            </button>
            <span className="px-2 text-zinc-400">
              {activePage} / {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={activePage >= totalPages}
              aria-label="Halaman Selanjutnya"
              className="p-1.5 rounded bg-zinc-900 border border-white/10 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <CaretRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
