"use client";

import { useEffect, useRef } from "react";
import { useScannerStore } from "@/lib/store";
import { MeasurementEvent } from "@/lib/types";

export function useSessionStream(sessionId?: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isClosingIntentionallyRef = useRef<boolean>(false);
  const lastSequenceRef = useRef<number>(0);

  const {
    setLastSequence,
    setConnectionState,
    setTargets,
    addBatchMeasurements,
    updateSessionStatus,
    addMarkerToSession,
    incrementDroppedFrames,
    updateAssociationState,
    upsertLanHost,
    setAdapterConflictNotice,
  } = useScannerStore();

  useEffect(() => {
    if (!sessionId) {
      setConnectionState("idle");
      return;
    }

    let isMounted = true;
    let retryCount = 0;
    isClosingIntentionallyRef.current = false;
    lastSequenceRef.current = 0;

    const connectWebSocket = () => {
      if (!isMounted || isClosingIntentionallyRef.current) return;

      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname || "127.0.0.1";
      const port = "8000";
      const currentSeq = lastSequenceRef.current;
      const wsUrl = `${wsProtocol}//${host}:${port}/ws/v1/sessions/${sessionId}?after_sequence=${currentSeq}`;

      setConnectionState("reconnecting");
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted || isClosingIntentionallyRef.current) return;
        setConnectionState("connected");
        retryCount = 0;

        // Clear any previous ping interval
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 15000);
      };

      ws.onmessage = (event) => {
        if (!isMounted || isClosingIntentionallyRef.current) return;
        try {
          const msg = JSON.parse(event.data);

          switch (msg.type) {
            case "session.snapshot":
              if (msg.targets && Array.isArray(msg.targets)) {
                setTargets(msg.targets);
              }
              if (msg.status) {
                updateSessionStatus(msg.status);
              }
              break;

            case "session.state_changed":
              if (msg.status) {
                updateSessionStatus(msg.status);
              }
              break;

            case "measurement.batch":
              if (msg.data && Array.isArray(msg.data)) {
                const seqTo = msg.sequence_to || (lastSequenceRef.current + 1);
                // Detect gap
                if (msg.sequence_from > lastSequenceRef.current + 1 && lastSequenceRef.current > 0) {
                  incrementDroppedFrames();
                }
                lastSequenceRef.current = seqTo;
                setLastSequence(seqTo);
                addBatchMeasurements(msg.data as MeasurementEvent[], { trace_id: msg.trace_id });
              }
              break;

            case "marker.added":
              if (msg.marker) {
                addMarkerToSession(msg.marker);
              }
              break;

            case "association.state_changed":
              if (msg.to_state) {
                updateAssociationState(msg.to_state);
                if (msg.to_state === "associating" || msg.to_state === "connected") {
                  setAdapterConflictNotice("Pemindaian AP dijeda karena radio aktif terhubung ke jaringan.");
                } else if (msg.to_state === "idle" || msg.to_state === "failed") {
                  setAdapterConflictNotice(null);
                }
              }
              break;

            case "association.address_acquired":
              if (msg.to_state) {
                updateAssociationState(msg.to_state, {
                  ipv4: msg.ipv4,
                  gateway: msg.gateway,
                  prefix: msg.prefix,
                });
                setAdapterConflictNotice("Pemindaian AP dijeda karena radio aktif terhubung ke jaringan.");
              }
              break;

            case "association.failed":
              updateAssociationState("failed");
              setAdapterConflictNotice(null);
              break;

            case "inventory.host_discovered":
            case "inventory.host_updated":
              if (msg.host) {
                upsertLanHost(msg.host);
              }
              break;

            case "channel.health_updated":
              if (msg.channels) {
                useScannerStore.getState().setChannelHealthSnapshot({
                  schema_version: msg.schema_version || "1.2",
                  snapshot_id: msg.snapshot_id,
                  session_id: msg.session_id,
                  band: msg.band,
                  channel_width_mhz: msg.channel_width_mhz || 20,
                  observation_window: msg.observation_window,
                  regulatory_domain: msg.regulatory_domain || { value: "ID", provenance: "configured", source: "org" },
                  channels: msg.channels,
                  quality_flags: msg.quality_flags || [],
                  created_at: msg.timestamp || new Date().toISOString(),
                });
              }
              break;

            case "channel.recommendation_updated":
              if (msg.recommendation) {
                useScannerStore.getState().setLatestRecommendation(msg.recommendation);
              }
              break;

            default:
              break;
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message", e);
        }
      };

      ws.onclose = (event) => {
        if (!isMounted || isClosingIntentionallyRef.current) return;
        setConnectionState("disconnected");
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);

        // Exponential backoff reconnect
        const delay = Math.min(8000, 1000 * Math.pow(1.5, retryCount) + Math.random() * 400);
        retryCount++;
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, delay);
      };

      ws.onerror = () => {
        if (!isMounted || isClosingIntentionallyRef.current) return;
        setConnectionState("disconnected");
      };
    };

    connectWebSocket();

    return () => {
      isMounted = false;
      isClosingIntentionallyRef.current = true;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [sessionId, setConnectionState, setTargets, addBatchMeasurements, updateSessionStatus, addMarkerToSession, incrementDroppedFrames, setLastSequence]);

  return { isConnected: wsRef.current?.readyState === WebSocket.OPEN };
}
