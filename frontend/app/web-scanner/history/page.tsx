"use client";

import React from "react";
import Link from "next/link";
import { Header } from "@/components/layout/Header";
import { WebScanHistory } from "@/components/web-scanner/WebScanHistory";
import { ArrowLeft } from "@phosphor-icons/react";

export default function WebScanHistoryPage() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      <Header />

      <main className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto space-y-6">
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <Link
            href="/web-scanner"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-100 transition"
          >
            <ArrowLeft size={14} />
            <span>Back to Web Scanner</span>
          </Link>
        </div>

        <WebScanHistory />
      </main>
    </div>
  );
}
