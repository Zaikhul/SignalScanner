"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { webScanApiClient } from "@/lib/webScanApiClient";
import {
  GeoEndpoint,
  GeoRelation,
  WebScanGeographyResponse,
} from "@/lib/webScanTypes";

export type ViewMode = "globe" | "list" | "split";

export function useWebScanGeography(scanId: string | null, scanStatus?: string | null) {
  const [data, setData] = useState<WebScanGeographyResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRelationId, setSelectedRelationId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [basisFilter, setBasisFilter] = useState<string>("all");
  const [viewMode, setViewMode] = useState<ViewMode>("split");
  const [canvasSupported, setCanvasSupported] = useState<boolean>(true);

  // Keep track of the currently active scanId to prevent race conditions (T04)
  const activeScanRef = useRef<string | null>(scanId);
  activeScanRef.current = scanId;

  // Track if terminal refetch has occurred for the current scanId (T05)
  const terminalRefetchedRef = useRef<string | null>(null);

  const fetchGeography = useCallback(async (targetId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await webScanApiClient.getGeography(targetId);
      if (activeScanRef.current === targetId) {
        setData(res);
      }
    } catch (err: any) {
      if (activeScanRef.current === targetId) {
        setError(err.message || "Gagal memuat dataset hubungan geografis");
      }
    } finally {
      if (activeScanRef.current === targetId) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!scanId) {
      setData(null);
      setSelectedRelationId(null);
      setError(null);
      setLoading(false);
      return;
    }

    // Immediately clear previous scan's data and reset all filters (T04, T06)
    setData(null);
    setSelectedRelationId(null);
    setSearchQuery("");
    setStatusFilter("all");
    setBasisFilter("all");
    setError(null);

    fetchGeography(scanId);
  }, [scanId, fetchGeography]);

  // Terminal lifecycle trigger: auto-refresh geography once terminal observations are stored (T05)
  useEffect(() => {
    if (!scanId) return;
    const isTerminal = ["completed", "partial", "failed", "cancelled"].includes(scanStatus || "");
    if (isTerminal && terminalRefetchedRef.current !== scanId) {
      terminalRefetchedRef.current = scanId;
      fetchGeography(scanId);
    }
  }, [scanId, scanStatus, fetchGeography]);

  const endpointsById = useMemo(() => {
    const map = new Map<string, GeoEndpoint>();
    if (data?.endpoints) {
      for (const ep of data.endpoints) {
        map.set(ep.id, ep);
      }
    }
    return map;
  }, [data?.endpoints]);

  const filteredRelations = useMemo(() => {
    if (!data?.relations) return [];

    return data.relations.filter((rel) => {
      const source = endpointsById.get(rel.source_endpoint_id);
      const target = endpointsById.get(rel.target_endpoint_id);

      // Search Filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesTarget =
          target?.display_name?.toLowerCase().includes(q) ||
          target?.ip?.toLowerCase().includes(q) ||
          target?.location?.city?.toLowerCase().includes(q) ||
          target?.location?.country?.toLowerCase().includes(q);
        const matchesSource =
          source?.display_name?.toLowerCase().includes(q) ||
          source?.executor_id?.toLowerCase().includes(q);
        const matchesStatus = rel.status_codes.some((code) => String(code).includes(q));

        if (!matchesTarget && !matchesSource && !matchesStatus) {
          return false;
        }
      }

      // Status Code Filter
      if (statusFilter !== "all") {
        if (statusFilter === "2xx" && !rel.status_codes.some((c) => c >= 200 && c < 300)) return false;
        if (statusFilter === "3xx" && !rel.status_codes.some((c) => c >= 300 && c < 400)) return false;
        if (statusFilter === "4xx" && !rel.status_codes.some((c) => c >= 400 && c < 500)) return false;
        if (statusFilter === "5xx" && !rel.status_codes.some((c) => c >= 500)) return false;
      }

      // Relation Basis Filter (T06)
      if (basisFilter !== "all" && rel.relation_basis !== basisFilter) {
        return false;
      }

      return true;
    });
  }, [data?.relations, endpointsById, searchQuery, statusFilter, basisFilter]);

  // Reconcile selection against filtered relations (T06)
  const selectedRelation = useMemo(() => {
    if (!selectedRelationId || !filteredRelations) return null;
    return filteredRelations.find((r) => r.id === selectedRelationId) || null;
  }, [selectedRelationId, filteredRelations]);

  const clearFilters = useCallback(() => {
    setSearchQuery("");
    setStatusFilter("all");
    setBasisFilter("all");
  }, []);

  return {
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
    // Alias webglSupported for backwards compatibility
    webglSupported: canvasSupported,
    setWebglSupported: setCanvasSupported,
    filteredRelations,
    endpointsById,
    clearFilters,
    refetch: () => scanId && fetchGeography(scanId),
  };
}
