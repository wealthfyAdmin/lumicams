"use client";

import { useEffect, useRef } from "react";
import { create } from "zustand";
import { getWebSocketAlertsUrl } from "@/lib/wsUrl";
import { useRealtimeStore } from "@/stores/realtimeStore";
import { AlertBroadcast, CrowdMetricBroadcast } from "@/types";

let alertsSocketActive = false;

interface AlertStore {
  liveAlerts:   AlertBroadcast[];
  isConnected:  boolean;
  addAlert:     (a: AlertBroadcast) => void;
  clearAlerts:  () => void;
  setConnected: (v: boolean) => void;
}

/**
 * Global alert store.
 * Holds the last 50 live alerts received over WebSocket.
 */
export const useAlertStore = create<AlertStore>((set) => ({
  liveAlerts:   [],
  isConnected:  false,

  addAlert(a) {
    set((state) => ({
      // Prevent duplicate cards when same event is replayed/reconnected.
      liveAlerts: (
        state.liveAlerts.some((x) => {
          if (x.alert_id && a.alert_id) return x.alert_id === a.alert_id;
          return (
            x.type === a.type &&
            x.camera_id === a.camera_id &&
            x.timestamp === a.timestamp &&
            x.confidence === a.confidence
          );
        })
          ? state.liveAlerts
          : [a, ...state.liveAlerts]
      ).slice(0, 50),
    }));
  },

  clearAlerts() {
    set({ liveAlerts: [] });
  },

  setConnected(v) {
    set({ isConnected: v });
  },
}));

/**
 * Hook – opens / manages the WebSocket connection.
 * Call once in a top-level layout component; the store is globally shared.
 */
export function useAlertsWebSocket() {
  const wsRef     = useRef<WebSocket | null>(null);
  const pingRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const notifiedRef = useRef<Set<string>>(new Set());
  const addAlert  = useAlertStore((s) => s.addAlert);
  const setConn   = useAlertStore((s) => s.setConnected);

  useEffect(() => {
    let retryTimeout: ReturnType<typeof setTimeout>;
    if (alertsSocketActive) return;
    alertsSocketActive = true;

    function connect() {
      const url = getWebSocketAlertsUrl();
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConn(true);
        // Send a ping every 25 s to keep the connection alive
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ event: "ping" }));
          }
        }, 25_000);
      };

      ws.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data) as Record<string, unknown>;
          const kind = payload.event as string | undefined;
          if (kind === "pong") return;

          if (kind === "alert") {
            const p = payload as unknown as AlertBroadcast;
            addAlert(p);
            if (Notification.permission === "granted") {
              const notifKey = `${p.alert_id ?? ""}|${p.camera_id}|${p.type}|${p.timestamp}`;
              if (!notifiedRef.current.has(notifKey)) {
                notifiedRef.current.add(notifKey);
                if (notifiedRef.current.size > 200) {
                  const it = notifiedRef.current.values().next();
                  if (!it.done) notifiedRef.current.delete(it.value);
                }
                new Notification(`⚠ ${p.type} Detected`, {
                  body: `Camera: ${p.camera_name}  •  Confidence: ${p.confidence}`,
                  icon: "/favicon.ico",
                });
              }
            }
            return;
          }

          if (kind === "footfall") {
            const dir = payload.direction === "exit" ? "exit" : "entry";
            useRealtimeStore.getState().pushFootfall({
              camera_id: Number(payload.camera_id),
              camera_name: String(payload.camera_name ?? ""),
              direction: dir,
              crossed_at: String(payload.crossed_at ?? ""),
              track_id:
                payload.track_id !== undefined ? Number(payload.track_id) : undefined,
            });
            return;
          }

          if (kind === "heatmap_flush") {
            useRealtimeStore.getState().bumpData();
            return;
          }

          if (kind === "crowd_roi") {
            useRealtimeStore.getState().bumpData();
            return;
          }

          if (kind === "crowd_metric") {
            const p = payload as unknown as CrowdMetricBroadcast;
            const people = Number(p.people_count ?? 0);
            const roi = Number(p.roi_count ?? 0);
            const lim = p.limit_count != null ? Number(p.limit_count) : people;
            useRealtimeStore.getState().upsertCrowdMetric({
              camera_id: Number(p.camera_id),
              camera_name: String(p.camera_name ?? ""),
              timestamp: String(p.timestamp ?? ""),
              people_count: people,
              roi_count: roi,
              limit_count: lim,
              limit_basis: String(p.limit_basis ?? "none"),
              crowd_roi_enabled: Boolean(p.crowd_roi_enabled),
              roi_active: Boolean(p.roi_active),
              crowd_limit_enabled: Boolean(p.crowd_limit_enabled),
              max_people: Number(p.max_people ?? 0),
              overcrowded: Boolean(p.overcrowded),
              entry_60s: Number(p.entry_60s ?? 0),
              exit_60s: Number(p.exit_60s ?? 0),
              net_60s: Number(p.net_60s ?? 0),
              counterflow: Boolean(p.counterflow),
            });
          }
        } catch {
          /* ignore malformed messages */
        }
      };

      ws.onclose = () => {
        setConn(false);
        if (pingRef.current) clearInterval(pingRef.current);
        // Auto-reconnect after 3 s
        retryTimeout = setTimeout(connect, 3_000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    // Request notification permission
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }

    return () => {
      alertsSocketActive = false;
      clearTimeout(retryTimeout);
      if (pingRef.current) clearInterval(pingRef.current);
      wsRef.current?.close();
    };
  }, [addAlert, setConn]);
}
