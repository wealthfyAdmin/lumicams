"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Camera, BellRing, Flame, PersonStanding, Brain, Users,
  ShieldCheck, Shield, RefreshCw, AlertTriangle, UserRound, HardHat,
  TrendingUp, Activity, Clock3, BarChart3,
} from "lucide-react";
import StatCard from "@/components/dashboard/StatCard";
import CameraGrid from "@/components/cameras/CameraGrid";
import CameraTable from "@/components/cameras/CameraTable";
import { getAnalyticsOverview, getCameras } from "@/lib/api";
import { useRealtimeStore } from "@/stores/realtimeStore";
import { AnalyticsOverview, Camera as CameraType } from "@/types";

const RISK_COLOR: Record<string, { text: string; bg: string; border: string; pct: number }> = {
  low:    { text: "#22c55e", bg: "rgba(34,197,94,0.10)",    border: "rgba(34,197,94,0.3)",   pct: 20 },
  medium: { text: "#fbbf24", bg: "rgba(251,191,36,0.10)",   border: "rgba(251,191,36,0.3)",  pct: 55 },
  high:   { text: "#ff6b35", bg: "rgba(255,107,53,0.12)",   border: "rgba(255,107,53,0.35)", pct: 90 },
};

const ALERT_TYPE_META: { key: string; label: string; color: string; bg: string }[] = [
  { key: "Fire",   label: "Fire",   color: "#ff6b35", bg: "rgba(255,107,53,0.15)"  },
  { key: "Fall",   label: "Fall",   color: "#fbbf24", bg: "rgba(251,191,36,0.12)"  },
  { key: "Crowd",  label: "Crowd",  color: "#f43f5e", bg: "rgba(244,63,94,0.12)"   },
  { key: "Face",   label: "Face",   color: "#a78bfa", bg: "rgba(167,139,250,0.12)" },
  { key: "PPE",    label: "PPE",    color: "#f59e0b", bg: "rgba(245,158,11,0.12)"  },
  { key: "Weapon", label: "Weapon", color: "#ef4444", bg: "rgba(239,68,68,0.12)"   },
];

