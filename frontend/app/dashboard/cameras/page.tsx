"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import CameraGrid from "@/components/cameras/CameraGrid";
import CameraTable from "@/components/cameras/CameraTable";
import { getCameras } from "@/lib/api";
import { Camera } from "@/types";

export default function CamerasPage() {
  const [cameras,   setCameras]   = useState<Camera[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [refreshTs, setRefreshTs] = useState(Date.now());

  const refresh = useCallback(() => setRefreshTs(Date.now()), []);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getCameras();
        setCameras(data);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [refreshTs]);

  const active   = cameras.filter((c) => c.status === "active").length;
  const inactive = cameras.filter((c) => c.status === "inactive").length;
  const error    = cameras.filter((c) => c.status === "error").length;

  return (
    <div className="space-y-6 fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-widest"
              style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}>
            CAMERAS
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "#475569" }}>
            Manage RTSP streams and AI processor control
          </p>
        </div>
        <button onClick={refresh} className="btn-lumicams text-xs">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          REFRESH
        </button>
      </div>

      {/* Summary chips */}
      <div className="flex items-center gap-3 flex-wrap text-xs font-semibold tracking-wider">
        {[
          { label: "ACTIVE",   count: active,   color: "#22c55e" },
          { label: "IDLE",     count: inactive, color: "#475569" },
          { label: "ERROR",    count: error,    color: "#ef4444" },
          { label: "TOTAL",    count: cameras.length, color: "#00d4ff" },
        ].map(({ label, count, color }) => (
          <span
            key={label}
            className="px-3 py-1.5 rounded-md"
            style={{
              background: `${color}14`,
              border:     `1px solid ${color}33`,
              color,
            }}
          >
            {count} {label}
          </span>
        ))}
      </div>

      {/* Live feed grid */}
      <section>
        <h2 className="text-xs font-bold tracking-widest mb-3"
            style={{ fontFamily: "var(--font-orbitron)", color: "#475569" }}>
          LIVE FEEDS
        </h2>
        {loading ? (
          <div className="lumicams-card flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin"
                 style={{ color: "#00d4ff" }} />
          </div>
        ) : (
          <CameraGrid cameras={cameras} onRefresh={refresh} />
        )}
      </section>

      {/* Management table */}
      <CameraTable cameras={cameras} onRefresh={refresh} />
    </div>
  );
}
