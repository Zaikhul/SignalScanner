"use client";

import React, { useMemo, useState } from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { ScanFinding, Severity } from "@/lib/webScanTypes";
import { MagnifyingGlass, Funnel, CaretRight } from "@phosphor-icons/react";

export function WebFindingTable() {
  const { findings, setSelectedFinding } = useWebScanStore();

  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [moduleFilter, setModuleFilter] = useState<string>("all");
  const [search, setSearch] = useState<string>("");

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

  const severityBadges: Record<Severity, string> = {
    critical: "bg-red-950/60 text-red-400 border-red-500/30",
    high: "bg-orange-950/60 text-orange-400 border-orange-500/30",
    medium: "bg-amber-950/60 text-amber-400 border-amber-500/30",
    low: "bg-blue-950/60 text-blue-400 border-blue-500/30",
    info: "bg-zinc-800 text-zinc-300 border-zinc-700",
  };

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg overflow-hidden shadow-sm">
      {/* Table Toolbar */}
      <div className="p-4 border-b border-white/10 flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex items-center gap-2 w-full sm:w-72 relative">
          <MagnifyingGlass size={16} className="absolute left-3 text-zinc-500" />
          <input
            type="text"
            placeholder="Search findings by title or check..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 bg-zinc-950 border border-white/10 rounded-md text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Funnel size={14} className="text-zinc-500" />
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </select>

          <select
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-zinc-200 focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Modules</option>
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
              <th className="py-3 px-4">Severity</th>
              <th className="py-3 px-4">Check ID</th>
              <th className="py-3 px-4">Title</th>
              <th className="py-3 px-4">Confidence</th>
              <th className="py-3 px-4">Count</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-zinc-500">
                  No security findings recorded matching current filters.
                </td>
              </tr>
            ) : (
              filtered.map((finding) => (
                <tr
                  key={finding.id}
                  onClick={() => setSelectedFinding(finding)}
                  className="hover:bg-zinc-800/50 cursor-pointer transition"
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
                  <td className="py-3 px-4 text-right text-zinc-500">
                    <CaretRight size={14} className="inline-block" />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