export default function DashboardPage() {
  const [cameras,   setCameras]   = useState<CameraType[]>([]);
  const [overview,  setOverview]  = useState<AnalyticsOverview | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [refreshTs, setRefreshTs] = useState(Date.now());
  const dataRevision = useRealtimeStore((s) => s.dataRevision);
  const skipNextSpinnerRef = useRef(false);

  const refresh = useCallback(() => {
    skipNextSpinnerRef.current = false;
    setRefreshTs(Date.now());
  }, []);

  useEffect(() => {
    if (dataRevision === 0) return;
    const t = setTimeout(() => {
      skipNextSpinnerRef.current = true;
      setRefreshTs(Date.now());
    }, 450);
    return () => clearTimeout(t);
  }, [dataRevision]);

  useEffect(() => {
    async function load() {
      const silent = skipNextSpinnerRef.current;
      skipNextSpinnerRef.current = false;
      if (!silent) setLoading(true);
      try {
        const [cams, ov] = await Promise.all([getCameras(), getAnalyticsOverview(24)]);
        setCameras(cams);
        setOverview(ov);
      } catch {
        /* handled by axios interceptor */
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [refreshTs]);

  const activeCams  = cameras.filter((c) => c.status === "active").length;
  const totalAlerts = overview?.summary?.total_alerts ?? 0;
  const riskKey     = (overview?.summary?.risk_level ?? "low") as "low" | "medium" | "high";
  const risk        = RISK_COLOR[riskKey];

  // compute max alert count across types for bar scaling
  const typeEntries = ALERT_TYPE_META.map((m) => ({ ...m, count: overview?.by_type?.[m.key] ?? 0 }));
  const maxTypeCount = Math.max(1, ...typeEntries.map((t) => t.count));

  // hourly sparkline data
  const hourly = overview?.hourly_trend ?? [];
  const maxHourly = Math.max(1, ...hourly.map((h) => h.count));

  return (
    <div className="space-y-5 fade-in">
      {/* ── Page header ───────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1
            className="text-xl font-bold tracking-widest"
            style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}
          >
            OVERVIEW
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            Real-time AI surveillance — last 24 h
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-2 btn-aegis text-xs"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          REFRESH
        </button>
      </div>

      {/* ── Stat cards ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-4 2xl:grid-cols-8 gap-3">
        <StatCard
          title="ACTIVE CAMERAS"
          value={activeCams}
          icon={Camera}
          color="cyan"
          subtitle={`${cameras.length} total configured`}
          fillPct={cameras.length > 0 ? (activeCams / cameras.length) * 100 : 0}
        />
        <StatCard
          title="TOTAL ALERTS (24H)"
          value={overview?.summary?.total_alerts ?? "—"}
          icon={BellRing}
          color="muted"
          subtitle={`${overview?.summary?.unacknowledged_alerts ?? 0} unacknowledged`}
          fillPct={overview ? Math.min(100, (overview.summary.unacknowledged_alerts / Math.max(1, overview.summary.total_alerts)) * 100) : 0}
        />
        <StatCard
          title="FIRE DETECTIONS"
          value={overview?.by_type?.Fire ?? 0}
          icon={Flame}
          color="fire"
          pulse={!!overview?.by_type?.Fire}
          subtitle="via YOLO-class fire/smoke"
          fillPct={totalAlerts > 0 ? ((overview?.by_type?.Fire ?? 0) / totalAlerts) * 100 : 0}
        />
        <StatCard
          title="FALL DETECTIONS"
          value={overview?.by_type?.Fall ?? 0}
          icon={PersonStanding}
          color="fall"
          pulse={!!overview?.by_type?.Fall}
          subtitle="via MediaPipe Pose"
          fillPct={totalAlerts > 0 ? ((overview?.by_type?.Fall ?? 0) / totalAlerts) * 100 : 0}
        />
        <StatCard
          title="CROWD EVENTS"
          value={overview?.by_type?.Crowd ?? 0}
          icon={Users}
          color="muted"
          pulse={!!overview?.by_type?.Crowd}
          subtitle="overcrowd / counter-flow / queue"
          fillPct={totalAlerts > 0 ? ((overview?.by_type?.Crowd ?? 0) / totalAlerts) * 100 : 0}
        />
        <StatCard
          title="FACE ALERTS"
          value={overview?.by_type?.Face ?? 0}
          icon={UserRound}
          color="cyan"
          pulse={!!overview?.by_type?.Face}
          subtitle="blacklist / watchlist"
          fillPct={totalAlerts > 0 ? ((overview?.by_type?.Face ?? 0) / totalAlerts) * 100 : 0}
        />
        <StatCard
          title="PPE ALERTS"
          value={overview?.by_type?.PPE ?? 0}
          icon={HardHat}
          color="fall"
          pulse={!!overview?.by_type?.PPE}
          subtitle="missing equipment compliance"
          fillPct={totalAlerts > 0 ? ((overview?.by_type?.PPE ?? 0) / totalAlerts) * 100 : 0}
        />
        <StatCard
          title="WEAPON ALERTS"
          value={overview?.by_type?.Weapon ?? 0}
          icon={Shield}
          color="fire"
          pulse={!!overview?.by_type?.Weapon}
          subtitle="YOLO + VLM verification"
          fillPct={totalAlerts > 0 ? ((overview?.by_type?.Weapon ?? 0) / totalAlerts) * 100 : 0}
        />
      </div>

      {/* ── Middle row: Risk + Insights + Alert breakdown ─────── */}
      <div className="grid xl:grid-cols-3 gap-4">

        {/* Risk Snapshot */}
        <div className="aegis-card p-5 flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" style={{ color: "#fbbf24" }} />
            <h3
              className="text-xs font-bold tracking-widest"
              style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
            >
              RISK SNAPSHOT
            </h3>
          </div>

          {/* Risk level badge */}
          <div
            className="flex items-center justify-between px-4 py-3 rounded-lg"
            style={{ background: risk.bg, border: `1px solid ${risk.border}` }}
          >
            <div>
              <p className="text-[10px] tracking-widest" style={{ color: "var(--dash-subtle)" }}>CURRENT LEVEL</p>
              <p
                className="text-2xl font-black tracking-widest mt-0.5 uppercase"
                style={{ fontFamily: "var(--font-orbitron)", color: risk.text }}
              >
                {riskKey}
              </p>
            </div>
            <div className="relative w-14 h-14">
              <svg viewBox="0 0 56 56" className="w-full h-full -rotate-90">
                <circle cx="28" cy="28" r="22" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
                <circle
                  cx="28" cy="28" r="22" fill="none"
                  stroke={risk.text}
                  strokeWidth="5"
                  strokeDasharray={`${(risk.pct / 100) * 138.2} 138.2`}
                  strokeLinecap="round"
                  style={{ filter: `drop-shadow(0 0 4px ${risk.text})` }}
                />
              </svg>
              <span
                className="absolute inset-0 flex items-center justify-center text-[10px] font-bold"
                style={{ color: risk.text, fontFamily: "var(--font-orbitron)" }}
              >
                {risk.pct}%
              </span>
            </div>
          </div>

          <div className="space-y-2 text-xs" style={{ color: "var(--dash-body-text)" }}>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5"><Activity className="w-3.5 h-3.5" style={{ color: "#00d4ff" }} /> Alert Rate</span>
              <span className="font-bold" style={{ fontFamily: "var(--font-space-mono)" }}>
                {overview?.summary?.alert_rate_per_hour ?? 0} /hr
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5"><TrendingUp className="w-3.5 h-3.5" style={{ color: "#00d4ff" }} /> Top Camera</span>
              <span className="font-bold text-right max-w-[140px] truncate" style={{ fontFamily: "var(--font-space-mono)", color: "#00d4ff" }}>
                {overview?.top_cameras?.[0]?.camera_name ?? "N/A"}
              </span>
            </div>
            {overview?.top_cameras?.[0] && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5"><BarChart3 className="w-3.5 h-3.5" style={{ color: "#00d4ff" }} /> Alerts</span>
                <span className="font-bold" style={{ fontFamily: "var(--font-space-mono)" }}>
                  {overview.top_cameras[0].alert_count}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Intelligent Insights */}
        <div className="aegis-card p-5 flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4" style={{ color: "#a78bfa" }} />
            <h3
              className="text-xs font-bold tracking-widest"
              style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
            >
              INTELLIGENT INSIGHTS
            </h3>
          </div>
          <ul className="flex-1 space-y-2.5">
            {(overview?.intelligent_insights?.length
              ? overview.intelligent_insights
              : ["No insights available yet."]
            ).map((insight, idx) => (
              <li
                key={idx}
                className="flex gap-2 text-xs leading-relaxed rounded-md px-3 py-2"
                style={{
                  color: "var(--dash-body-text)",
                  background: "rgba(167,139,250,0.05)",
                  border: "1px solid rgba(167,139,250,0.1)",
                }}
              >
                <span style={{ color: "#a78bfa", fontWeight: "bold", flexShrink: 0 }}>›</span>
                {insight}
              </li>
            ))}
          </ul>
        </div>

        {/* Alert type breakdown chart */}
        <div className="aegis-card p-5 flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4" style={{ color: "#00d4ff" }} />
            <h3
              className="text-xs font-bold tracking-widest"
              style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
            >
              ALERT BREAKDOWN
            </h3>
          </div>
          <div className="flex-1 space-y-2.5">
            {typeEntries.map((t) => (
              <div key={t.key} className="space-y-1">
                <div className="flex items-center justify-between text-[10px]">
                  <span style={{ color: "var(--dash-body-text)" }}>{t.label}</span>
                  <span style={{ color: t.color, fontFamily: "var(--font-space-mono)", fontWeight: "bold" }}>{t.count}</span>
                </div>
                <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${(t.count / maxTypeCount) * 100}%`,
                      background: t.color,
                      boxShadow: t.count > 0 ? `0 0 6px ${t.color}88` : "none",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Hourly trend sparkline ─────────────────────────────── */}
      {hourly.length > 0 && (
        <div className="aegis-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Clock3 className="w-4 h-4" style={{ color: "#00d4ff" }} />
            <h3
              className="text-xs font-bold tracking-widest"
              style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
            >
              24-HOUR ALERT TREND
            </h3>
          </div>
          <div className="flex items-end gap-1 h-16">
            {hourly.map((h, i) => {
              const pct = (h.count / maxHourly) * 100;
              const label = new Date(h.hour).getHours().toString().padStart(2, "0") + ":00";
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1 group" title={`${label} — ${h.count} alerts`}>
                  <div className="w-full flex items-end justify-center" style={{ height: "52px" }}>
                    <div
                      className="w-full rounded-t transition-all duration-500"
                      style={{
                        height: `${Math.max(2, pct)}%`,
                        background: h.count > 0
                          ? `linear-gradient(180deg, #00d4ff, rgba(0,212,255,0.4))`
                          : "rgba(255,255,255,0.06)",
                        boxShadow: h.count > 0 ? "0 0 6px rgba(0,212,255,0.4)" : "none",
                      }}
                    />
                  </div>
                  {i % 4 === 0 && (
                    <span className="text-[8px]" style={{ color: "var(--dash-meta)", fontFamily: "var(--font-space-mono)" }}>
                      {label}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── How to read ───────────────────────────────────────── */}
      <div className="aegis-card p-5">
        <h3
          className="text-xs font-bold tracking-widest mb-4 flex items-center gap-2"
          style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
        >
          <ShieldCheck className="w-4 h-4" style={{ color: "#00d4ff" }} />
          HOW TO READ THIS DASHBOARD
        </h3>
        <div className="grid md:grid-cols-3 gap-3">
          {[
            { label: "Fire / Fall",     desc: "Safety incidents from visual AI models.",                                               color: "#ff6b35" },
            { label: "Crowd Events",    desc: "Occupancy behavior alerts — Overcrowd, QueueHigh, CounterFlow.",                        color: "#f43f5e" },
            { label: "Face Alerts",     desc: "Blacklist matches from Face Intelligence (requires embeddings + enabled pipeline).",     color: "#a78bfa" },
            { label: "PPE Alerts",      desc: "Missing selected safety gear on PPE-enabled cameras.",                                  color: "#f59e0b" },
            { label: "Weapon Alerts",   desc: "Custom weapon YOLO + VLM second-pass (police / security deployments).",                 color: "#ef4444" },
            { label: "Risk Snapshot",   desc: "Combines alert rate and pending alerts to show operational urgency.",                   color: "#fbbf24" },
          ].map(({ label, desc, color }) => (
            <div
              key={label}
              className="flex gap-3 rounded-lg px-3 py-2.5 text-xs"
              style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}
            >
              <div className="mt-0.5 w-2 h-2 rounded-full shrink-0" style={{ background: color, boxShadow: `0 0 6px ${color}88` }} />
              <div>
                <p className="font-bold tracking-wide mb-0.5" style={{ color }}>{label}</p>
                <p style={{ color: "var(--dash-body-text)" }}>{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Live feeds ────────────────────────────────────────── */}
      <div>
        <h2
          className="text-xs font-bold tracking-widest mb-3 flex items-center gap-2"
          style={{ fontFamily: "var(--font-orbitron)", color: "var(--dash-subtle)" }}
        >
          <Camera className="w-3.5 h-3.5" />
          LIVE FEEDS
        </h2>
        {loading ? (
          <div className="aegis-card flex items-center justify-center py-16">
            <div className="flex flex-col items-center gap-3">
              <div
                className="w-7 h-7 border-2 border-t-transparent rounded-full animate-spin"
                style={{ borderColor: "#00d4ff", borderTopColor: "transparent" }}
              />
              <p className="text-xs" style={{ color: "var(--dash-subtle)" }}>Loading streams…</p>
            </div>
          </div>
        ) : (
          <CameraGrid cameras={cameras} onRefresh={refresh} />
        )}
      </div>

      {/* ── Camera management table ───────────────────────────── */}
      <CameraTable cameras={cameras} onRefresh={refresh} />

      {/* ── System status footer ──────────────────────────────── */}
      <div className="flex items-center gap-2 text-xs pb-2" style={{ color: "var(--dash-meta)" }}>
        <ShieldCheck className="w-3.5 h-3.5" />
        <span>Lumicams · Fire + Fall + Crowd Intelligence · Realtime WS Alerts · JWT RBAC</span>
      </div>
    </div>
  );
}
