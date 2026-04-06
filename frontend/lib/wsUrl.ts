import Cookies from "js-cookie";

/**
 * Builds the WebSocket URL for the FastAPI alert/realtime feed.
 *
 * Priority:
 * 1. NEXT_PUBLIC_WS_URL — full URL, e.g. ws://127.0.0.1:8001/ws/alerts
 * 2. NEXT_PUBLIC_API_URL — if absolute (http/https), same host with ws/wss + /ws/alerts
 * 3. Browser: same host as the page (Next.js dev proxy) → /ws/alerts
 *
 * Appends `?token=` from the auth cookie so tenant-scoped realtime works.
 */

export function getWebSocketAlertsUrl(): string {
  const token = typeof window !== "undefined" ? Cookies.get("aegis_token") : undefined;
  const suffix = token ? `?token=${encodeURIComponent(token)}` : "";

  if (typeof window === "undefined") {
    return `ws://127.0.0.1:8000/ws/alerts${suffix}`;
  }

  const explicit = process.env.NEXT_PUBLIC_WS_URL;
  if (explicit?.startsWith("ws://") || explicit?.startsWith("wss://")) {
    if (!token) return explicit;
    const join = explicit.includes("?") ? "&" : "?";
    return `${explicit}${join}token=${encodeURIComponent(token)}`;
  }

  const api = process.env.NEXT_PUBLIC_API_URL ?? "";
  if (api.startsWith("http://") || api.startsWith("https://")) {
    try {
      const u = new URL(api);
      const wsProto = u.protocol === "https:" ? "wss:" : "ws:";
      const base = `${wsProto}//${u.host}`;
      return `${base}/ws/alerts${suffix}`;
    } catch {
      /* fall through */
    }
  }

  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/alerts${suffix}`;
}
