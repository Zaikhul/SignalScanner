"use client";

import React, { useEffect, useState } from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { useWebScanGeography } from "@/hooks/useWebScanGeography";
import { WebScanGlobe } from "./WebScanGlobe";
import { WebScanRelationList } from "./WebScanRelationList";
import { WebScanRelationDetail } from "./WebScanRelationDetail";
import {
  Globe,
  ListDashes,
  Eye,
  MagnifyingGlass,
  ArrowClockwise,
  Info,
  WarningOctagon,
  CaretDown,
  CaretUp,
} from "@phosphor-icons/react";

export function WebScanGeographyPanel({ scanId }: { scanId?: string } = {}) {
  const { activeJob } = useWebScanStore();
  const effectiveScanId = scanId || activeJob?.id || null;
  const [isCollapsed, setIsCollapsed] = useState(false);

  const {
    data,
    loading,
    error,
    selectedRelationId,
    setSelectedRelationId,
    selectedRelation,
    searchQuery,
    setSearchQuery,
    statusFilter,
    setStatusFilter,
    basisFilter,
    setBasisFilter,
    viewMode,
    setViewMode,
    canvasSupported,
    setCanvasSupported,
    filteredRelations,
    endpointsById,
    clearFilters,
    refetch,
  } = useWebScanGeography(effectiveScanId, activeJob?.status);

  // Fallback connection (T07): automatically switch to list mode if Canvas 2D fails
  useEffect(() => {
    if (!canvasSupported && viewMode !== "list") {
      setViewMode("list");
    }
  }, [canvasSupported, viewMode, setViewMode]);

  if (!effectiveScanId) {
    return (
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-6 text-center space-y-2">
        <div className="w-10 h-10 mx-auto rounded-full bg-zinc-950 border border-white/5 flex items-center justify-center text-zinc-500">
          <Globe size={20} />
        </div>
        <p className="text-xs text-zinc-400">
          Pilih atau jalankan scan yang telah diotorisasi untuk melihat peta hubungan pemindaian.
        </p>
      </div>
    );
  }

  const coverage = data?.coverage;
  const isFiltered = Boolean(searchQuery.trim() || statusFilter !== "all" || basisFilter !== "all");

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg p-5 space-y-4 shadow-sm">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <Globe size={18} weight="bold" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-100">
              Peta Hubungan Pemindaian (Scan Flow Graph)
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-950 border border-white/10 text-zinc-400">
              web_scan.geo.v1
            </span>
          </div>
          <p className="text-xs text-zinc-400">
            Visualisasi hubungan logis permintaan HTTP dari pelaksana scan backend menuju alamat IP target.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded bg-zinc-950 hover:bg-zinc-800 border border-white/10 text-zinc-400 hover:text-zinc-200 text-xs flex items-center gap-1 transition"
            title={isCollapsed ? "Buka panel hubungan" : "Ringkas panel hubungan"}
            aria-expanded={!isCollapsed}
          >
            {isCollapsed ? <CaretDown size={14} /> : <CaretUp size={14} />}
            <span className="hidden sm:inline">{isCollapsed ? "Buka" : "Ringkas"}</span>
          </button>

          <button
            onClick={refetch}
            disabled={loading}
            className="p-1.5 rounded bg-zinc-950 hover:bg-zinc-800 border border-white/10 text-zinc-300 text-xs flex items-center gap-1.5 transition disabled:opacity-50"
            title="Perbarui Hasil Geografis Tersimpan"
          >
            <ArrowClockwise size={14} className={loading ? "animate-spin" : ""} />
            <span className="hidden sm:inline">Perbarui</span>
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <>
          {/* Mandatory Regulatory / Semantic Disclaimer (PRD §1 & §10.3) */}
          <div className="bg-blue-950/30 border border-blue-500/20 rounded-md p-3 flex items-start gap-2.5 text-xs text-blue-300/90 leading-relaxed">
            <Info size={16} className="shrink-0 mt-0.5 text-blue-400" />
            <span>
              <strong>Pemberitahuan:</strong> Lokasi IP merupakan perkiraan. Garis menunjukkan hubungan permintaan yang divisualisasikan, bukan rute paket atau lokasi fisik yang terverifikasi.
            </span>
          </div>

          {/* Canvas 2D Fallback Alert Banner (T07) */}
          {!canvasSupported && (
            <div className="bg-amber-950/30 border border-amber-500/20 rounded-md p-3 flex items-start gap-2.5 text-xs text-amber-300/90">
              <WarningOctagon size={16} className="shrink-0 mt-0.5 text-amber-400" />
              <span>
                Tampilan grafis globe tidak dapat diinisialisasi (Canvas 2D tidak didukung pada peramban ini); seluruh hubungan dialihkan secara otomatis ke mode <strong>Daftar</strong>.
              </span>
            </div>
          )}

          {/* Subset Alert if database capped observations */}
          {coverage?.is_subset && (
            <div className="bg-amber-950/30 border border-amber-500/20 rounded-md p-3 flex items-start gap-2.5 text-xs text-amber-300/90">
              <WarningOctagon size={16} className="shrink-0 mt-0.5 text-amber-400" />
              <span>
                Hanya sebagian observasi scan tersimpan (sampel {coverage.observations_stored} dari {coverage.observations_total} observasi dibuat). Hubungan yang ditampilkan mewakili observasi tersimpan yang diizinkan.
              </span>
            </div>
          )}

          {/* Coverage Metric Summary Bar with Clear Units (T11) */}
          {coverage && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              <div className="bg-zinc-950 border border-white/5 rounded-md p-2.5 font-mono">
                <span className="text-[10px] text-zinc-500 block">Total Rekaman Terkait</span>
                <span className="text-sm font-bold text-zinc-200">{coverage.eligible_records}</span>
                <span className="text-[10px] text-zinc-500 block">observasi</span>
              </div>

              <div className="bg-zinc-950 border border-white/5 rounded-md p-2.5 font-mono">
                <span className="text-[10px] text-zinc-500 block">Terpetakan Lengkap</span>
                <span className="text-sm font-bold text-emerald-400">{coverage.both_located_count}</span>
                <span className="text-[10px] text-zinc-500 block">relasi</span>
              </div>

              <div className="bg-zinc-950 border border-white/5 rounded-md p-2.5 font-mono">
                <span className="text-[10px] text-zinc-500 block">Lokasi Sebagian</span>
                <span className="text-sm font-bold text-amber-400">{coverage.partial_located_count}</span>
                <span className="text-[10px] text-zinc-500 block">relasi</span>
              </div>

              <div className="bg-zinc-950 border border-white/5 rounded-md p-2.5 font-mono">
                <span className="text-[10px] text-zinc-500 block">Lokasi Tidak Diketahui</span>
                <span className="text-sm font-bold text-zinc-400">{coverage.unlocated_count}</span>
                <span className="text-[10px] text-zinc-500 block">relasi</span>
              </div>
            </div>
          )}

          {/* Interactive Controls & Filter Toolbar */}
          <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 pt-1">
            {/* Search Input */}
            <div className="relative flex-1">
              <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type="text"
                placeholder="Cari IP, hostname target, atau status..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Cari IP, hostname target, atau status"
                className="w-full bg-zinc-950 border border-white/10 rounded-md pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Status Filter */}
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter status HTTP"
                className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-blue-500 font-mono"
              >
                <option value="all">Semua Status HTTP</option>
                <option value="2xx">Status 2xx (Sukses)</option>
                <option value="3xx">Status 3xx (Redirect)</option>
                <option value="4xx">Status 4xx (Client Error)</option>
                <option value="5xx">Status 5xx (Server Error)</option>
              </select>

              {/* Basis Filter (T06) */}
              <select
                value={basisFilter}
                onChange={(e) => setBasisFilter(e.target.value)}
                aria-label="Filter basis relasi"
                className="bg-zinc-950 border border-white/10 rounded-md px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-blue-500 font-mono"
              >
                <option value="all">Semua Basis Relasi</option>
                <option value="observed_http">HTTP Teramati</option>
                <option value="transport_attempt">Percobaan Transport</option>
                <option value="configured_target">Target Konfigurasi</option>
              </select>

              {/* View Mode Toggle Buttons (T07) */}
              <div className="flex items-center bg-zinc-950 border border-white/10 rounded-md p-0.5 text-xs">
                <button
                  onClick={() => setViewMode("globe")}
                  disabled={!canvasSupported}
                  aria-pressed={viewMode === "globe"}
                  className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed ${
                    viewMode === "globe" ? "bg-blue-600 text-white font-medium" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title={canvasSupported ? "Tampilan Globe 3D Saja" : "Globe tidak didukung"}
                >
                  <Globe size={13} />
                  <span className="hidden sm:inline">3D</span>
                </button>
                <button
                  onClick={() => setViewMode("list")}
                  aria-pressed={viewMode === "list"}
                  className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 ${
                    viewMode === "list" ? "bg-blue-600 text-white font-medium" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title="Tampilan Daftar Hubungan Saja (WCAG AA)"
                >
                  <ListDashes size={13} />
                  <span className="hidden sm:inline">Daftar</span>
                </button>
                <button
                  onClick={() => setViewMode("split")}
                  disabled={!canvasSupported}
                  aria-pressed={viewMode === "split"}
                  className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed ${
                    viewMode === "split" ? "bg-blue-600 text-white font-medium" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                  title={canvasSupported ? "Tampilan Bersanding (3D + Daftar)" : "Globe tidak didukung"}
                >
                  <Eye size={13} />
                  <span className="hidden sm:inline">Bersanding</span>
                </button>
              </div>
            </div>
          </div>

          {/* Main Presentation Area */}
          {loading && !data ? (
            <div className="h-64 flex flex-col items-center justify-center text-xs text-zinc-500 space-y-2">
              <ArrowClockwise size={22} className="animate-spin text-blue-400" />
              <span>Memuat dataset hubungan geografis...</span>
            </div>
          ) : error ? (
            <div className="bg-red-950/40 border border-red-500/30 rounded-lg p-4 text-xs text-red-300 flex items-center justify-between">
              <span>{error}</span>
              <button onClick={refetch} className="underline text-red-400 hover:text-red-200 font-mono">
                Coba lagi
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Conditional Layouts: Globe, List, or Split */}
              {viewMode === "globe" && canvasSupported && (
                <WebScanGlobe
                  endpointsById={endpointsById}
                  relations={filteredRelations}
                  selectedRelationId={selectedRelationId}
                  onSelectRelation={setSelectedRelationId}
                  onCanvasError={() => setCanvasSupported(false)}
                />
              )}

              {viewMode === "list" && (
                <WebScanRelationList
                  relations={filteredRelations}
                  endpointsById={endpointsById}
                  selectedRelationId={selectedRelationId}
                  onSelectRelation={setSelectedRelationId}
                  onClearFilters={clearFilters}
                  isFiltered={isFiltered}
                />
              )}

              {viewMode === "split" && canvasSupported && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                  <WebScanGlobe
                    endpointsById={endpointsById}
                    relations={filteredRelations}
                    selectedRelationId={selectedRelationId}
                    onSelectRelation={setSelectedRelationId}
                    onCanvasError={() => setCanvasSupported(false)}
                  />

                  <WebScanRelationList
                    relations={filteredRelations}
                    endpointsById={endpointsById}
                    selectedRelationId={selectedRelationId}
                    onSelectRelation={setSelectedRelationId}
                    onClearFilters={clearFilters}
                    isFiltered={isFiltered}
                  />
                </div>
              )}

              {/* Detailed Drawer / Inspection Box */}
              {selectedRelation && (
                <WebScanRelationDetail
                  relation={selectedRelation}
                  endpointsById={endpointsById}
                  onClose={() => setSelectedRelationId(null)}
                />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
