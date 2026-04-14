"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Brain,
  Flame,
  HardHat,
  PersonStanding,
  Shield,
  Users,
  RefreshCw,
  Video,
  VideoOff,
} from "lucide-react";
import { getAlerts, getCameraAnalytics, getCameraVideoSrc } from "@/lib/api";
import { Alert, CameraAnalytics } from "@/types";
import { formatTs, snapshotPathToUrl } from "@/lib/utils";

export default function CameraAnalyticsPage() {
  const params = useParams<{ id: string }>();
  const cameraId = Number(params.id);

  const [data, setData] = useState<CameraAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [snapshotAlerts, setSnapshotAlerts] = useState<Alert[]>([]);
  const [hours, setHours] = useState(72);
  const [streamKey, setStreamKey] = useState(() => Date.now());
  const [streamError, setStreamError] = useState(false);

  async function load(resetStream = false) {
    setLoading(true);
    try {
      const [analytics, camAlerts] = await Promise.all([
        getCameraAnalytics(cameraId, hours),
        getAlerts({ camera_id: cameraId, limit: 12 }),
      ]);
      setData(analytics);
      setSnapshotAlerts(
        (camAlerts as Alert[]).filter((a) => Boolean(a.snapshot_path)).slice(0, 8)
      );
      // Only reconnect the MJPEG stream when explicitly requested (manual Refresh button)
      // or when recovering from a stream error. Avoids blink on routine data polls.
      if (resetStream) {
        setStreamKey(Date.now());
        setStreamError(false);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!Number.isNaN(cameraId)) load(false);
  }, [cameraId, hours]); // eslint-disable-line react-hooks/exhaustive-deps

  const videoSrc = useMemo(
    () => (Number.isNaN(cameraId) ? "" : getCameraVideoSrc(cameraId, streamKey)),
    [cameraId, streamKey]
  );

  const isLive = data?.camera?.status === "active";

  const maxHour = useMemo(() => {
    if (!data?.hourly_trend?.length) return 1;
    return Math.max(...data.hourly_trend.map((h) => h.count), 1);
  }, [data]);

  return (
    <div className="space-y-8 fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <Link
            href="/dashboard/cameras"
            className="text-xs inline-flex items-center gap-1"
            style={{ color: "var(--dash-subtle)" }}
          >
            <ArrowLeft className="w-3.5 h-3.5" /> BACK TO CAMERAS
          </Link>
          <h1
            className="text-xl font-bold tracking-widest mt-1"
            style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}
          >
            CAMERA ANALYTICS
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            {data?.camera?.name ?? `Camera #${cameraId}`}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="text-xs px-2 py-1.5 rounded aegis-control"
          >
            <option value={24}>Last 24h</option>
            <option value={72}>Last 72h</option>
            <option value={168}>Last 7d</option>
          </select>
          <button onClick={() => load(true)} className="btn-aegis text-xs">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            REFRESH
          </button>
        </div>
      </div>

      {loading || !data ? (
        <div className="aegis-card py-16 flex justify-center">
          <div
            className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin"
            style={{ color: "#00d4ff" }}
          />
        </div>
      ) : (
        <>
          {/* Live footage — large hero */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <Video className="w-4 h-4" style={{ color: "#00d4ff" }} />
              <h2
                className="text-xs font-bold tracking-widest"
                style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
              >
                LIVE FOOTAGE
              </h2>
              {isLive && !streamError && (
                <span
                  className="text-[10px] px-2 py-0.5 rounded font-mono"
                  style={{ background: "rgba(34,197,94,0.12)", color: "#4ade80" }}
                >
                  PROCESSOR RUNNING
                </span>
              )}
            </div>
            <div
              className="aegis-card overflow-hidden p-0 border shadow-lg"
              style={{ borderColor: "var(--dash-sidebar-border)", boxShadow: "0 0 40px rgba(0,212,255,0.06)" }}
            >
              <div className="relative w-full max-w-6xl mx-auto aspect-video max-h-[75vh] min-h-[280px]" style={{ background: "var(--dash-alerts-bg)" }}>
                <span className="absolute top-3 left-3 w-6 h-6 border-t-2 border-l-2 z-10 opacity-50 pointer-events-none" style={{ borderColor: "#00d4ff" }} />
                <span className="absolute top-3 right-3 w-6 h-6 border-t-2 border-r-2 z-10 opacity-50 pointer-events-none" style={{ borderColor: "#00d4ff" }} />
                <span className="absolute bottom-3 left-3 w-6 h-6 border-b-2 border-l-2 z-10 opacity-50 pointer-events-none" style={{ borderColor: "#00d4ff" }} />
                <span className="absolute bottom-3 right-3 w-6 h-6 border-b-2 border-r-2 z-10 opacity-50 pointer-events-none" style={{ borderColor: "#00d4ff" }} />

                {isLive && !streamError && (
                  <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 bg-black/50 px-3 py-1 rounded-full">
                    <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    <span className="text-[11px] font-mono text-red-400 font-bold tracking-wider">LIVE</span>
                  </div>
                )}

                {isLive && !streamError ? (
                  <img
                    src={videoSrc}
                    alt={`${data.camera.name} live`}
                    className="absolute inset-0 w-full h-full object-contain"
                    onError={() => setStreamError(true)}
                  />
                ) : (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
                    <VideoOff className="w-14 h-14" style={{ color: "var(--dash-subtle)" }} />
                    <div>
                      <p className="text-sm font-semibold" style={{ color: "var(--dash-body-text)" }}>No live feed</p>
                      <p className="text-xs mt-2 max-w-md" style={{ color: "var(--dash-subtle)" }}>
                        {streamError
                          ? "Stream interrupted. Try Refresh, or check that the processor is running."
                          : "Start the camera processor from the Cameras page to view AI overlays (boxes, ROI, footfall) here."}
                      </p>
                    </div>
                    <Link href="/dashboard/cameras" className="btn-aegis text-xs mt-2">
                      GO TO CAMERAS
                    </Link>
                  </div>
                )}
              </div>
            </div>
            <p className="text-[10px] px-1" style={{ color: "var(--dash-subtle)" }}>
              Preview uses the same inference stream as the dashboard grid. Pause the camera to stop the feed.
            </p>
          </section>

          {/* Analytics below */}
          <section className="space-y-6 pt-2 border-t" style={{ borderColor: "var(--dash-sidebar-border)" }}>
            <h2
              className="text-xs font-bold tracking-widest flex items-center gap-2"
              style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
            >
              <Brain className="w-4 h-4" /> ANALYTICS &amp; ALERTS
            </h2>

            <div className="grid grid-cols-2 xl:grid-cols-7 gap-4">
              <Stat title="TOTAL ALERTS" value={data.summary.total_alerts} />
              <Stat title="UNACKNOWLEDGED" value={data.summary.unacknowledged_alerts} />
              <Stat title="FIRE ALERTS" value={data.summary.by_type?.Fire ?? 0} icon={<Flame className="w-4 h-4" />} />
              <Stat title="FALL ALERTS" value={data.summary.by_type?.Fall ?? 0} icon={<PersonStanding className="w-4 h-4" />} />
              <Stat title="CROWD ALERTS" value={data.summary.by_type?.Crowd ?? 0} icon={<Users className="w-4 h-4" />} />
              <Stat title="PPE ALERTS" value={data.summary.by_type?.PPE ?? 0} icon={<HardHat className="w-4 h-4" />} />
              <Stat title="WEAPON ALERTS" value={data.summary.by_type?.Weapon ?? 0} icon={<Shield className="w-4 h-4" />} />
            </div>

            <div className="aegis-card p-4">
              <h2
                className="text-xs font-bold tracking-widest mb-3"
                style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
              >
                MODELS TRIGGERING ALERTS
              </h2>
              <div className="grid sm:grid-cols-2 gap-3">
                {data.model_alerts.map((m) => (
                  <div
                    key={m.model}
                    className="p-3 rounded-md"
                    style={{ background: "var(--dash-alerts-bg)", border: "1px solid var(--dash-sidebar-border)" }}
                  >
                    <p className="text-sm font-semibold" style={{ color: "var(--dash-body-text)" }}>{m.model}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--dash-subtle)" }}>
                      {m.alert_type} alerts: {m.count}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="aegis-card p-4">
              <h2
                className="text-xs font-bold tracking-widest mb-3"
                style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
              >
                ALERT TREND (HOURLY)
              </h2>
              <div className="space-y-2">
                {data.hourly_trend.slice(-24).map((point) => (
                  <div key={point.hour} className="flex items-center gap-2">
                    <span
                      className="text-[10px] w-28"
                      style={{ color: "var(--dash-subtle)", fontFamily: "var(--font-space-mono)" }}
                    >
                      {formatTs(point.hour)}
                    </span>
                    <div
                      className="h-2 rounded bg-cyan-500/30"
                      style={{ width: `${(point.count / maxHour) * 100}%` }}
                    />
                    <span className="text-xs" style={{ color: "var(--dash-body-text)" }}>{point.count}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="aegis-card p-4">
              <h2
                className="text-xs font-bold tracking-widest mb-3 flex items-center gap-2"
                style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
              >
                <Brain className="w-4 h-4" /> INTELLIGENT RECOMMENDATIONS
              </h2>
              <ul className="space-y-2">
                {data.intelligent_recommendations.map((rec, idx) => (
                  <li key={idx} className="text-sm" style={{ color: "var(--dash-body-text)" }}>
                    - {rec}
                  </li>
                ))}
              </ul>
            </div>

            <div className="aegis-card p-4">
              <h2
                className="text-xs font-bold tracking-widest mb-3 flex items-center gap-2"
                style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
              >
                RECENT SNAPSHOTS (THIS CAMERA)
              </h2>
              {snapshotAlerts.length === 0 ? (
                <p className="text-xs" style={{ color: "var(--dash-subtle)" }}>
                  No snapshots yet for this camera in recent alerts.
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                  {snapshotAlerts.map((a) => (
                    <a
                      key={a.id}
                      href={snapshotPathToUrl(a.snapshot_path)}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-md overflow-hidden border"
                      style={{ borderColor: "var(--dash-sidebar-border)", background: "var(--dash-alerts-bg)" }}
                      title={`Alert #${a.id} · ${a.type} · ${formatTs(a.timestamp)}`}
                    >
                      <div className="aspect-video" style={{ background: "var(--dash-alerts-bg)" }}>
                        <img
                          src={snapshotPathToUrl(a.snapshot_path)}
                          alt={`Alert ${a.id} snapshot`}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="px-2 py-1.5">
                        <p className="text-[10px] font-semibold" style={{ color: "var(--dash-body-text)" }}>
                          #{a.id} · {a.type}
                        </p>
                        <p
                          className="text-[10px]"
                          style={{ color: "var(--dash-subtle)", fontFamily: "var(--font-space-mono)" }}
                        >
                          {formatTs(a.timestamp)}
                        </p>
                      </div>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ title, value, icon }: { title: string; value: number | string; icon?: ReactNode }) {
  return (
    <div className="aegis-card p-4">
      <p className="text-xs tracking-widest flex items-center gap-1.5" style={{ color: "var(--dash-subtle)" }}>
        {icon} {title}
      </p>
      <p className="text-2xl font-bold mt-1" style={{ color: "#00d4ff", fontFamily: "var(--font-orbitron)" }}>
        {value}
      </p>
    </div>
  );
}
