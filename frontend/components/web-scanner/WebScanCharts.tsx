"use client";

import React from "react";
import { useWebScanStore } from "@/lib/webScanStore";

export function WebScanCharts() {
  const { snapshot, findings } = useWebScanStore();

  const req = snapshot?.result?.requests;
  const totalReq = req?.completed || 0;

  // Calculate findings by module
  const byModule: Record<string, number> = {};
  for (const f of findings) {
    byModule[f.module] = (byModule[f.module] || 0) + 1;
  }

  const moduleNames = ["recon", "headers", "cookies", "forms", "parameters", "header_probes", "stress"];
  const maxModuleCount = Math.max(...Object.values(byModule), 1);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      {/* Findings by Module Distribution */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <h4 className="text-xs font-semibold text-zinc-300 mb-3">Findings by Scanner Module</h4>
        <div className="space-y-2 text-xs">
          {moduleNames.map((mod) => {
            const count = byModule[mod] || 0;
            const pct = Math.round((count / maxModuleCount) * 100);
            return (
              <div key={mod} className="space-y-1">
                <div className="flex justify-between text-zinc-400 font-mono text-[11px]">
                  <span className="capitalize">{mod.replace("_", " ")}</span>
                  <span>{count}</span>
                </div>
                <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-300"
                    style={{ width: `${count > 0 ? Math.max(pct, 5) : 0}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* HTTP Traffic Status Distribution */}
      <div className="bg-zinc-900 border border-white/10 rounded-lg p-4">
        <h4 className="text-xs font-semibold text-zinc-300 mb-3">HTTP Response Status Breakdown</h4>
        {totalReq === 0 ? (
          <div className="text-xs text-zinc-500 py-6 text-center">No HTTP telemetry recorded yet.</div>
        ) : (
          <div className="space-y-3 text-xs">
            <div className="space-y-1">
              <div className="flex justify-between font-mono text-[11px] text-zinc-400">
                <span className="text-emerald-400">2xx / 3xx (Success & Redirects)</span>
                <span>{req?.http_2xx_3xx || 0}</span>
              </div>
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${Math.round(((req?.http_2xx_3xx || 0) / totalReq) * 100)}%` }}
                />
              </div>
            </div>

            <div className="space-y-1">
              <div className="flex justify-between font-mono text-[11px] text-zinc-400">
                <span className="text-amber-400">4xx (Client Errors & Not Found)</span>
                <span>{req?.http_4xx || 0}</span>
              </div>
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 rounded-full"
                  style={{ width: `${Math.round(((req?.http_4xx || 0) / totalReq) * 100)}%` }}
                />
              </div>
            </div>

            <div className="space-y-1">
              <div className="flex justify-between font-mono text-[11px] text-zinc-400">
                <span className="text-red-400">5xx (Server Errors)</span>
                <span>{req?.http_5xx || 0}</span>
              </div>
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-red-500 rounded-full"
                  style={{ width: `${Math.round(((req?.http_5xx || 0) / totalReq) * 100)}%` }}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
