"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  Camera, Flame, PersonStanding, Brain, Users,
  ShieldCheck, Shield, RefreshCw, AlertTriangle, UserRound, HardHat,
} from "lucide-react";
import CameraGrid from "@/components/cameras/CameraGrid";
import CameraTable from "@/components/cameras/CameraTable";
import { getAnalyticsOverview, getCameras } from "@/lib/api";
import { useRealtimeStore } from "@/stores/realtimeStore";
import { AnalyticsOverview, Camera as CameraType } from "@/types";

export default function DashboardPage() {
  const [cameras,   setCameras]   = useState<CameraType[]>([]);
  const [overview,  setOverview]  = useState<AnalyticsOverview | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [refreshTs, setRefreshTs] = useState(Date.now());
  const dataRevision = useRealtimeStore((s) => s.dataRevision);
  /** When true, the next load() skips the full-page spinner (keeps MJPEG feeds mounted). */
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

  const activeCams = cameras.filter((c) => c.status === "active").length;
  const overviewStats = [
    {
      title: "ACTIVE CAMERAS",
      value: activeCams,
      icon: Camera,
      color: "#00d4ff",
    },
    {
      title: "FIRE",
      value: overview?.by_type?.Fire ?? 0,
      icon: Flame,
      color: "#ff6b35",
    },
    {
      title: "FALL",
      value: overview?.by_type?.Fall ?? 0,
      icon: PersonStanding,
      color: "#fbbf24",
    },
    {
      title: "CROWD",
      value: overview?.by_type?.Crowd ?? 0,
      icon: Users,
      color: "#94a3b8",
    },
    {
      title: "FACE",
      value: overview?.by_type?.Face ?? 0,
      icon: UserRound,
      color: "#00d4ff",
    },
    {
      title: "PPE",
      value: overview?.by_type?.PPE ?? 0,
      icon: HardHat,
      color: "#94a3b8",
    },
    {
      title: "WEAPON",
      value: overview?.by_type?.Weapon ?? 0,
      icon: Shield,
      color: "#94a3b8",
    },
  ];

  return (
    <div className="space-y-6 fade-in">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-md font-bold tracking-widest" style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}>
            OVERVIEW
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            Real-time AI surveillance — last 24 h
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-2 btn-lumicams text-xs"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          REFRESH
        </button>
      </div>

      {/* Compact overview icons */}
      <div className="grid grid-cols-3 sm:grid-cols-4 xl:grid-cols-7 gap-2">
        {overviewStats.map(({ title, value, icon: Icon, color }) => (
          <button
            key={title}
            type="button"
            title={title}
            aria-label={title}
            className="group flex flex-col items-center justify-center gap-1 rounded-2xl border border-slate-300 bg-white px-3 py-3 text-slate-700 transition hover:bg-slate-50"
            style={{ minHeight: 88 }}
          >
            <span
              className="flex items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 p-2"
            >
              <Icon className="w-4 h-4" style={{ color }} />
            </span>
            <span className="text-sm font-semibold" style={{ color }}>
              {value}
            </span>
          </button>
        ))}
      </div>

      <div className="grid xl:grid-cols-2 gap-4">
        <div className="lumicams-card p-4">
          <h3 className="text-xs font-bold tracking-widest flex items-center gap-2"
              style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
            <AlertTriangle className="w-4 h-4" /> RISK SNAPSHOT
          </h3>
          <div className="mt-3 text-sm" style={{ color: "var(--dash-body-text)" }}>
            <p>Risk Level: <span className="uppercase font-bold">{overview?.summary?.risk_level ?? "unknown"}</span></p>
            <p className="mt-1">Alert Rate: {overview?.summary?.alert_rate_per_hour ?? 0} alerts/hour</p>
            <p className="mt-1">
              Top Camera: {overview?.top_cameras?.[0]?.camera_name ?? "N/A"}
              {" "}({overview?.top_cameras?.[0]?.alert_count ?? 0} alerts)
            </p>
          </div>
        </div>
        <div className="lumicams-card p-4">
          <h3 className="text-xs font-bold tracking-widest flex items-center gap-2"
              style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
            <Brain className="w-4 h-4" /> INTELLIGENT INSIGHTS
          </h3>
          <ul className="mt-3 space-y-2">
            {(overview?.intelligent_insights ?? ["No insights available yet."]).map((insight, idx) => (
              <li key={idx} className="text-sm" style={{ color: "var(--dash-body-text)" }}>
                - {insight}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="lumicams-card p-4">
        <h3
          className="text-xs font-bold tracking-widest mb-2"
          style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
        >
          HOW TO READ THIS DASHBOARD
        </h3>
        <div className="grid md:grid-cols-3 gap-3 text-xs" style={{ color: "var(--dash-body-text)" }}>
          <p><b>Fire/Fall:</b> safety incidents from visual AI models.</p>
          <p><b>Crowd events:</b> occupancy behavior alerts like Overcrowd, QueueHigh, CounterFlow.</p>
          <p><b>Face alerts:</b> blacklist matches from the Face Intelligence module (requires embeddings + enabled pipeline).</p>
          <p><b>PPE alerts:</b> missing selected safety gear on PPE-enabled cameras.</p>
          <p><b>Weapon alerts:</b> custom weapon YOLO + VLM second pass (police / security deployments).</p>
          <p><b>Risk snapshot:</b> combines alert rate and pending alerts to show operational urgency.</p>
        </div>
      </div>

      {/* Camera feed grid */}
      <div>
        <h2 className="text-xs font-bold tracking-widest mb-3"
            style={{ fontFamily: "var(--font-orbitron)", color: "var(--dash-subtle)" }}>
          LIVE FEEDS
        </h2>
        {loading ? (
          <div className="lumicams-card flex items-center justify-center py-12">
            <div className="flex flex-col items-center gap-3">
              <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin"
                   style={{ color: "#00d4ff" }} />
              <p className="text-xs" style={{ color: "var(--dash-subtle)" }}>Loading streams…</p>
            </div>
          </div>
        ) : (
          <CameraGrid cameras={cameras} onRefresh={refresh} />
        )}
      </div>

      {/* Camera management table */}
      <CameraTable cameras={cameras} onRefresh={refresh} />

      {/* System status footer */}
      <div className="flex items-center gap-2 text-xs pb-2" style={{ color: "var(--dash-meta)" }}>
        <ShieldCheck className="w-3.5 h-3.5" />
        <span>Lumicams · Fire + Fall + Crowd Intelligence · Realtime WS Alerts · JWT RBAC</span>
      </div>
    </div>
  );
}
