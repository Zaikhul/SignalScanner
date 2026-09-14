"use client";

import React from "react";
import { ChannelMetricEvidence } from "@/lib/types";
import { Broadcast, MegaphoneSimple, Cpu, Question } from "@phosphor-icons/react";

interface MethodBadgeProps {
  evidence: ChannelMetricEvidence;
  methodName?: string;
  className?: string;
}

export function MethodBadge({ evidence, methodName, className = "" }: MethodBadgeProps) {
  switch (evidence) {
    case "measured":
      return (
        <span
          title={methodName ? `Direct hardware measurement via ${methodName}` : "Direct hardware measurement"}
          className={`inline-flex items-center gap-1 rounded-md border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-400 ${className}`}
        >
          <Broadcast size={12} weight="bold" />
          Measured
        </span>
      );
    case "advertised":
      return (
        <span
          title={methodName ? `Advertised by beacon/AP IE via ${methodName}` : "Advertised in beacon payload"}
          className={`inline-flex items-center gap-1 rounded-md border border-indigo-500/30 bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-medium text-indigo-400 ${className}`}
        >
          <MegaphoneSimple size={12} weight="bold" />
          Advertised
        </span>
      );
    case "inferred":
      return (
        <span
          title={methodName ? `Algorithmic estimation via ${methodName}` : "Estimated/inferred from BSSID overlap calculation"}
          className={`inline-flex items-center gap-1 rounded-md border border-purple-500/30 bg-purple-500/10 px-1.5 py-0.5 text-[10px] font-medium text-purple-400 ${className}`}
        >
          <Cpu size={12} weight="bold" />
          Inferred
        </span>
      );
    default:
      return (
        <span
          title="Evidence source unknown or unsupported on this platform"
          className={`inline-flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400 ${className}`}
        >
          <Question size={12} weight="bold" />
          Unknown
        </span>
      );
  }
}
