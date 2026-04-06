"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Flame, PersonStanding, Users, UserRound, HardHat, Shield, CheckCheck, Trash2,
  Loader2, ChevronLeft, ChevronRight, RefreshCw, Filter,
} from "lucide-react";
import { Alert, AlertType } from "@/types";
import { getAlerts, acknowledgeAlert, deleteAlert } from "@/lib/api";
import { formatTs } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import toast from "react-hot-toast";

const PAGE_SIZE = 20;

export default function AlertsPage() {
  const isAdmin = useAuth((s) => s.isAdmin);
  const [alerts,      setAlerts]      = useState<Alert[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [page,        setPage]        = useState(0);
  const [typeFilter,  setTypeFilter]  = useState<AlertType | "">("");
  const [ackFilter,   setAckFilter]   = useState<"" | "false" | "true">("");
  const [refreshTs,   setRefreshTs]   = useState(Date.now());

  const refresh = useCallback(() => setRefreshTs(Date.now()), []);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const params: Record<string, unknown> = {
          skip: page * PAGE_SIZE,
          limit: PAGE_SIZE,
        };
        if (typeFilter) params.alert_type = typeFilter;
        if (ackFilter !== "") params.acknowledged = ackFilter === "true";
        const data = await getAlerts(params);
        setAlerts(data);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [page, typeFilter, ackFilter, refreshTs]);

  async function handleAck(alert: Alert) {
    try {
      await acknowledgeAlert(alert.id);
      toast.success("Alert acknowledged.");
      refresh();
    } catch {
      toast.error("Acknowledge failed.");
    }
  }

  async function handleDelete(alert: Alert) {
    if (!confirm("Delete this alert record permanently?")) return;
    try {
      await deleteAlert(alert.id);
      toast.success("Alert deleted.");
      refresh();
    } catch {
      toast.error("Delete failed.");
    }
  }

  return (
    <div className="space-y-5 fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-widest" style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}>
            ALERT HISTORY
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>All AI-detected events</p>
        </div>
        <button onClick={refresh} className="btn-aegis text-xs">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          REFRESH
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter className="w-3.5 h-3.5" style={{ color: "var(--dash-subtle)" }} />
        {/* Type filter */}
        {(["", "Fire", "Fall", "Crowd", "Face", "PPE", "Weapon"] as const).map((t) => (
          <button
            key={t}
            onClick={() => { setTypeFilter(t); setPage(0); }}
            className="text-xs px-3 py-1.5 rounded-md font-semibold tracking-wider transition-all"
            style={typeFilter === t
              ? { background: "rgba(0,212,255,0.12)", border: "1px solid rgba(0,212,255,0.3)", color: "#00d4ff" }
              : { background: "rgba(71,85,105,0.08)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-subtle)" }
            }
          >
            {t === "" ? "ALL TYPES" : t.toUpperCase()}
          </button>
        ))}
        <span style={{ color: "var(--dash-sidebar-border)" }}>|</span>
        {(["", "false", "true"] as const).map((v) => (
          <button
            key={v}
            onClick={() => { setAckFilter(v); setPage(0); }}
            className="text-xs px-3 py-1.5 rounded-md font-semibold tracking-wider transition-all"
            style={ackFilter === v
              ? { background: "rgba(0,212,255,0.12)", border: "1px solid rgba(0,212,255,0.3)", color: "#00d4ff" }
              : { background: "rgba(71,85,105,0.08)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-subtle)" }
            }
          >
            {v === "" ? "ALL" : v === "false" ? "UNACKED" : "ACKED"}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="aegis-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full aegis-table">
            <thead>
              <tr>
                <th className="text-left">ID</th>
                <th className="text-left">TYPE</th>
                <th className="text-left">CAMERA</th>
                <th className="text-left">CONFIDENCE</th>
                <th className="text-left">TIMESTAMP</th>
                <th className="text-left">DETAILS</th>
                <th className="text-left">STATUS</th>
                <th className="text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto" style={{ color: "var(--dash-subtle)" }} />
                  </td>
                </tr>
              ) : alerts.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-sm" style={{ color: "var(--dash-meta)" }}>
                    No alerts match your filters.
                  </td>
                </tr>
              ) : (
                alerts.map((alert) => {
                  const isFire = alert.type === "Fire";
                  const isCrowd = alert.type === "Crowd";
                  const isFace = alert.type === "Face";
                  const isPpe = alert.type === "PPE";
                  const isWeapon = alert.type === "Weapon";
                  return (
                    <tr key={alert.id}>
                      <td style={{ color: "var(--dash-meta)", fontFamily: "var(--font-space-mono)" }}>#{alert.id}</td>
                      <td>
                        <span className={isFire ? "badge-fire" : isPpe ? "badge-crowd" : isWeapon ? "badge-fire" : "badge-fall"}>
                          {isFire ? (
                            <Flame className="w-3 h-3" />
                          ) : isCrowd ? (
                            <Users className="w-3 h-3" />
                          ) : isFace ? (
                            <UserRound className="w-3 h-3" />
                          ) : isPpe ? (
                            <HardHat className="w-3 h-3" />
                          ) : isWeapon ? (
                            <Shield className="w-3 h-3" />
                          ) : (
                            <PersonStanding className="w-3 h-3" />
                          )}
                          {alert.type}
                        </span>
                      </td>
                      <td style={{ color: "var(--dash-body-text)" }}>#{alert.camera_id}</td>
                      <td style={{ color: "var(--dash-subtle)", fontFamily: "var(--font-space-mono)" }}>
                        {alert.confidence
                          ? `${(parseFloat(alert.confidence) * 100).toFixed(1)}%`
                          : "—"
                        }
                      </td>
                      <td style={{ color: "var(--dash-subtle)", fontSize: "0.75rem", fontFamily: "var(--font-space-mono)" }}>
                        {formatTs(alert.timestamp)}
                      </td>
                      <td style={{ color: "var(--dash-body-text)", maxWidth: 240 }}>
                        <span className="text-xs truncate block" title={alert.notes ?? ""}>
                          {alert.notes ?? "—"}
                        </span>
                      </td>
                      <td>
                        {alert.acknowledged ? (
                          <span className="text-xs flex items-center gap-1" style={{ color: "#22c55e" }}>
                            <CheckCheck className="w-3 h-3" /> ACK
                          </span>
                        ) : (
                          <span className="text-xs blink" style={{ color: "#f59e0b" }}>PENDING</span>
                        )}
                      </td>
                      <td>
                        <div className="flex items-center justify-end gap-2">
                          {!alert.acknowledged && (
                            <button
                              onClick={() => handleAck(alert)}
                              className="p-1.5 rounded transition-all"
                              style={{ color: "#22c55e", background: "rgba(34,197,94,0.08)" }}
                              title="Acknowledge"
                            >
                              <CheckCheck className="w-3.5 h-3.5" />
                            </button>
                          )}
                          {isAdmin && (
                            <button
                              onClick={() => handleDelete(alert)}
                              className="p-1.5 rounded transition-all"
                              style={{ color: "#ef4444", background: "rgba(239,68,68,0.08)" }}
                              title="Delete"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-5 py-3" style={{ borderTop: "1px solid var(--dash-sidebar-border)" }}>
          <span className="text-xs" style={{ color: "var(--dash-meta)" }}>
            Page {page + 1} · {PAGE_SIZE} per page
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1.5 rounded disabled:opacity-30"
              style={{ color: "var(--dash-subtle)", border: "1px solid var(--dash-sidebar-border)" }}
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={alerts.length < PAGE_SIZE}
              className="p-1.5 rounded disabled:opacity-30"
              style={{ color: "var(--dash-subtle)", border: "1px solid var(--dash-sidebar-border)" }}
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
