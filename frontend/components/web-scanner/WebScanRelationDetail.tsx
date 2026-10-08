"use client";

import React from "react";
import {
  ArrowRight,
  Info,
  WarningCircle,
  X,
  ArrowSquareOut,
} from "@phosphor-icons/react";
import { GeoEndpoint, GeoRelation } from "@/lib/webScanTypes";
import { useWebScanStore } from "@/lib/webScanStore";

interface WebScanRelationDetailProps {
  relation: GeoRelation | null;
  endpointsById: Map<string, GeoEndpoint>;
  onClose: () => void;
}

export function WebScanRelationDetail({
  relation,
  endpointsById,
  onClose,
}: WebScanRelationDetailProps) {
  const { findings, setSelectedFinding } = useWebScanStore();

  if (!relation) return null;

  const source = endpointsById.get(relation.source_endpoint_id);
  const target = endpointsById.get(relation.target_endpoint_id);
  const targetLoc = target?.location;

  const getBasisLabel = (basis: string) => {
    switch (basis) {
      case "observed_http":
        return "HTTP Teramati (Respon Nyata)";
      case "transport_attempt":
        return "Percobaan Transport (TCP/TLS Sambungan)";
      case "configured_target":
        return "Target Konfigurasi (Parameter Input)";
      default:
        return basis;
    }
  };

  return (
    <div
      role="region"
      aria-label="Rincian Hubungan Pemindaian"
      className="bg-zinc-900 border border-white/10 rounded-lg p-4 space-y-4 shadow-lg text-xs"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded bg-blue-500/20 text-blue-400">
            <Info size={16} weight="bold" />
          </div>
          <h4 className="font-semibold text-zinc-100">Rincian Hubungan Pemindaian</h4>
        </div>

        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-white/10 text-zinc-400 hover:text-zinc-200 transition focus:outline-none focus:ring-1 focus:ring-blue-500"
          title="Tutup Detail"
          aria-label="Tutup Rincian Hubungan"
        >
          <X size={16} />
        </button>
      </div>

      {/* Endpoint Path Banner */}
      <div className="bg-zinc-950 border border-white/5 rounded-md p-3 flex items-center justify-between gap-3 font-mono">
        <div>
          <span className="text-[10px] text-zinc-500 block uppercase tracking-wider">
            Sumber (Executor)
          </span>
          <span className="text-blue-400 font-bold">{source?.display_name || "Executor"}</span>
          <span className="text-[11px] text-zinc-400 block mt-0.5">
            {source?.location?.city
              ? `${source.location.city}, ${source.location.country}`
              : "Lokasi tidak dikonfigurasi"}
          </span>
        </div>

        <div className="flex flex-col items-center px-2">
          <ArrowRight size={18} className="text-zinc-500" />
          <span className="text-[10px] text-zinc-500 mt-1">
            {relation.record_count} {relation.unit}
          </span>
        </div>

        <div className="text-right">
          <span className="text-[10px] text-zinc-500 block uppercase tracking-wider">
            Target (Tujuan)
          </span>
          <span className="text-emerald-400 font-bold">
            {target?.ip || target?.display_name || "Target"}
          </span>
          <span className="text-[11px] text-zinc-400 block mt-0.5">
            {targetLoc
              ? [targetLoc.city, targetLoc.country].filter(Boolean).join(", ")
              : "Lokasi tidak diketahui"}
          </span>
        </div>
      </div>

      {/* Relation Basis & Target Provenance */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px]">
        <div className="space-y-1 bg-zinc-950/60 p-2.5 rounded border border-white/5">
          <span className="text-zinc-400 block font-medium">Dasar Relasi Hubungan</span>
          <span className="font-mono text-zinc-200 block">
            {getBasisLabel(relation.relation_basis)}
          </span>
        </div>

        <div className="space-y-1 bg-zinc-950/60 p-2.5 rounded border border-white/5">
          <span className="text-zinc-400 block font-medium">Estimasi Geolokasi Target</span>
          <span className="font-mono text-zinc-200 block">
            {target?.location_status === "located" && targetLoc
              ? `${targetLoc.latitude.toFixed(4)}, ${targetLoc.longitude.toFixed(4)} (${target.location_level || "perkiraan"})`
              : target?.status_reason || "Estimasi koordinat tidak tersedia"}
          </span>
        </div>
      </div>

      {/* Target Address Basis & Provenance */}
      <div className="bg-zinc-950/60 p-2.5 rounded border border-white/5 text-[11px] space-y-1">
        <span className="text-zinc-400 block font-medium">Provenans Alamat IP Target</span>
        <span className="font-mono text-zinc-300 block">
          {target?.address_basis === "observed_connection"
            ? "Koneksi Teramati (Peer Socket Address)"
            : target?.address_basis === "transport_selected"
            ? "IP Pilihan Transport (DNS Pinning)"
            : target?.address_basis === "dns_candidate"
            ? "Kandidat DNS Resolusi"
            : target?.address_basis === "configured"
            ? "Tujuan Terkonfigurasi"
            : "Belum Teresolusi"}
        </span>
      </div>

      {/* HTTP Observational Telemetry */}
      <div className="space-y-2">
        <span className="text-[11px] font-semibold text-zinc-300 block">Observasi HTTP Terkait</span>
        <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
          <span className="text-zinc-400">Metode:</span>
          {relation.methods.map((m) => (
            <span
              key={m}
              className="px-1.5 py-0.5 rounded bg-zinc-950 border border-white/10 text-zinc-300"
            >
              {m}
            </span>
          ))}

          <span className="text-zinc-400 ml-2">Status:</span>
          {relation.status_codes.map((sc) => (
            <span
              key={sc}
              className="px-1.5 py-0.5 rounded bg-zinc-950 border border-white/10 text-zinc-300"
            >
              {sc}
            </span>
          ))}
        </div>
      </div>

      {/* Supporting Observation IDs */}
      {relation.supporting_observation_ids.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[11px] font-semibold text-zinc-400 block">
            ID Observasi Bukti ({relation.supporting_observation_ids.length})
          </span>
          <div className="max-h-20 overflow-y-auto space-y-1 font-mono text-[10px] text-zinc-500 bg-zinc-950 p-2 rounded border border-white/5">
            {relation.supporting_observation_ids.map((id) => (
              <div key={id} className="truncate">
                {id}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Linked Security Findings — Actionable Buttons */}
      {relation.linked_finding_ids.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[11px] font-semibold text-amber-400 flex items-center gap-1.5">
            <WarningCircle size={14} />
            <span>Temuan Keamanan Tertaut ({relation.linked_finding_ids.length})</span>
          </span>
          <div className="max-h-28 overflow-y-auto space-y-1 bg-amber-950/20 border border-amber-500/20 p-2 rounded">
            {relation.linked_finding_ids.map((fid) => {
              const matchedFinding = findings.find((f) => f.id === fid);
              return (
                <button
                  key={fid}
                  type="button"
                  onClick={() => {
                    if (matchedFinding) {
                      setSelectedFinding(matchedFinding);
                    }
                  }}
                  disabled={!matchedFinding}
                  title={matchedFinding ? "Buka rincian temuan ini" : "Detail temuan tidak ditemukan"}
                  className={`w-full text-left font-mono text-[11px] px-2 py-1 rounded flex items-center justify-between gap-2 transition ${
                    matchedFinding
                      ? "hover:bg-amber-500/20 text-amber-200 cursor-pointer"
                      : "text-zinc-500 cursor-default"
                  }`}
                >
                  <span className="truncate">
                    {matchedFinding ? `${matchedFinding.check_id}: ${matchedFinding.title}` : `ID: ${fid}`}
                  </span>
                  {matchedFinding && <ArrowSquareOut size={13} className="shrink-0 text-amber-400" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
