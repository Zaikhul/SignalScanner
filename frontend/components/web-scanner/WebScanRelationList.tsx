"use client";

import React from "react";
import {
  ArrowRight,
  Globe,
  Question,
  ShieldCheck,
  WarningCircle,
} from "@phosphor-icons/react";
import { GeoEndpoint, GeoRelation } from "@/lib/webScanTypes";

interface WebScanRelationListProps {
  relations: GeoRelation[];
  endpointsById: Map<string, GeoEndpoint>;
  selectedRelationId: string | null;
  onSelectRelation: (id: string | null) => void;
  onClearFilters?: () => void;
  isFiltered?: boolean;
}

export function WebScanRelationList({
  relations,
  endpointsById,
  selectedRelationId,
  onSelectRelation,
  onClearFilters,
  isFiltered = false,
}: WebScanRelationListProps) {
  if (relations.length === 0) {
    return (
      <div className="bg-zinc-950 border border-white/5 rounded-lg p-8 text-center space-y-3">
        <div className="w-10 h-10 mx-auto rounded-full bg-zinc-900 border border-white/10 flex items-center justify-center text-zinc-500">
          <Question size={20} />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-zinc-300">
            {isFiltered
              ? "Tidak ada hubungan yang sesuai dengan kriteria filter/pencarian."
              : "Belum ada hubungan permintaan HTTP yang teramati pada scan ini."}
          </p>
          <p className="text-xs text-zinc-500">
            {isFiltered
              ? "Coba sesuaikan kata kunci pencarian atau bersihkan filter status."
              : "Hasil hubungan akan muncul otomatis setelah observasi scan selesai dicatat."}
          </p>
        </div>
        {isFiltered && onClearFilters && (
          <button
            onClick={onClearFilters}
            className="px-3 py-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-xs font-mono text-zinc-300 border border-white/10 transition"
          >
            Hapus Filter
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      role="region"
      aria-label="Daftar Hubungan Pemindaian"
      className="space-y-2 max-h-[420px] overflow-y-auto pr-1"
    >
      {relations.map((rel) => {
        const isSelected = rel.id === selectedRelationId;
        const source = endpointsById.get(rel.source_endpoint_id);
        const target = endpointsById.get(rel.target_endpoint_id);

        const targetLoc = target?.location;
        const targetLocText = targetLoc
          ? [targetLoc.city, targetLoc.country].filter(Boolean).join(", ")
          : "Lokasi tidak diketahui";

        return (
          <div
            key={rel.id}
            tabIndex={0}
            role="button"
            aria-pressed={isSelected}
            onClick={() => onSelectRelation(isSelected ? null : rel.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectRelation(isSelected ? null : rel.id);
              }
            }}
            className={`w-full text-left p-3.5 rounded-lg border transition cursor-pointer select-none outline-none focus:ring-1 focus:ring-blue-500 ${
              isSelected
                ? "bg-blue-500/10 border-blue-500/40 text-zinc-100 shadow-sm"
                : "bg-zinc-900/60 hover:bg-zinc-900 border-white/5 text-zinc-300"
            }`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
              {/* Endpoint Flow: Source -> Target */}
              <div className="flex items-center gap-2 text-xs font-mono">
                <span className="text-blue-400 font-semibold truncate max-w-[130px]">
                  {source?.display_name || "Executor"}
                </span>
                <ArrowRight size={14} className="text-zinc-500 shrink-0" />
                <span className="text-emerald-400 font-semibold truncate max-w-[170px]">
                  {target?.ip || target?.display_name || "Target"}
                </span>
              </div>

              {/* Status Codes & Record count badge */}
              <div className="flex items-center gap-2 shrink-0 text-xs">
                {rel.status_codes.map((sc) => {
                  const badgeColor =
                    sc >= 200 && sc < 300
                      ? "bg-emerald-950/60 border-emerald-500/30 text-emerald-400"
                      : sc >= 300 && sc < 400
                      ? "bg-sky-950/60 border-sky-500/30 text-sky-400"
                      : sc >= 400 && sc < 500
                      ? "bg-amber-950/60 border-amber-500/30 text-amber-400"
                      : "bg-red-950/60 border-red-500/30 text-red-400";
                  return (
                    <span
                      key={sc}
                      className={`px-1.5 py-0.5 rounded font-mono text-[11px] border ${badgeColor}`}
                    >
                      {sc}
                    </span>
                  );
                })}

                <span className="px-2 py-0.5 rounded bg-zinc-950 border border-white/10 font-mono text-[11px] text-zinc-400">
                  {rel.record_count} {rel.unit}
                </span>
              </div>
            </div>

            {/* Sub-info: Location & Evidence links */}
            <div className="mt-2 pt-2 border-t border-white/5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-400">
              <div className="flex items-center gap-1.5">
                <Globe size={13} className="text-zinc-500" />
                <span>Target: {targetLocText}</span>
                {target?.location_status !== "located" && (
                  <span className="text-zinc-500 italic">(Estimasi tidak tersedia)</span>
                )}
              </div>

              {rel.linked_finding_ids.length > 0 && (
                <div className="flex items-center gap-1 text-amber-400 font-mono">
                  <WarningCircle size={13} />
                  <span>{rel.linked_finding_ids.length} Temuan Terkait</span>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
