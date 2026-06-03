"use client";

import { useMemo } from "react";
import { Users, Radio } from "lucide-react";
import { useRealtimeStore } from "@/stores/realtimeStore";
import { useAlertStore } from "@/hooks/useAlerts";

interface CrowdLiveCountPanelProps {
  cameraId?: number;
  processorActive?: boolean;
  personDetectionEnabled?: boolean;
  crowdRoiEnabled?: boolean;
  lastCrowdRoiCount?: number;
  crowdLimitEnabled?: boolean;
  crowdMaxPeople?: number;
}

export default function CrowdLiveCountPanel({
  cameraId,
  processorActive = false,
  personDetectionEnabled = true,
  crowdRoiEnabled = false,
  lastCrowdRoiCount,
  crowdLimitEnabled = false,
  crowdMaxPeople = 10,
}: CrowdLiveCountPanelProps) {
  const wsConnected = useAlertStore((s) => s.isConnected);
  const metrics = useRealtimeStore((s) => s.latestCrowdMetrics);

  const live = useMemo(
    () =>
      cameraId != null
        ? metrics.find((m) => m.camera_id === cameraId)
        : undefined,
    [metrics, cameraId]
  );

  const hasLive = Boolean(live && processorActive && wsConnected);
  const frameCount = hasLive ? live!.people_count : null;
  const zoneCount = hasLive ? live!.roi_count : null;
  const limitBasis = live?.limit_basis ?? (crowdRoiEnabled ? "zone" : "frame");
  const limitCount = hasLive
    ? (live!.limit_count ?? (limitBasis === "zone" ? zoneCount : frameCount))
    : null;

  return (
    <div
      className="lumicams-subcard rounded-md p-3 space-y-2"
      style={{ borderColor: "rgba(56,189,248,0.35)" }}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className="inline-flex items-center gap-2 text-[10px] font-semibold tracking-widest"
          style={{ color: "#38bdf8" }}
        >
          <Users className="w-3.5 h-3.5" />
          PEOPLE DETECTED
        </span>
        {hasLive && (
          <span
            className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded"
            style={{
              background: "rgba(34,197,94,0.12)",
              border: "1px solid rgba(34,197,94,0.35)",
              color: "#4ade80",
            }}
          >
            <Radio className="w-2.5 h-2.5" />
            LIVE
          </span>
        )}
      </div>

      {!personDetectionEnabled ? (
        <p className="text-[10px]" style={{ color: "#94a3b8" }}>
          Enable <strong>Person detection</strong> under Crowd Intelligence to count people in
          the stream.
        </p>
      ) : cameraId == null ? (
        <p className="text-[10px]" style={{ color: "#94a3b8" }}>
          Save the camera, then <strong>start the processor</strong> to see how many people YOLO
          detects in this feed.
        </p>
      ) : !processorActive ? (
        <p className="text-[10px]" style={{ color: "#94a3b8" }}>
          Processor is <strong>stopped</strong>. Start this camera to see live people counts.
          {lastCrowdRoiCount != null && crowdRoiEnabled && (
            <>
              {" "}
              Last zone count saved:{" "}
              <span className="font-mono text-cyan-400/90">{lastCrowdRoiCount}</span>.
            </>
          )}
        </p>
      ) : !wsConnected ? (
        <p className="text-[10px]" style={{ color: "#94a3b8" }}>
          Waiting for WebSocket… Start the processor; counts update about once per second.
          {lastCrowdRoiCount != null && crowdRoiEnabled && (
            <>
              {" "}
              Last zone (DB):{" "}
              <span className="font-mono text-cyan-400/90">{lastCrowdRoiCount}</span>.
            </>
          )}
        </p>
      ) : frameCount == null ? (
        <p className="text-[10px]" style={{ color: "#94a3b8" }}>
          No metrics yet — confirm person detection is on and the stream is readable.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <div
              className="rounded-md px-3 py-2 text-center"
              style={{ background: "rgba(15,23,42,0.65)", border: "1px solid #1a2540" }}
            >
              <p className="text-[9px] tracking-widest mb-0.5" style={{ color: "#64748b" }}>
                FULL FRAME
              </p>
              <p
                className="text-2xl font-bold tabular-nums leading-none"
                style={{ color: "#00d4ff", fontFamily: "var(--font-orbitron)" }}
              >
                {frameCount}
              </p>
              <p className="text-[9px] mt-1" style={{ color: "#475569" }}>
                People in view
              </p>
            </div>
            <div
              className="rounded-md px-3 py-2 text-center"
              style={{
                background: "rgba(15,23,42,0.65)",
                border: `1px solid ${crowdRoiEnabled ? "rgba(251,191,36,0.35)" : "#1a2540"}`,
              }}
            >
              <p className="text-[9px] tracking-widest mb-0.5" style={{ color: "#64748b" }}>
                IN ZONE (ROI)
              </p>
              <p
                className="text-2xl font-bold tabular-nums leading-none"
                style={{
                  color: crowdRoiEnabled ? "#fbbf24" : "#475569",
                  fontFamily: "var(--font-orbitron)",
                }}
              >
                {crowdRoiEnabled ? zoneCount ?? 0 : "—"}
              </p>
              <p className="text-[9px] mt-1" style={{ color: "#475569" }}>
                {crowdRoiEnabled ? "Inside rectangle" : "ROI off"}
              </p>
            </div>
          </div>
          {crowdLimitEnabled && limitCount != null && (
            <p className="text-[10px]" style={{ color: "#94a3b8" }}>
              Crowd limit uses <strong>{limitBasis}</strong> count:{" "}
              <span className="font-mono text-amber-400/90">{limitCount}</span>
              {" / "}
              <span className="font-mono">{crowdMaxPeople}</span> max
              {live?.overcrowded ? (
                <span className="ml-1 text-red-400 font-semibold">· OVER LIMIT</span>
              ) : null}
            </p>
          )}
        </>
      )}
    </div>
  );
}
