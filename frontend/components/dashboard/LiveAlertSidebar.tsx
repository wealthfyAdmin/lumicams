"use client";

import { Flame, PersonStanding, Users, UserRound, HardHat, Shield, X, CheckCheck } from "lucide-react";
import { useAlertStore } from "@/hooks/useAlerts";
import { AlertBroadcast } from "@/types";
import { formatTs, timeAgo } from "@/lib/utils";

function AlertItem({ alert }: { alert: AlertBroadcast }) {
  const isFire = alert.type === "Fire";
  const isCrowd = alert.type === "Crowd";
  const isFace = alert.type === "Face";
  const isPpe = alert.type === "PPE";
  const isWeapon = alert.type === "Weapon";
  const accent = isFire
    ? "#ff6b35"
    : isCrowd
      ? "#f43f5e"
      : isFace
        ? "#a78bfa"
        : isPpe
          ? "#f59e0b"
          : isWeapon
            ? "#ef4444"
            : "#fbbf24";

  const rowBg = isFire
    ? "rgba(255,69,0,0.06)"
    : isCrowd
      ? "rgba(244,63,94,0.08)"
      : isFace
        ? "rgba(139,92,246,0.07)"
        : isPpe
          ? "rgba(245,158,11,0.08)"
          : isWeapon
            ? "rgba(239,68,68,0.08)"
            : "rgba(245,158,11,0.06)";
  const rowBorder = isFire
    ? "rgba(255,69,0,0.2)"
    : isCrowd
      ? "rgba(244,63,94,0.25)"
      : isFace
        ? "rgba(139,92,246,0.22)"
        : isPpe
          ? "rgba(245,158,11,0.25)"
          : isWeapon
            ? "rgba(239,68,68,0.28)"
            : "rgba(245,158,11,0.2)";

  return (
    <div
      className="alert-enter flex gap-3 p-3 rounded-lg"
      style={{
        background: rowBg,
        border: `1px solid ${rowBorder}`,
      }}
    >
      {/* Icon */}
      <div
        className="shrink-0 flex items-center justify-center w-8 h-8 rounded"
        style={{
          background: isFire
            ? "rgba(255,69,0,0.15)"
            : isCrowd
              ? "rgba(244,63,94,0.16)"
              : isFace
                ? "rgba(139,92,246,0.14)"
                : isPpe
                  ? "rgba(245,158,11,0.18)"
                  : isWeapon
                    ? "rgba(239,68,68,0.16)"
                    : "rgba(245,158,11,0.15)",
          border: `1px solid ${
            isFire
              ? "rgba(255,69,0,0.3)"
              : isCrowd
                ? "rgba(244,63,94,0.35)"
                : isFace
                  ? "rgba(139,92,246,0.3)"
                  : isPpe
                    ? "rgba(245,158,11,0.35)"
                    : isWeapon
                      ? "rgba(239,68,68,0.35)"
                      : "rgba(245,158,11,0.3)"
          }`,
        }}
      >
        {isFire ? (
          <Flame className="w-4 h-4" style={{ color: accent }} />
        ) : isCrowd ? (
          <Users className="w-4 h-4" style={{ color: accent }} />
        ) : isFace ? (
          <UserRound className="w-4 h-4" style={{ color: accent }} />
        ) : isPpe ? (
          <HardHat className="w-4 h-4" style={{ color: accent }} />
        ) : isWeapon ? (
          <Shield className="w-4 h-4" style={{ color: accent }} />
        ) : (
          <PersonStanding className="w-4 h-4" style={{ color: accent }} />
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span
            className="text-xs font-bold tracking-wider"
            style={{ color: accent, fontFamily: "var(--font-orbitron)" }}
          >
            {alert.type.toUpperCase()}
          </span>
          {alert.confidence && (
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{
                background: "var(--live-alert-badge-bg)",
                color: "var(--live-alert-hint)",
                fontFamily: "var(--font-space-mono)",
              }}
            >
              {(parseFloat(alert.confidence) * 100).toFixed(0)}%
            </span>
          )}
        </div>
        <p className="text-xs mt-0.5 truncate" style={{ color: "var(--live-alert-sub)" }}>
          {alert.camera_name}
        </p>
        {alert.type === "Crowd" && (
          <p className="text-[10px] mt-0.5" style={{ color: "#fda4af" }}>
            {(alert.subtype ?? "Overcrowd").toUpperCase()}
            {alert.people_count != null && alert.max_people != null
              ? ` · ${alert.people_count}/${alert.max_people}`
              : ""}
          </p>
        )}
        <p className="text-xs mt-0.5" style={{ color: "var(--live-alert-time)", fontFamily: "var(--font-space-mono)" }}>
          {timeAgo(alert.timestamp)}
        </p>
        <p
          className="text-[10px] mt-0.5 opacity-90"
          style={{ color: "var(--live-alert-hint)", fontFamily: "var(--font-space-mono)" }}
        >
          {formatTs(alert.timestamp)}
        </p>
      </div>
    </div>
  );
}

export default function LiveAlertSidebar() {
  const liveAlerts  = useAlertStore((s) => s.liveAlerts);
  const clearAlerts = useAlertStore((s) => s.clearAlerts);
  const isConnected = useAlertStore((s) => s.isConnected);

  return (
    <aside className="dashboard-alerts-panel w-72 shrink-0 flex flex-col">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid var(--dash-alerts-border)" }}
      >
        <div className="flex items-center gap-2">
          <span className={`status-dot ${isConnected ? "active" : "error"}`} />
          <span
            className="text-xs font-bold tracking-widest"
            style={{ fontFamily: "var(--font-orbitron)", color: "var(--dash-body-text)" }}
          >
            LIVE ALERTS
          </span>
          {liveAlerts.length > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded-full font-bold"
                  style={{ background: "#ff4500", color: "#fff", fontSize: "10px" }}>
              {liveAlerts.length}
            </span>
          )}
        </div>
        {liveAlerts.length > 0 && (
          <button
            onClick={clearAlerts}
            className="flex items-center gap-1 text-xs transition-colors hover:opacity-70"
            style={{ color: "var(--dash-meta)" }}
            title="Clear all"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {liveAlerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <CheckCheck className="w-8 h-8 opacity-20" style={{ color: "#22c55e" }} />
            <p className="text-xs" style={{ color: "var(--dash-meta)" }}>
              {isConnected ? "All clear — monitoring active" : "Connecting to feed…"}
            </p>
          </div>
        ) : (
          liveAlerts.map((a) => (
            <AlertItem key={`${a.alert_id}-${a.timestamp}`} alert={a} />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 shrink-0" style={{ borderTop: "1px solid var(--dash-alerts-border)" }}>
        <p className="text-xs" style={{ color: "var(--dash-meta)", fontFamily: "var(--font-space-mono)" }}>
          WS · {isConnected ? "CONNECTED" : "RECONNECTING…"}
        </p>
      </div>
    </aside>
  );
}
