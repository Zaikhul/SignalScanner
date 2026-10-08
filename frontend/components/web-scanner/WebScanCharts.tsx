"use client";

import React from "react";
import { useWebScanStore } from "@/lib/webScanStore";

export function WebScanCharts() {
  const { snapshot, findings } = useWebScanStore();

  const req = snapshot?.result?.requests;
  const totalAttempted = req?.attempted || 0;
  const totalCompleted = req?.completed || 0;

  // Determine scanned modules from coverage
  const scannedModules = new Set<string>();
  if (snapshot?.result?.coverage) {
    for (const c of snapshot.result.coverage) {
      if (c.module) scannedModules.add(c.module);
    }
  }

  // Calculate findings by module
  const byModule: Record<string, number> = {};
  for (const f of findings) {
    byModule[f.module] = (byModule[f.module] || 0) + 1;
  }

  const moduleNames = [
    "recon",
    "headers",
    "cookies",
    "forms",
    "parameters",
    "header_probes",
    "stress",
  ];
  const maxModuleCount = Math.max(...Object.values(byModule), 1);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      {/* Findings by Module Distribution */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <h4 className="text-xs font-semibold text-zinc-300 mb-3">Temuan Berdasarkan Modul Pemindai</h4>
        <div className="space-y-2 text-xs">
          {moduleNames.map((mod) => {
            const isScanned = scannedModules.size === 0 || scannedModules.has(mod);
            const count = byModule[mod] || 0;
            const pct = Math.round((count / maxModuleCount) * 100);

            return (
              <div key={mod} className="space-y-1">
                <div className="flex justify-between text-zinc-400 font-mono text-[11px]">
                  <span className="capitalize">{mod.replace("_", " ")}</span>
                  <span>
                    {!isScanned ? (
                      <span className="text-zinc-600 italic">Tidak dipindai</span>
                    ) : (
                      count
                    )}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-300 ${
                      !isScanned ? "bg-zinc-700" : "bg-blue-500"
                    }`}
                    style={{ width: `${isScanned && count > 0 ? pct : 0}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* HTTP Traffic Status Distribution */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-semibold text-zinc-300">Distribusi Telemetri HTTP</h4>
          {totalCompleted > 0 && (
            <span className="text-[11px] font-mono text-zinc-500">
              {totalCompleted} selesai / {totalAttempted} upaya
            </span>
          )}
        </div>

        {totalCompleted === 0 && totalAttempted === 0 ? (
          <div className="text-xs text-zinc-500 py-6 text-center">
            Belum ada telemetri lalu lintas HTTP yang tercatat.
          </div>
        ) : (
          <div className="space-y-3 text-xs">
            {/* 2xx / 3xx */}
            <div className="space-y-1">
              <div className="flex justify-between font-mono text-[11px] text-zinc-400">
                <span className="text-emerald-400">2xx / 3xx (Sukses & Pengalihan)</span>
                <span>
                  {req?.http_2xx_3xx || 0}{" "}
                  <span className="text-zinc-500">
                    ({totalCompleted > 0 ? Math.round(((req?.http_2xx_3xx || 0) / totalCompleted) * 100) : 0}%)
                  </span>
                </span>
              </div>
              <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{
                    width: `${
                      totalCompleted > 0
                        ? Math.round(((req?.http_2xx_3xx || 0) / totalCompleted) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            {/* 4xx */}
            <div className="space-y-1">
              <div className="flex justify-between font-mono text-[11px] text-zinc-400">
                <span className="text-amber-400">4xx (Client Errors & Not Found)</span>
                <span>
                  {req?.http_4xx || 0}{" "}
                  <span className="text-zinc-500">
                    ({totalCompleted > 0 ? Math.round(((req?.http_4xx || 0) / totalCompleted) * 100) : 0}%)
                  </span>
                </span>
              </div>
              <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 rounded-full"
                  style={{
                    width: `${
                      totalCompleted > 0
                        ? Math.round(((req?.http_4xx || 0) / totalCompleted) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            {/* 5xx */}
            <div className="space-y-1">
              <div className="flex justify-between font-mono text-[11px] text-zinc-400">
                <span className="text-red-400">5xx (Server Errors)</span>
                <span>
                  {req?.http_5xx || 0}{" "}
                  <span className="text-zinc-500">
                    ({totalCompleted > 0 ? Math.round(((req?.http_5xx || 0) / totalCompleted) * 100) : 0}%)
                  </span>
                </span>
              </div>
              <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-red-500 rounded-full"
                  style={{
                    width: `${
                      totalCompleted > 0
                        ? Math.round(((req?.http_5xx || 0) / totalCompleted) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            {/* Network Failed */}
            <div className="space-y-1">
              <div className="flex justify-between font-mono text-[11px] text-zinc-400">
                <span className="text-rose-400">Kegagalan Jaringan (Transport Error)</span>
                <span>
                  {req?.network_failed || 0}{" "}
                  <span className="text-zinc-500">
                    ({totalAttempted > 0 ? Math.round(((req?.network_failed || 0) / totalAttempted) * 100) : 0}%)
                  </span>
                </span>
              </div>
              <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-rose-500 rounded-full"
                  style={{
                    width: `${
                      totalAttempted > 0
                        ? Math.round(((req?.network_failed || 0) / totalAttempted) * 100)
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            {/* Rate Limited */}
            {req && req.rate_limited > 0 && (
              <div className="pt-1 flex items-center justify-between text-[11px] font-mono text-zinc-400 border-t border-white/5">
                <span className="text-purple-400">Dibatasi Laju (HTTP 429 Rate Limited):</span>
                <span className="text-purple-300 font-semibold">{req.rate_limited} permintaan</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
