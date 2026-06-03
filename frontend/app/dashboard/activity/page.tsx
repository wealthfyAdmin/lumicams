"use client";

import { useEffect, useState } from "react";
import { Activity, Flame, PersonStanding, HardHat, CheckCheck } from "lucide-react";
import { getAlerts, getAlertStats } from "@/lib/api";
import { Alert, AlertStats } from "@/types";
import { formatTs, timeAgo } from "@/lib/utils";

export default function ActivityPage() {
  const [recentAlerts, setRecentAlerts] = useState<Alert[]>([]);
  const [stats,        setStats]        = useState<AlertStats | null>(null);
  const [loading,      setLoading]      = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [alerts, st] = await Promise.all([
          getAlerts({ limit: 50 }),
          getAlertStats(168), // 7-day stats
        ]);
        setRecentAlerts(alerts);
        setStats(st);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="space-y-6 fade-in">
      <div>
        <h1 className="text-xl font-bold tracking-widest"
            style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}>
          ACTIVITY LOG
        </h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
          System events — last 7 days
        </p>
      </div>

      {/* 7-day stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "TOTAL (7D)",    value: stats.total,            color: "#94a3b8" },
            { label: "UNACKNOWLEDGED",value: stats.unacknowledged,   color: "#f59e0b" },
            { label: "FIRE EVENTS",   value: stats.by_type?.Fire ?? 0, color: "#ff6b35" },
            { label: "FALL EVENTS",   value: stats.by_type?.Fall ?? 0, color: "#fbbf24" },
            { label: "PPE EVENTS",    value: stats.by_type?.PPE ?? 0, color: "#f59e0b" },
            { label: "WEAPON EVENTS", value: stats.by_type?.Weapon ?? 0, color: "#ef4444" },
          ].map(({ label, value, color }) => (
            <div key={label} className="lumicams-card p-4 text-center">
              <p className="text-2xl font-bold" style={{ fontFamily: "var(--font-orbitron)", color }}>
                {value}
              </p>
              <p className="text-xs mt-1 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
                {label}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Timeline */}
      <div className="lumicams-card overflow-hidden">
        <div className="px-5 py-3" style={{ borderBottom: "1px solid var(--dash-sidebar-border)" }}>
          <h2 className="text-xs font-bold tracking-widest"
              style={{ fontFamily: "var(--font-orbitron)", color: "var(--dash-body-text)" }}>
            EVENT TIMELINE
          </h2>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin"
                 style={{ color: "#00d4ff" }} />
          </div>
        ) : recentAlerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-2">
            <Activity className="w-8 h-8 opacity-20" style={{ color: "#00d4ff" }} />
            <p className="text-sm" style={{ color: "var(--dash-meta)" }}>No events recorded yet.</p>
          </div>
        ) : (
          <div className="p-5 space-y-0">
            {recentAlerts.map((alert, idx) => {
              const isFire = alert.type === "Fire";
              const isPpe = alert.type === "PPE";
              return (
                <div key={alert.id} className="relative flex gap-4">
                  {/* Timeline line */}
                  {idx < recentAlerts.length - 1 && (
                    <div className="absolute left-4 top-8 bottom-0 w-px"
                         style={{ background: "var(--dash-sidebar-border)" }} />
                  )}

                  {/* Icon */}
                  <div
                    className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center z-10"
                    style={{
                      background: isFire ? "rgba(255,69,0,0.15)" : "rgba(245,158,11,0.15)",
                      border: `1px solid ${isFire ? "rgba(255,69,0,0.3)" : "rgba(245,158,11,0.3)"}`,
                    }}
                  >
                    {isFire
                      ? <Flame           className="w-3.5 h-3.5" style={{ color: "#ff6b35" }} />
                      : isPpe
                        ? <HardHat className="w-3.5 h-3.5" style={{ color: "#f59e0b" }} />
                      : <PersonStanding className="w-3.5 h-3.5" style={{ color: "#fbbf24" }} />
                    }
                  </div>

                  {/* Content */}
                  <div className="flex-1 pb-5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold"
                            style={{ color: isFire ? "#ff6b35" : "#fbbf24" }}>
                        {alert.type} Detected
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded"
                            style={{ background: "var(--live-alert-badge-bg)", color: "var(--dash-subtle)", fontFamily: "var(--font-space-mono)" }}>
                        Camera #{alert.camera_id}
                      </span>
                      {alert.confidence && (
                        <span className="text-xs" style={{ color: "var(--dash-meta)" }}>
                          {(parseFloat(alert.confidence) * 100).toFixed(1)}% conf.
                        </span>
                      )}
                      {alert.acknowledged && (
                        <span className="flex items-center gap-1 text-xs" style={{ color: "#22c55e" }}>
                          <CheckCheck className="w-3 h-3" /> Acknowledged
                        </span>
                      )}
                    </div>
                    <p className="text-xs mt-0.5"
                       style={{ color: "var(--dash-meta)", fontFamily: "var(--font-space-mono)" }}>
                      {formatTs(alert.timestamp)} · {timeAgo(alert.timestamp)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
