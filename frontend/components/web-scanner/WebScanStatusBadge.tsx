"use client";

import React from "react";
import { ScanState } from "@/lib/webScanTypes";
import {
  CheckCircle,
  WarningCircle,
  XCircle,
  Clock,
  Spinner,
  Prohibit,
} from "@phosphor-icons/react";

interface Props {
  status?: ScanState | string | null;
  size?: "sm" | "md";
}

export function WebScanStatusBadge({ status, size = "md" }: Props) {
  const s = (status ? String(status) : "unknown").toLowerCase().trim();

  let colorClasses = "bg-zinc-800 text-zinc-300 border-zinc-700";
  let icon = <Clock size={14} />;
  let label: string = status ? String(status) : "Unknown";

  if (s === "pending" || s === "queued") {
    colorClasses = "bg-amber-950/40 text-amber-300 border-amber-500/30";
    icon = <Clock size={14} className="animate-pulse" />;
    label = s === "queued" ? "Queued" : "Pending";
  } else if (s === "scanning") {
    colorClasses = "bg-blue-950/40 text-blue-300 border-blue-500/30";
    icon = <Spinner size={14} className="animate-spin" />;
    label = "Scanning...";
  } else if (s === "success" || s === "completed") {
    colorClasses = "bg-emerald-950/40 text-emerald-300 border-emerald-500/30";
    icon = <CheckCircle size={14} weight="fill" />;
    label = "Completed";
  } else if (s === "partial") {
    colorClasses = "bg-amber-950/40 text-amber-300 border-amber-500/30";
    icon = <WarningCircle size={14} />;
    label = "Partial";
  } else if (s === "failed") {
    colorClasses = "bg-red-950/40 text-red-300 border-red-500/30";
    icon = <XCircle size={14} weight="fill" />;
    label = "Failed";
  } else if (s === "cancelled") {
    colorClasses = "bg-zinc-800/80 text-zinc-400 border-zinc-700";
    icon = <Prohibit size={14} />;
    label = "Cancelled";
  } else if (s === "timeout" || s === "timed_out") {
    colorClasses = "bg-orange-950/40 text-orange-300 border-orange-500/30";
    icon = <WarningCircle size={14} />;
    label = "Timed Out";
  } else if (s === "interrupted") {
    colorClasses = "bg-purple-950/40 text-purple-300 border-purple-500/30";
    icon = <WarningCircle size={14} />;
    label = "Interrupted";
  }

  const px = size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded font-mono font-medium border uppercase tracking-wider ${colorClasses} ${px}`}
    >
      {icon}
      <span>{label}</span>
    </span>
  );
}
