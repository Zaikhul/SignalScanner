"use client";

import React, { useState } from "react";
import { useWebScanStore } from "@/lib/webScanStore";
import { webScanApiClient } from "@/lib/webScanApiClient";
import { DownloadSimple, FileText, Code, Database, Check } from "@phosphor-icons/react";

export function WebScanExportMenu() {
  const { activeJob } = useWebScanStore();
  const [downloading, setDownloading] = useState<string | null>(null);
  const [lastChecksum, setLastChecksum] = useState<string | null>(null);

  if (!activeJob) return null;

  async function handleDownload(format: "json" | "v2_json" | "txt" | "sql") {
    if (!activeJob) return;
    setDownloading(format);
    setLastChecksum(null);

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

      setLastChecksum(checksum);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-lg p-4 mb-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h4 className="text-xs font-semibold text-zinc-200">Export Audit Deliverables</h4>
          <p className="text-[11px] text-zinc-400">
            Download cryptographic audit reports in compliance with Rules of Engagement.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => handleDownload("json")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50"
          >
            <Code size={14} />
            <span>Native JSON</span>
          </button>

          <button
            onClick={() => handleDownload("v2_json")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50"
          >
            <Code size={14} />
            <span>Ghost v2 JSON</span>
          </button>

          <button
            onClick={() => handleDownload("txt")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50"
          >
            <FileText size={14} />
            <span>Text Report</span>
          </button>

          <button
            onClick={() => handleDownload("sql")}
            disabled={downloading !== null}
            className="px-3 py-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium border border-white/5 flex items-center gap-1.5 transition disabled:opacity-50"
          >
            <Database size={14} />
            <span>SQL Logs</span>
          </button>
        </div>
      </div>

      {lastChecksum && (
        <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-2 text-[11px] text-zinc-400 font-mono">
          <Check size={14} className="text-emerald-400" />
          <span>SHA-256 Checksum:</span>
          <span className="text-zinc-200 select-all">{lastChecksum}</span>
        </div>
      )}
    </div>
  );
}
