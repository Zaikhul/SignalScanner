"use client";

import React, { useState } from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { webScanApiClient } from "@/lib/webScanApiClient";
import {
  FileText,
  Code,
  Database,
  Check,
  Copy,
  Warning,
  CircleNotch,
} from "@phosphor-icons/react";

export function WebScanExportMenu() {
  const { activeJob } = useWebScanStore();
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastExport, setLastExport] = useState<{
    filename: string;
    checksum: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  if (!activeJob) return null;

  async function handleDownload(format: "json" | "v2_json" | "txt" | "sql") {
    if (!activeJob) return;
    setDownloading(format);
    setError(null);
    setCopied(false);

    try {
      const { blob, filename, checksum } = await webScanApiClient.downloadExport(
        activeJob.id,
        format
      );

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setLastExport({ filename, checksum });
    } catch (err: any) {
      setError(err.message || "Gagal mengunduh berkas ekspor.");
    } finally {
      setDownloading(null);
    }
  }

  const handleCopyChecksum = () => {
    if (!lastExport?.checksum) return;
    navigator.clipboard.writeText(lastExport.checksum);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg p-4 mb-6 shadow-sm">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h4 className="text-xs font-semibold text-zinc-200">Ekspor Laporan Audit</h4>
          <p className="text-[11px] text-zinc-400">
            Unduh laporan audit diagnostik berintegritas kriptografis sesuai Rules of Engagement.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => handleDownload("json")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {downloading === "json" ? (
              <CircleNotch size={14} className="animate-spin text-blue-400" />
            ) : (
              <Code size={14} />
            )}
            <span>Native JSON</span>
          </button>

          <button
            onClick={() => handleDownload("v2_json")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {downloading === "v2_json" ? (
              <CircleNotch size={14} className="animate-spin text-blue-400" />
            ) : (
              <Code size={14} />
            )}
            <span>Ghost v2 JSON</span>
          </button>

          <button
            onClick={() => handleDownload("txt")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {downloading === "txt" ? (
              <CircleNotch size={14} className="animate-spin text-blue-400" />
            ) : (
              <FileText size={14} />
            )}
            <span>Text Report</span>
          </button>

          <button
            onClick={() => handleDownload("sql")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {downloading === "sql" ? (
              <CircleNotch size={14} className="animate-spin text-blue-400" />
            ) : (
              <Database size={14} />
            )}
            <span>SQL Logs</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3 p-2.5 rounded bg-red-950/40 border border-red-500/20 flex items-center justify-between text-xs text-red-300">
          <div className="flex items-center gap-2">
            <Warning size={14} className="text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {lastExport && (
        <div className="mt-3 pt-3 border-t border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[11px] text-zinc-400 font-mono">
          <div className="flex items-center gap-2">
            <Check size={14} className="text-emerald-400 shrink-0" />
            <span>Berkas:</span>
            <span className="text-zinc-200 font-semibold">{lastExport.filename}</span>
            <span className="text-zinc-600">|</span>
            <span className="text-zinc-500">SHA-256:</span>
            <span className="text-zinc-300 select-all truncate max-w-[280px]">
              {lastExport.checksum}
            </span>
          </div>

          <button
            type="button"
            onClick={handleCopyChecksum}
            aria-label="Salin checksum SHA-256"
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white transition focus:outline-none focus:ring-1 focus:ring-blue-500 self-start sm:self-auto"
          >
            {copied ? (
              <>
                <Check size={13} className="text-emerald-400" />
                <span className="text-emerald-400 font-medium">Tersalin!</span>
              </>
            ) : (
              <>
                <Copy size={13} />
                <span>Salin Checksum</span>
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
