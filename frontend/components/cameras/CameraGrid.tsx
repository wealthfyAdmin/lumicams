"use client";

import { Camera as CameraIcon, Play, Square, Wifi, WifiOff, MapPin, VideoOff } from "lucide-react";
import { Camera } from "@/types";
import { startProcessor, stopProcessor, getCameraVideoSrc } from "@/lib/api";
import { useState, useEffect } from "react";
import Link from "next/link";
import toast from "react-hot-toast";

interface CameraCardProps {
  camera: Camera;
  onRefresh: () => void;
}

function CameraCard({ camera, onRefresh }: CameraCardProps) {
  const [loading, setLoading] = useState(false);
  const [streamError, setStreamError] = useState(false);
  
  const isActive = camera.status === "active";
  const isError = camera.status === "error";

  const streamUrl = getCameraVideoSrc(camera.id);

  // Reset stream error if the camera becomes active again
  useEffect(() => {
    if (isActive) setStreamError(false);
  }, [isActive]);

  async function handleToggle() {
    setLoading(true);
    setStreamError(false); // Reset error state on new attempt
    try {
      if (isActive) {
        await stopProcessor(camera.id);
        toast.success(`Paused ${camera.name}`);
      } else {
        await startProcessor(camera.id);
        toast.success(`Resumed ${camera.name} AI`);
      }
      
      // Wait a tiny bit for DB to commit before refreshing UI
      setTimeout(() => onRefresh(), 500);
      
    } catch (err: any) {
      // Robust error handling to prevent React crashes
      const detail = err.response?.data?.detail;
      const message = typeof detail === 'string' ? detail : "Action failed. Check video file path.";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="lumicams-card overflow-hidden group border border-[#1a2540] hover:border-[#00d4ff]/30 transition-colors">
      {/* Video Section */}
      <div className="relative aspect-video bg-[#080d1a] flex items-center justify-center overflow-hidden">
        {/* Corner brackets */}
        <span className="absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 z-10 opacity-40" style={{ borderColor: "#00d4ff" }} />
        <span className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 z-10 opacity-40" style={{ borderColor: "#00d4ff" }} />
        <span className="absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 z-10 opacity-40" style={{ borderColor: "#00d4ff" }} />
        <span className="absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 z-10 opacity-40" style={{ borderColor: "#00d4ff" }} />

        {isActive && !streamError && <div className="scan-overlay z-10" />}

        {/* Real Video Stream */}
        {isActive && !streamError ? (
          <img
            src={streamUrl}
            alt={`${camera.name} live stream`}
            className="w-full h-full object-cover"
            onError={() => {
              setStreamError(true);
            }}
          />
        ) : (
          <div className="flex flex-col items-center gap-2 opacity-40">
            {streamError ? (
              <>
                <VideoOff className="w-8 h-8 text-red-500" />
                <span className="text-[10px] tracking-[0.2em] font-mono text-red-500">FEED_INTERRUPTED</span>
              </>
            ) : (
              <>
                <CameraIcon className="w-8 h-8" style={{ color: "#00d4ff" }} />
                <span className="text-[10px] tracking-[0.2em] font-mono" style={{ color: "#00d4ff" }}>
                  {isActive ? "ESTABLISHING_LINK..." : "SYSTEM_OFFLINE"}
                </span>
              </>
            )}
          </div>
        )}

        {/* Status badge */}
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-20">
          <span
            className="flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded uppercase font-mono tracking-wider"
            style={{
              background: isActive ? "rgba(34,197,94,0.1)" : isError ? "rgba(239,68,68,0.1)" : "rgba(30,41,59,0.5)",
              border: `1px solid ${isActive ? "rgba(34,197,94,0.3)" : isError ? "rgba(239,68,68,0.3)" : "rgba(255,255,255,0.05)"}`,
              color: isActive ? "#4ade80" : isError ? "#f87171" : "#94a3b8",
            }}
          >
            {isActive ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {camera.status}
          </span>
        </div>

        {/* REC dot */}
        {isActive && !streamError && (
          <div className="absolute top-2 right-2 flex items-center gap-1.5 z-20 bg-black/40 px-2 py-0.5 rounded">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[10px] text-red-500 font-mono font-bold">LIVE</span>
          </div>
        )}
      </div>

      {/* Info Row */}
      <div className="p-3 flex items-center justify-between gap-3 bg-[#0c1222]">
        <div className="min-w-0 flex-1">
          <Link href={`/dashboard/cameras/${camera.id}`} className="block">
            <p className="text-sm font-bold truncate text-slate-200 hover:text-cyan-300 transition-colors">
              {camera.name}
            </p>
          </Link>
          <div className="flex items-center gap-2 mt-1">
            {camera.location && (
              <span className="text-[10px] flex items-center gap-1 text-slate-500 truncate">
                <MapPin className="w-3 h-3" /> {camera.location}
              </span>
            )}
          </div>
        </div>

        <button
          onClick={handleToggle}
          disabled={loading}
          className={`shrink-0 w-9 h-9 flex items-center justify-center rounded-lg transition-all active:scale-90 ${
            isActive 
              ? "bg-red-500/10 border border-red-500/30 text-red-500 hover:bg-red-500/20" 
              : "bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 hover:bg-emerald-500/20"
          }`}
        >
          {loading ? (
            <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : isActive ? (
            <Square className="w-4 h-4 fill-current" />
          ) : (
            <Play className="w-4 h-4 fill-current ml-0.5" />
          )}
        </button>
      </div>
    </div>
  );
}

interface CameraGridProps {
  cameras: Camera[];
  onRefresh: () => void;
}

export default function CameraGrid({ cameras, onRefresh }: CameraGridProps) {
  if (cameras.length === 0) {
    return (
      <div className="lumicams-card flex flex-col items-center justify-center gap-4 py-20 text-center opacity-60">
        <div className="p-4 rounded-full bg-slate-800/30">
          <CameraIcon className="w-10 h-10 text-slate-500" />
        </div>
        <div>
          <p className="text-slate-300 font-medium">No active surveillance nodes</p>
          <p className="text-xs text-slate-500 mt-1">Register an RTSP or local stream in the panel below.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {cameras.map((cam) => (
        <CameraCard key={cam.id} camera={cam} onRefresh={onRefresh} />
      ))}
    </div>
  );
}