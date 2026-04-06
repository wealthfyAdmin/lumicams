"use client";

import { useMemo } from "react";
import type { Camera } from "@/types";
import type { CrowdMetricLiveEvent } from "@/stores/realtimeStore";
import { formatTs } from "@/lib/utils";

type Props = {
  cameras: Camera[];
  selectedId: number | null;
  onSelectId: (id: number) => void;
  live: CrowdMetricLiveEvent | undefined;
  lastRoiFromDb: number | undefined;
  wsConnected: boolean;
};

/** Schematic 16:9 frame with ROI rectangle (normalized 0–1 from camera). */
export function CrowdZoneFramePanel({
  cameras,
  selectedId,
  onSelectId,
  live,
  lastRoiFromDb,
  wsConnected,
}: Props) {
  const cam = useMemo(
    () => cameras.find((c) => c.id === selectedId),
    [cameras, selectedId]
  );

  const roi = useMemo(() => {
    if (!cam) return { x1: 0.22, y1: 0.28, x2: 0.78, y2: 0.72 };
    const x1 = cam.crowd_roi_x1 ?? 0.22;
    const y1 = cam.crowd_roi_y1 ?? 0.28;
    const x2 = cam.crowd_roi_x2 ?? 0.78;
    const y2 = cam.crowd_roi_y2 ?? 0.72;
    return {
      x1: Math.min(x1, x2),
      y1: Math.min(y1, y2),
      x2: Math.max(x1, x2),
      y2: Math.max(y1, y2),
    };
  }, [cam]);

  const basisLabel = (b: string) => {
    if (b === "zone") return "Zone (rectangle)";
    if (b === "frame") return "Full frame";
    return "—";
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div
        className="rounded-xl overflow-hidden relative aspect-video max-h-[320px] mx-auto w-full border"
        style={{
          background: "linear-gradient(145deg, #0a1020 0%, #0f172a 50%, #0c1222 100%)",
          borderColor: "#1e3a5f",
        }}
      >
        <svg
          viewBox="0 0 100 56.25"
          className="w-full h-full block"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden
        >
          <defs>
            <pattern id="crowd-grid" width="6.25" height="6.25" patternUnits="userSpaceOnUse">
              <path
                d="M 6.25 0 L 0 0 0 6.25"
                fill="none"
                stroke="rgba(0,212,255,0.06)"
                strokeWidth="0.15"
              />
            </pattern>
          </defs>
          <rect width="100" height="56.25" fill="url(#crowd-grid)" />
          <rect
            x="0"
            y="0"
            width="100"
            height="56.25"
            fill="none"
            stroke="rgba(148,163,184,0.25)"
            strokeWidth="0.35"
          />
          <rect
            x={roi.x1 * 100}
            y={roi.y1 * 56.25}
            width={(roi.x2 - roi.x1) * 100}
            height={(roi.y2 - roi.y1) * 56.25}
            fill="rgba(255,200,100,0.08)"
            stroke="rgba(255,200,100,0.85)"
            strokeWidth="0.5"
            rx="0.6"
          />
          <text
            x={roi.x1 * 100 + 1.2}
            y={roi.y1 * 56.25 + 4}
            fill="rgba(255,220,160,0.95)"
            fontSize="3.2"
            fontFamily="var(--font-orbitron), ui-sans-serif, system-ui"
          >
            ZONE
          </text>
        </svg>
        <div
          className="absolute bottom-2 left-2 right-2 flex flex-wrap gap-2 justify-between items-end pointer-events-none"
        >
          <span
            className="text-[9px] px-2 py-0.5 rounded font-mono"
            style={{
              background: "rgba(15,23,42,0.85)",
              border: "1px solid rgba(0,212,255,0.25)",
              color: "#94a3b8",
            }}
          >
            Schematic · matches camera ROI in settings
          </span>
        </div>
      </div>

      <div className="space-y-4 flex flex-col justify-center">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs" style={{ color: "#475569" }}>
            Camera
          </span>
          <select
            value={selectedId ?? ""}
            onChange={(e) => onSelectId(Number(e.target.value))}
            className="text-xs px-2 py-1.5 rounded flex-1 max-w-xs"
            style={{ background: "#0d1527", border: "1px solid #1a2540", color: "#94a3b8" }}
          >
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {!wsConnected ? (
          <p className="text-xs" style={{ color: "#94a3b8" }}>
            Connect WebSocket for live counts. Last saved zone count from DB:{" "}
            <span className="font-mono text-cyan-400/90">{lastRoiFromDb ?? "—"}</span>
          </p>
        ) : !live || live.camera_id !== selectedId ? (
          <p className="text-xs" style={{ color: "#94a3b8" }}>
            No live metrics for this camera yet. Start the processor with person detection. If the
            camera is running, counts will appear here. Zone (last DB):{" "}
            <span className="font-mono text-cyan-400/90">{lastRoiFromDb ?? "—"}</span>
          </p>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div
                className="rounded-lg p-4 text-center"
                style={{ background: "rgba(15,23,42,0.65)", border: "1px solid #1a2540" }}
              >
                <p className="text-[10px] tracking-widest mb-1" style={{ color: "#64748b" }}>
                  FULL FRAME
                </p>
                <p
                  className="text-4xl font-bold tabular-nums"
                  style={{ color: "#00d4ff", fontFamily: "var(--font-orbitron)" }}
                >
                  {live.people_count}
                </p>
                <p className="text-[10px] mt-1" style={{ color: "#475569" }}>
                  All people in view
                </p>
              </div>
              <div
                className="rounded-lg p-4 text-center"
                style={{
                  background: "rgba(15,23,42,0.65)",
                  border: `1px solid ${
                    live.roi_active ? "rgba(255,200,100,0.35)" : "#1a2540"
                  }`,
                }}
              >
                <p className="text-[10px] tracking-widest mb-1" style={{ color: "#64748b" }}>
                  IN ZONE
                </p>
                <p
                  className="text-4xl font-bold tabular-nums"
                  style={{
                    color: live.roi_active ? "#fbbf24" : "#475569",
                    fontFamily: "var(--font-orbitron)",
                  }}
                >
                  {live.roi_active ? live.roi_count : "—"}
                </p>
                <p className="text-[10px] mt-1" style={{ color: "#475569" }}>
                  {live.roi_active
                    ? "Foot points inside rectangle"
                    : "Enable crowd ROI or footfall zone"}
                </p>
              </div>
            </div>

            <div
              className="rounded-lg p-3 space-y-2"
              style={{ background: "rgba(15,23,42,0.5)", border: "1px solid #1a2540" }}
            >
              <p className="text-[10px] tracking-widest" style={{ color: "#475569" }}>
                CROWD LIMIT (ALERT)
              </p>
              {live.crowd_limit_enabled ? (
                <>
                  <p className="text-sm" style={{ color: "#e2e8f0" }}>
                    <span className="font-mono text-cyan-300">{live.limit_count}</span>
                    <span style={{ color: "#64748b" }}> / </span>
                    <span className="font-mono">{live.max_people}</span>
                    <span className="text-xs ml-2" style={{ color: "#475569" }}>
                      ({basisLabel(live.limit_basis)})
                    </span>
                  </p>
                  <p
                    className="text-xs font-semibold"
                    style={{ color: live.overcrowded ? "#f87171" : "#22c55e" }}
                  >
                    {live.overcrowded ? "OVER LIMIT — OVERCROWD ALERT" : "Within limit"}
                  </p>
                </>
              ) : (
                <p className="text-xs" style={{ color: "#64748b" }}>
                  Crowd limit is off. Turn it on in Camera → Crowd limit to alert when the chosen
                  count (zone or frame) exceeds max.
                </p>
              )}
              <p className="text-[10px] pt-1" style={{ color: "#475569" }}>
                Updated {formatTs(live.timestamp)} ·{" "}
                {live.counterflow ? (
                  <span style={{ color: "#a78bfa" }}>Counter-flow pattern (60s)</span>
                ) : (
                  <span>Flow: in {live.entry_60s} / out {live.exit_60s} (60s)</span>
                )}
              </p>
            </div>
          </div>
        )}

        {!cam?.crowd_roi_enabled && (
          <p className="text-[10px] leading-relaxed" style={{ color: "#475569" }}>
            <strong>Tip:</strong> enable <strong>Crowd ROI</strong> on this camera and drag the
            rectangle to define the zone. With <strong>Crowd limit</strong> on, the backend uses
            zone counts by default when ROI is active (<code className="text-cyan-600/90">CROWD_LIMIT_COUNT_MODE=auto</code> in
            server env).
          </p>
        )}
      </div>
    </div>
  );
}
