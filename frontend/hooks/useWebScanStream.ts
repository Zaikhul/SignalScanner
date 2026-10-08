"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE, webScanApiClient } from "@/lib/webScanApiClient";
import { useWebScanStore } from "@/lib/webScanStore";

export function useWebScanStream(scanId: string | null, enabled: boolean = true) {
  const [connectionState, setConnectionState] = useState<
    "disconnected" | "connecting" | "connected" | "error"
  >("disconnected");

  const wsRef = useRef<WebSocket | null>(null);
  const lastSequenceRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const fallbackPollRef = useRef<NodeJS.Timeout | null>(null);

  const {
    setSnapshot,
    setActiveJob,
    setProgress,
    setFindings,
    upsertFinding,
    addObservation,
    addEvent,
    setError,
  } = useWebScanStore();

  useEffect(() => {
    if (!scanId || !enabled) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (fallbackPollRef.current) {
        clearInterval(fallbackPollRef.current);
        fallbackPollRef.current = null;
      }
      setConnectionState("disconnected");
      return;
    }

    let isCancelled = false;
    lastSequenceRef.current = 0;

    const targetScanId = scanId;

    function reconcileTerminalData() {
      if (!targetScanId) return;
      webScanApiClient
        .getSnapshot(targetScanId)
        .then((snap) => {
          const currentJob = useWebScanStore.getState().activeJob;
          if ((!currentJob || currentJob.id === targetScanId) && snap) {
            setSnapshot(snap);
            if (snap.job) {
              setActiveJob(snap.job);
            }
          }
        })
        .catch(() => {});
      webScanApiClient
        .listFindings(targetScanId, { limit: 200 })
        .then((res) => {
          const currentJob = useWebScanStore.getState().activeJob;
          if ((!currentJob || currentJob.id === targetScanId) && res && res.items) {
            setFindings(res.items);
          }
        })
        .catch(() => {});
    }

    function applyEvent(data: any) {
      if (!data) return;

      // Drop duplicate or out-of-order events (F-13)
      if (typeof data.sequence === "number") {
        if (data.sequence <= lastSequenceRef.current) {
          return;
        }
        lastSequenceRef.current = data.sequence;
      }

      const { type, payload } = data;
      if (type === "snapshot" && payload) {
        setSnapshot(payload);
      } else if (type === "progress" && payload) {
        const pct =
          typeof payload.progress_percent === "number"
            ? payload.progress_percent
            : typeof payload.percent === "number"
            ? payload.percent
            : 0;
        const mod = payload.current_module || payload.module;
        setProgress(pct, mod);
      } else if (type === "state_changed" && payload) {
        const currentJob = useWebScanStore.getState().activeJob;
        const nextStatus =
          typeof payload === "string"
            ? payload
            : (payload.status || payload.state || (currentJob ? currentJob.status : ""));
        if (currentJob) {
          setActiveJob({ ...currentJob, status: nextStatus });
        }
        if (["completed", "failed", "partial", "cancelled"].includes(nextStatus)) {
          if (nextStatus === "completed") {
            setProgress(100, "completed");
          }
          // Auto-reconcile findings and snapshot on terminal state (F-12)
          reconcileTerminalData();
        }
      } else if (type === "finding_upserted" && payload) {
        upsertFinding(payload);
      } else if (type === "observation_added" && payload) {
        addObservation(payload);
      } else if (type === "completed" && payload) {
        setProgress(100, "completed");
        const currentJob = useWebScanStore.getState().activeJob;
        if (currentJob) {
          setActiveJob({ ...currentJob, status: "completed" });
        }
        reconcileTerminalData();
      } else if (type === "cancelled" && payload) {
        const currentJob = useWebScanStore.getState().activeJob;
        if (currentJob) {
          setActiveJob({ ...currentJob, status: "cancelled" });
        }
        reconcileTerminalData();
      } else if (type === "partial" && payload) {
        const currentJob = useWebScanStore.getState().activeJob;
        if (currentJob) {
          setActiveJob({ ...currentJob, status: "partial" });
        }
        reconcileTerminalData();
      } else if (type === "failed" && payload) {
        const currentJob = useWebScanStore.getState().activeJob;
        if (currentJob) {
          setActiveJob({ ...currentJob, status: "failed" });
        }
        reconcileTerminalData();
      }

      addEvent(data);
    }

    async function connect() {
      if (isCancelled) return;
      setConnectionState("connecting");

      try {
        // Obtain one-time ticket
        const { ticket } = await webScanApiClient.createStreamTicket(scanId!);
        if (isCancelled) return;

        const wsBase = API_BASE.replace(/^http/, "ws");
        const url = `${wsBase}/ws/v1/web-scans/${scanId}?ticket=${ticket}&after_sequence=${lastSequenceRef.current}`;
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (isCancelled) {
            ws.close();
            return;
          }
          setConnectionState("connected");

          // Keep-alive ping every 15s
          pingIntervalRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "ping" }));
            }
          }, 15000);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            applyEvent(data);
          } catch (err) {
            console.warn("Failed to parse web scan websocket message:", err);
          }
        };

        ws.onerror = () => {
          setConnectionState("error");
        };

        ws.onclose = () => {
          setConnectionState("disconnected");
          if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
          }
          // Attempt auto-reconnect if not cancelled and still active
          if (!isCancelled) {
            reconnectTimeoutRef.current = setTimeout(() => {
              connect();
            }, 3000);
          }
        };
      } catch (err: any) {
        if (!isCancelled) {
          setConnectionState("error");
          setError(err.message || "Failed to establish stream connection");
        }
      }
    }

    connect();

    // Fallback polling every 2s for when WebSocket is disconnected or missing events
    fallbackPollRef.current = setInterval(async () => {
      if (isCancelled || !scanId) return;
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        try {
          const events = await webScanApiClient.getEvents(scanId, lastSequenceRef.current);
          if (!isCancelled && events && events.length > 0) {
            for (const ev of events) {
              applyEvent(ev);
            }
          }
          const snap = await webScanApiClient.getSnapshot(scanId);
          if (!isCancelled && snap) {
            if (!["pending", "queued", "scanning"].includes(snap.job.status)) {
              setSnapshot(snap);
            }
          }
        } catch {
          // Ignore background polling errors
        }
      }
    }, 2000);

    return () => {
      isCancelled = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (fallbackPollRef.current) clearInterval(fallbackPollRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [scanId, enabled]);

  return { connectionState };
}
