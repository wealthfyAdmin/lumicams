"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Footprints,
  RefreshCw,
  TrendingUp,
  Radio,
  WifiOff,
  Users,
  Scan,
} from "lucide-react";
import { getCameras, getFootfallSummary } from "@/lib/api";
import { useAlertStore } from "@/hooks/useAlerts";
import { useRealtimeStore } from "@/stores/realtimeStore";
import { Camera, FootfallSummary } from "@/types";
import { formatTs, timeAgo } from "@/lib/utils";
import { CrowdZoneFramePanel } from "@/components/dashboard/CrowdZoneFramePanel";

export default function CrowdAnalyticsPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [footfall, setFootfall] = useState<FootfallSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(168);
  const [camFilter, setCamFilter] = useState<number | "all">("all");
  const [focusCamId, setFocusCamId] = useState<number | null>(null);
  const [refreshTs, setRefreshTs] = useState(Date.now());
  const dataRevision = useRealtimeStore((s) => s.dataRevision);
  const recentFootfall = useRealtimeStore((s) => s.recentFootfall);
  const latestCrowdMetrics = useRealtimeStore((s) => s.latestCrowdMetrics);
  const wsConnected = useAlertStore((s) => s.isConnected);
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
    }, 350);
    return () => clearTimeout(t);
  }, [dataRevision]);

  useEffect(() => {
    async function load() {
      const silent = skipNextSpinnerRef.current;
      skipNextSpinnerRef.current = false;
      if (!silent) setLoading(true);
      try {
        const cams = await getCameras();
        setCameras(cams);
        const camParam = camFilter === "all" ? undefined : camFilter;
        const f = await getFootfallSummary(hours, camParam);
        setFootfall(f);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [hours, camFilter, refreshTs]);

  useEffect(() => {
    if (focusCamId == null && cameras.length > 0) {
      setFocusCamId(cameras[0].id);
    }
  }, [cameras, focusCamId]);

  const maxDayTotal = useMemo(() => {
    if (!footfall?.by_day?.length) return 1;
    return Math.max(
      ...footfall.by_day.map((d) => d.entry + d.exit),
      1
    );
  }, [footfall]);

  const hourlySlice = useMemo(() => {
    if (!footfall?.hourly?.length) return [];
    return footfall.hourly.slice(-Math.min(footfall.hourly.length, 48));
  }, [footfall]);

  const { maxEntry: maxHourEntry, maxExit: maxHourExit } = useMemo(() => {
    if (!hourlySlice.length) return { maxEntry: 1, maxExit: 1 };
    return {
      maxEntry: Math.max(...hourlySlice.map((h) => h.entry), 1),
      maxExit: Math.max(...hourlySlice.map((h) => h.exit), 1),
    };
  }, [hourlySlice]);

  const filteredLive = useMemo(() => {
    if (camFilter === "all") return recentFootfall;
    return recentFootfall.filter((e) => e.camera_id === camFilter);
  }, [recentFootfall, camFilter]);

  const focusCam = useMemo(
    () => cameras.find((c) => c.id === focusCamId),
    [cameras, focusCamId]
  );

  const liveForFocus = useMemo(
    () => latestCrowdMetrics.find((m) => m.camera_id === focusCamId),
    [latestCrowdMetrics, focusCamId]
  );
  const totalPeopleNow = useMemo(
    () => latestCrowdMetrics.reduce((acc, m) => acc + Math.max(0, m.people_count), 0),
    [latestCrowdMetrics]
  );
  const totalZoneNow = useMemo(
    () =>
      latestCrowdMetrics.reduce(
        (acc, m) => acc + (m.roi_active ? Math.max(0, m.roi_count) : 0),
        0
      ),
    [latestCrowdMetrics]
  );

  return (
    <div className="space-y-8 fade-in">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1
            className="text-xl font-bold tracking-widest flex items-center gap-2"
            style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}
          >
            <Footprints className="w-6 h-6" />
            CROWD INTELLIGENCE
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            Full-frame & zone occupancy · footfall · flow
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="text-[10px] px-2 py-1 rounded flex items-center gap-1.5 font-mono"
            style={{
              border: "1px solid",
              borderColor: wsConnected ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)",
              color: wsConnected ? "#22c55e" : "#ef4444",
              background: wsConnected ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
            }}
            title="WebSocket — live crowd metrics and footfall"
          >
            {wsConnected ? (
              <>
                <Radio className="w-3 h-3" />
                REALTIME
              </>
            ) : (
              <>
                <WifiOff className="w-3 h-3" />
                WS OFFLINE
              </>
            )}
          </span>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="text-xs px-2 py-1.5 rounded"
            style={{ background: "var(--dash-alerts-bg)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-body-text)" }}
          >
            <option value={24}>Last 24h</option>
            <option value={168}>Last 7d</option>
            <option value={720}>Last 30d</option>
          </select>
          <select
            value={camFilter === "all" ? "all" : String(camFilter)}
            onChange={(e) =>
              setCamFilter(e.target.value === "all" ? "all" : Number(e.target.value))
            }
            className="text-xs px-2 py-1.5 rounded max-w-[200px]"
            style={{ background: "var(--dash-alerts-bg)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-body-text)" }}
          >
            <option value="all">All cameras (footfall)</option>
            {cameras.map((c) => (
              <option key={c.id} value={String(c.id)}>
                {c.name}
              </option>
            ))}
          </select>
          <button onClick={refresh} className="btn-aegis text-xs">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            REFRESH
          </button>
        </div>
      </div>

      <section className="aegis-card p-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Metric
            label="TOTAL PEOPLE NOW"
            value={wsConnected ? totalPeopleNow : 0}
            sub={wsConnected ? `${latestCrowdMetrics.length} active camera metrics` : "WS offline"}
            color="#00d4ff"
          />
          <Metric
            label="TOTAL IN ZONES"
            value={wsConnected ? totalZoneNow : 0}
            sub="Sum of ROI-active camera counts"
            color="#fbbf24"
          />
          <Metric
            label="FOCUS CAMERA PEOPLE"
            value={liveForFocus?.people_count ?? 0}
            sub={focusCam?.name ?? "Select camera below"}
            color="#22c55e"
          />
        </div>
      </section>

      {/* Footfall */}
      <section className="aegis-card p-5 space-y-4">
        <h2
          className="text-xs font-bold tracking-widest flex items-center gap-2"
          style={{ fontFamily: "var(--font-orbitron)", color: "#94a3b8" }}
        >
          <TrendingUp className="w-4 h-4" /> FOOTFALL ANALYTICS
        </h2>
        {loading || !footfall ? (
          <div className="py-12 flex justify-center">
            <div
              className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin"
              style={{ color: "#00d4ff" }}
            />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric label="ENTRY" value={footfall.totals.entry} color="#22c55e" />
              <Metric label="EXIT" value={footfall.totals.exit} color="#f97316" />
              <Metric label="NET FLOW" value={footfall.totals.net_flow} color="#00d4ff" />
              <Metric
                label="PEAK HOUR"
                value={footfall.peak_hour_total_crossings}
                sub={footfall.peak_hour ? formatTs(footfall.peak_hour) : "—"}
                color="#a78bfa"
              />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-2">
                <p className="text-[10px] tracking-widest" style={{ color: "#475569" }}>
                  HOURLY TRAFFIC (last {hourlySlice.length || "—"} h with data) — entry vs exit
                </p>
                {hourlySlice.length === 0 ? (
                  <p className="text-sm py-6" style={{ color: "#64748b" }}>
                    No hourly breakdown yet. When the processor runs with footfall enabled, crossings
                    appear here by the hour.
                  </p>
                ) : (
                  <div className="flex items-end gap-px h-32 overflow-x-auto pb-1">
                    {hourlySlice.map((row) => {
                      const total = row.entry + row.exit;
                      const he = Math.round((row.entry / maxHourEntry) * 100);
                      const hx = Math.round((row.exit / maxHourExit) * 100);
                      const label = formatTs(row.hour);
                      return (
                        <div
                          key={row.hour}
                          className="flex flex-col items-center gap-0.5 min-w-[10px] flex-1"
                          title={`${label}: entry ${row.entry}, exit ${row.exit} (total ${total})`}
                        >
                          <div className="flex gap-px w-full h-24 items-end justify-center">
                            <div
                              className="w-[45%] rounded-t bg-emerald-500/70 min-h-[3px]"
                              style={{ height: `${Math.max(he, total ? 4 : 0)}%` }}
                            />
                            <div
                              className="w-[45%] rounded-t bg-orange-500/70 min-h-[3px]"
                              style={{ height: `${Math.max(hx, total ? 4 : 0)}%` }}
                            />
                          </div>
                          <span className="text-[7px] text-center leading-tight opacity-70 truncate w-full" style={{ color: "#64748b" }}>
                            {new Date(row.hour).getHours()}h
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="flex gap-4 text-[10px]" style={{ color: "#64748b" }}>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm bg-emerald-500/80" /> Entry
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm bg-orange-500/80" /> Exit
                  </span>
                </div>
              </div>
              <div
                className="rounded-lg p-3 space-y-2"
                style={{ background: "rgba(15,23,42,0.5)", border: "1px solid #1a2540" }}
              >
                <p className="text-[10px] tracking-widest" style={{ color: "#475569" }}>
                  LIVE CROSSINGS (this session)
                </p>
                {!wsConnected && (
                  <p className="text-xs" style={{ color: "#94a3b8" }}>
                    Connect the dashboard WebSocket to see crossings as they happen.
                  </p>
                )}
                {wsConnected && filteredLive.length === 0 && (
                  <p className="text-xs" style={{ color: "#94a3b8" }}>
                    Waiting for line crossings… Processors must be running with footfall enabled.
                  </p>
                )}
                <ul className="space-y-1.5 max-h-40 overflow-y-auto text-xs">
                  {filteredLive.map((e, i) => (
                    <li
                      key={`${e.crossed_at}-${e.track_id}-${i}`}
                      className="flex justify-between gap-2"
                      style={{ color: "#cbd5e1" }}
                    >
                      <span className="truncate" title={e.camera_name}>
                        {e.camera_name || `Cam ${e.camera_id}`}
                      </span>
                      <span
                        className="shrink-0 font-mono"
                        style={{ color: e.direction === "entry" ? "#22c55e" : "#fb923c" }}
                      >
                        {e.direction.toUpperCase()}
                      </span>
                      <span className="shrink-0 opacity-70">{timeAgo(e.crossed_at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div>
              <p className="text-[10px] tracking-widest mb-2" style={{ color: "#475569" }}>
                DAILY TOTALS (entry + exit)
              </p>
              <div className="flex items-end gap-1 h-24">
                {footfall.by_day.slice(-14).map((d) => {
                  const t = d.entry + d.exit;
                  const h = Math.round((t / maxDayTotal) * 100);
                  return (
                    <div key={d.date} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                      <div
                        className="w-full rounded-t bg-cyan-500/40 border border-cyan-500/30"
                        style={{ height: `${Math.max(h, t ? 6 : 2)}%` }}
                        title={`${d.date}: in ${d.entry} / out ${d.exit}`}
                      />
                      <span
                        className="text-[8px] truncate w-full text-center"
                        style={{ color: "#2a3a5c" }}
                      >
                        {d.date.slice(5)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <ul className="space-y-1.5">
              {footfall.insights.map((t, i) => (
                <li key={i} className="text-sm" style={{ color: "#cbd5e1" }}>
                  · {t}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {/* Live crowd metrics */}
      <section className="aegis-card p-5 space-y-4">
        <h2
          className="text-xs font-bold tracking-widest flex items-center gap-2"
          style={{ fontFamily: "var(--font-orbitron)", color: "#94a3b8" }}
        >
          <Users className="w-4 h-4" /> LIVE OCCUPANCY & FLOW
        </h2>
        {!wsConnected ? (
          <p className="text-xs" style={{ color: "#94a3b8" }}>
            Realtime feed is offline. Start backend and keep WebSocket connected for live occupancy
            and flow.
          </p>
        ) : latestCrowdMetrics.length === 0 ? (
          <p className="text-xs" style={{ color: "#94a3b8" }}>
            Waiting for crowd metrics… Start camera processors with person detection.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {latestCrowdMetrics.map((m) => (
              <div
                key={m.camera_id}
                className="rounded-lg p-3 space-y-2"
                style={{
                  background: "rgba(15,23,42,0.5)",
                  border: `1px solid ${m.overcrowded ? "rgba(239,68,68,0.35)" : "#1a2540"}`,
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold truncate" style={{ color: "#e2e8f0" }}>
                    {m.camera_name || `Camera ${m.camera_id}`}
                  </p>
                  <span className="text-[10px] font-mono" style={{ color: "#64748b" }}>
                    {timeAgo(m.timestamp)}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <MetricSmall label="FRAME" value={m.people_count} color="#00d4ff" />
                  <MetricSmall
                    label="IN ZONE"
                    value={m.roi_active ? m.roi_count : null}
                    color="#fbbf24"
                  />
                </div>
                <div className="grid grid-cols-3 gap-1.5 text-center">
                  <div>
                    <p className="text-[9px] tracking-wider" style={{ color: "#475569" }}>
                      IN 60s
                    </p>
                    <p className="text-sm font-mono text-emerald-400">{m.entry_60s}</p>
                  </div>
                  <div>
                    <p className="text-[9px] tracking-wider" style={{ color: "#475569" }}>
                      OUT 60s
                    </p>
                    <p className="text-sm font-mono text-orange-400">{m.exit_60s}</p>
                  </div>
                  <div>
                    <p className="text-[9px] tracking-wider" style={{ color: "#475569" }}>
                      NET
                    </p>
                    <p className="text-sm font-mono" style={{ color: "#94a3b8" }}>
                      {m.net_60s}
                    </p>
                  </div>
                </div>
                {m.counterflow && (
                  <p className="text-[10px] text-violet-400 font-medium">Counter-flow (60s)</p>
                )}
                <p className="text-[10px]" style={{ color: m.overcrowded ? "#fca5a5" : "#64748b" }}>
                  {m.crowd_limit_enabled ? (
                    <>
                      Limit {m.limit_count}/{m.max_people}
                      {m.limit_basis === "zone"
                        ? " (zone)"
                        : m.limit_basis === "frame"
                          ? " (frame)"
                          : ""}{" "}
                      · {m.overcrowded ? "OVER LIMIT" : "OK"}
                    </>
                  ) : (
                    "Crowd limit off"
                  )}
                </p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Zone + frame (replaces abstract grid heatmap) */}
      <section className="aegis-card p-5 space-y-4">
        <h2
          className="text-xs font-bold tracking-widest flex items-center gap-2"
          style={{ fontFamily: "var(--font-orbitron)", color: "#94a3b8" }}
        >
          <Scan className="w-4 h-4" /> FRAME & ZONE MAP
        </h2>
        <p className="text-xs leading-relaxed" style={{ color: "#64748b" }}>
          The rectangle matches the <strong>crowd ROI</strong> from camera settings.{" "}
          <strong>Full frame</strong> is everyone in view; <strong>in zone</strong> counts people
          whose foot point falls inside the box. Enable <strong>Crowd limit</strong> to raise an
          overcrowd alert when the compared count (zone or full frame, per server{" "}
          <code className="text-cyan-500/80">CROWD_LIMIT_COUNT_MODE</code>) exceeds the maximum.
        </p>
        {cameras.length === 0 ? (
          <p className="text-sm py-8 text-center" style={{ color: "#64748b" }}>
            Add a camera to configure ROI and see live counts.
          </p>
        ) : (
          <CrowdZoneFramePanel
            cameras={cameras}
            selectedId={focusCamId}
            onSelectId={setFocusCamId}
            live={liveForFocus}
            lastRoiFromDb={focusCam?.last_crowd_roi_count}
            wsConnected={wsConnected}
          />
        )}
      </section>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: number;
  sub?: string;
  color: string;
}) {
  return (
    <div className="p-3 rounded-lg" style={{ background: "rgba(15,23,42,0.6)", border: "1px solid #1a2540" }}>
      <p className="text-[10px] tracking-widest" style={{ color: "#475569" }}>
        {label}
      </p>
      <p className="text-2xl font-bold mt-1" style={{ color, fontFamily: "var(--font-orbitron)" }}>
        {value}
      </p>
      {sub && (
        <p className="text-[10px] mt-0.5 truncate" style={{ color: "#64748b" }}>
          {sub}
        </p>
      )}
    </div>
  );
}

function MetricSmall({
  label,
  value,
  color,
}: {
  label: string;
  value: number | null;
  color: string;
}) {
  return (
    <div
      className="p-2 rounded-md text-center"
      style={{ background: "rgba(15,23,42,0.6)", border: "1px solid #1a2540" }}
    >
      <p className="text-[9px] tracking-wider" style={{ color: "#475569" }}>
        {label}
      </p>
      <p className="text-xl font-bold tabular-nums mt-0.5" style={{ color: value == null ? "#475569" : color, fontFamily: "var(--font-orbitron)" }}>
        {value == null ? "—" : value}
      </p>
    </div>
  );
}
