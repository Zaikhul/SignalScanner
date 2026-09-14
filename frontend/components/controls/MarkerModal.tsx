"use client";

import React, { useState } from "react";
import { BookmarkSimple, X } from "@phosphor-icons/react";
import { apiClient } from "@/lib/apiClient";
import { useScannerStore } from "@/lib/store";

export function MarkerModal() {
  const { markerModalOpen, setMarkerModalOpen, activeSession, addMarkerToSession } = useScannerStore();
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);

  if (!markerModalOpen || !activeSession) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!label.trim()) return;

    setLoading(true);
    try {
      const marker = await apiClient.addMarker(activeSession.id, label.trim(), notes.trim() || undefined);
      addMarkerToSession(marker);
      setLabel("");
      setNotes("");
      setMarkerModalOpen(false);
    } catch (e) {
      console.error("Failed to add marker", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-[var(--color-surface)] border border-white/10 rounded-[var(--radius-panel)] p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in duration-150">
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <div className="flex items-center gap-2 text-zinc-100 font-semibold text-sm">
            <BookmarkSimple size={18} className="text-[var(--color-signal)]" />
            <span>Tambah Marker Kejadian</span>
          </div>
          <button
            type="button"
            onClick={() => setMarkerModalOpen(false)}
            className="text-zinc-400 hover:text-zinc-100 transition p-1"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3 text-xs">
          <div>
            <label className="block text-zinc-300 font-medium mb-1">Nama Marker / Momen *</label>
            <input
              type="text"
              required
              autoFocus
              placeholder="Contoh: Berpindah ke Lantai 2, Dinding Partisi"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full bg-[var(--color-surface-raised)] border border-white/15 rounded-[var(--radius-control)] px-3 py-2 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-[var(--color-signal)]"
            />
          </div>

          <div>
            <label className="block text-zinc-300 font-medium mb-1">Catatan Tambahan (Opsional)</label>
            <textarea
              rows={3}
              placeholder="Keterangan lingkungan atau interferensi..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full bg-[var(--color-surface-raised)] border border-white/15 rounded-[var(--radius-control)] px-3 py-2 text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-[var(--color-signal)] resize-none"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setMarkerModalOpen(false)}
              className="px-3 py-2 rounded-[var(--radius-control)] border border-white/10 text-zinc-300 hover:bg-white/5 transition"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={loading || !label.trim()}
              className="px-4 py-2 rounded-[var(--radius-control)] bg-[var(--color-signal)] text-zinc-950 font-semibold hover:opacity-90 transition disabled:opacity-50"
            >
              {loading ? "Menyimpan..." : "Simpan Marker"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
