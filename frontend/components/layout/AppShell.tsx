"use client";

import React from "react";
import { Header } from "./Header";
import { ConnectionBanner } from "./ConnectionBanner";
import { MarkerModal } from "../controls/MarkerModal";

export function AppShell({
  leftRail,
  centerStage,
  rightInspector,
}: {
  leftRail: React.ReactNode;
  centerStage: React.ReactNode;
  rightInspector: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col selection:bg-[var(--color-signal)] selection:text-zinc-950">
      <Header />
      <ConnectionBanner />

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[18rem_minmax(0,1fr)_22rem] overflow-hidden">
        {/* Left Rail (Controls, Mode, Collector) */}
        <aside className="border-r border-white/10 bg-zinc-950 p-4 lg:p-5 space-y-5 overflow-y-auto">
          {leftRail}
        </aside>

        {/* Center Stage (Radar Field & Mode Visualizers) */}
        <section className="p-4 lg:p-6 overflow-y-auto space-y-5 bg-[var(--color-canvas)]">
          {centerStage}
        </section>

        {/* Right Inspector (Target Details & Virtualized Table) */}
        <aside className="border-l border-white/10 bg-zinc-950 overflow-y-auto">
          {rightInspector}
        </aside>
      </main>

      <MarkerModal />
    </div>
  );
}
