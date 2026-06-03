"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Plus, Pencil, Trash2, Play, Square, Loader2, X, Check, Flame, PersonStanding, ScanFace, HardHat, Users, Shield
} from "lucide-react";
import { Camera, Organization } from "@/types";
import {
  createCamera,
  updateCamera,
  deleteCamera,
  startProcessor,
  stopProcessor,
  getCameraVideoSrc,
  getOrganizations,
} from "@/lib/api";
import toast from "react-hot-toast";
import { useAuth } from "@/hooks/useAuth";
import { formatTs } from "@/lib/utils";
import CrowdLiveCountPanel from "@/components/cameras/CrowdLiveCountPanel";
import { useRealtimeStore } from "@/stores/realtimeStore";

// ── Add / Edit Modal ──────────────────────────────────────────
interface ModalProps {
  initial?: Camera | null;
  onClose: () => void;
  onSave:  () => void;
}

function isCrowdModuleEnabled(cam: Camera): boolean {
  return (
    (cam.person_detection_enabled ?? true) ||
    Boolean(cam.crowd_roi_enabled) ||
    (cam.footfall_enabled ?? true) ||
    (cam.heatmap_enabled ?? true)
  );
}

function initRoiSliders(c?: Camera | null) {
  const x1 = c?.crowd_roi_x1 ?? 0.22;
  const x2 = c?.crowd_roi_x2 ?? 0.78;
  const y1 = c?.crowd_roi_y1 ?? 0.28;
  const y2 = c?.crowd_roi_y2 ?? 0.72;
  return {
    minX: Math.round(Math.min(x1, x2) * 100),
    maxX: Math.round(Math.max(x1, x2) * 100),
    minY: Math.round(Math.min(y1, y2) * 100),
    maxY: Math.round(Math.max(y1, y2) * 100),
  };
}

function clampPct(v: number) {
  return Math.max(0, Math.min(100, Math.round(v)));
}

function RoiDrawEditor({
  cameraId,
  minX,
  maxX,
  minY,
  maxY,
  onChange,
}: {
  cameraId?: number;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  onChange: (next: { minX: number; maxX: number; minY: number; maxY: number }) => void;
}) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const streamSrc = useMemo(
    () => (cameraId ? getCameraVideoSrc(cameraId, Date.now()) : ""),
    [cameraId]
  );

  const pointToPct = (clientX: number, clientY: number) => {
    const el = boxRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return null;
    const x = ((clientX - r.left) / r.width) * 100;
    const y = ((clientY - r.top) / r.height) * 100;
    return { x: clampPct(x), y: clampPct(y) };
  };

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const p = pointToPct(e.clientX, e.clientY);
    if (!p) return;
    dragStart.current = p;
    setDragging(true);
    onChange({ minX: p.x, maxX: p.x, minY: p.y, maxY: p.y });
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging || !dragStart.current) return;
    const p = pointToPct(e.clientX, e.clientY);
    if (!p) return;
    const s = dragStart.current;
    onChange({
      minX: Math.min(s.x, p.x),
      maxX: Math.max(s.x, p.x),
      minY: Math.min(s.y, p.y),
      maxY: Math.max(s.y, p.y),
    });
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    setDragging(false);
    dragStart.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
  };

  return (
    <div className="space-y-2">
      <p className="text-[9px] tracking-widest" style={{ color: "#475569" }}>
        DRAW ZONE ON CAMERA VIEW (drag to mark rectangle)
      </p>
      <div
        ref={boxRef}
        className="relative w-full aspect-video rounded overflow-hidden select-none touch-none"
        style={{ background: "#070d1a", border: "1px solid #1a2540" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {cameraId ? (
          // MJPEG endpoint. If the stream cannot be embedded, we still keep the drawing plane.
          <img src={streamSrc} alt="Camera preview" className="absolute inset-0 w-full h-full object-cover opacity-90" />
        ) : (
          <div className="absolute inset-0 grid place-items-center text-[10px]" style={{ color: "#475569" }}>
            Save camera first to draw on live preview
          </div>
        )}
        <div
          className="absolute"
          style={{
            left: `${minX}%`,
            top: `${minY}%`,
            width: `${Math.max(1, maxX - minX)}%`,
            height: `${Math.max(1, maxY - minY)}%`,
            border: "2px solid rgba(255,200,100,0.95)",
            background: "rgba(255,200,100,0.12)",
            boxShadow: "0 0 0 9999px rgba(2,6,23,0.28)",
          }}
        />
      </div>
      <p className="text-[9px]" style={{ color: "#64748b" }}>
        Zone: X {minX}-{maxX}% · Y {minY}-{maxY}%
      </p>
    </div>
  );
}

function CameraModal({ initial, onClose, onSave }: ModalProps) {
  const authUser = useAuth((s) => s.user);
  const isPlatform = authUser?.role === "super_admin";
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [orgPick, setOrgPick] = useState<number | "">(
    initial?.organization_id != null ? initial.organization_id : ""
  );

  useEffect(() => {
    if (!isPlatform) return;
    getOrganizations().then(setOrgs).catch(() => setOrgs([]));
  }, [isPlatform]);

  const [name,     setName]     = useState(initial?.name     ?? "");
  const [rtsp,     setRtsp]     = useState(initial?.rtsp_url ?? "");
  const [location, setLocation] = useState(initial?.location ?? "");
  const [personDet, setPersonDet] = useState(initial?.person_detection_enabled ?? true);
  const [crowdRoi, setCrowdRoi] = useState(initial?.crowd_roi_enabled ?? false);
  const [crowdModuleEnabled, setCrowdModuleEnabled] = useState(
    (initial?.person_detection_enabled ?? true) ||
      (initial?.crowd_roi_enabled ?? false) ||
      (initial?.footfall_enabled ?? true) ||
      (initial?.heatmap_enabled ?? true)
  );
  const roi0 = initRoiSliders(initial ?? null);
  const [roiMinX, setRoiMinX] = useState(roi0.minX);
  const [roiMaxX, setRoiMaxX] = useState(roi0.maxX);
  const [roiMinY, setRoiMinY] = useState(roi0.minY);
  const [roiMaxY, setRoiMaxY] = useState(roi0.maxY);
  const [footfallEnabled, setFootfallEnabled] = useState(initial?.footfall_enabled ?? true);
  const [crowdLimitEnabled, setCrowdLimitEnabled] = useState(initial?.crowd_limit_enabled ?? false);
  const [crowdMaxPeople, setCrowdMaxPeople] = useState(initial?.crowd_max_people ?? 10);
  const [fireEnabled, setFireEnabled] = useState(initial?.fire_enabled ?? true);
  const [fireMinConf, setFireMinConf] = useState<number>(
    initial?.fire_min_confidence != null ? Number(initial.fire_min_confidence) : 0.45
  );
  const [fallEnabled, setFallEnabled] = useState(initial?.fall_enabled ?? true);
  const [fallConsecutive, setFallConsecutive] = useState<number>(
    initial?.fall_consecutive_frames != null ? Number(initial.fall_consecutive_frames) : 5
  );
  const [faceEnabled, setFaceEnabled] = useState(initial?.face_enabled ?? true);
  const [faceMinSimilarity, setFaceMinSimilarity] = useState<number>(
    initial?.face_min_similarity != null ? Number(initial.face_min_similarity) : 0.52
  );
  const [ppeEnabled, setPpeEnabled] = useState(initial?.ppe_enabled ?? false);
  const [ppeConfidence, setPpeConfidence] = useState<number>(
    initial?.ppe_confidence != null ? Number(initial.ppe_confidence) : 0.45
  );
  const [ppeItems, setPpeItems] = useState<string[]>(
    Array.isArray(initial?.ppe_items) && initial!.ppe_items!.length > 0
      ? (initial!.ppe_items as string[])
      : ["helmet", "vest"]
  );
  const [weaponEnabled, setWeaponEnabled] = useState(initial?.weapon_enabled ?? false);
  const [weaponConfidence, setWeaponConfidence] = useState<number>(
    initial?.weapon_confidence != null ? Number(initial.weapon_confidence) : 0.45
  );
  const [footfallMode, setFootfallMode] = useState<"line" | "zone">(
    initial?.footfall_mode === "zone" ? "zone" : "line"
  );
  const [heatmapEnabled, setHeatmapEnabled] = useState(initial?.heatmap_enabled ?? true);
  const [lineY, setLineY] = useState(initial?.footfall_line_y ?? 0.5);
  const showRoiSliders =
    crowdModuleEnabled && (crowdRoi || (footfallEnabled && footfallMode === "zone"));
  const [loading,  setLoading]  = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    let minX = roiMinX;
    let maxX = roiMaxX;
    let minY = roiMinY;
    let maxY = roiMaxY;
    if (minX >= maxX) maxX = Math.min(99, minX + 1);
    if (minY >= maxY) maxY = Math.min(99, minY + 1);
    setLoading(true);
    try {
      const aiPayload = {
        person_detection_enabled: crowdModuleEnabled ? personDet : false,
        crowd_roi_enabled: crowdModuleEnabled ? crowdRoi : false,
        crowd_roi_x1: minX / 100,
        crowd_roi_y1: minY / 100,
        crowd_roi_x2: maxX / 100,
        crowd_roi_y2: maxY / 100,
        crowd_limit_enabled: crowdModuleEnabled ? crowdLimitEnabled : false,
        crowd_max_people: Math.max(1, Math.min(500, Number(crowdMaxPeople) || 10)),
        fire_enabled: fireEnabled,
        fire_min_confidence: fireEnabled ? Math.max(0.05, Math.min(0.99, Number(fireMinConf) || 0.45)) : null,
        fall_enabled: fallEnabled,
        fall_consecutive_frames: fallEnabled ? Math.max(1, Math.min(30, Number(fallConsecutive) || 5)) : null,
        face_enabled: faceEnabled,
        face_min_similarity: faceEnabled ? Math.max(0.1, Math.min(0.99, Number(faceMinSimilarity) || 0.52)) : null,
        ppe_enabled: ppeEnabled,
        ppe_items: ppeEnabled ? ppeItems : [],
        ppe_confidence: ppeEnabled ? Math.max(0.05, Math.min(0.99, Number(ppeConfidence) || 0.45)) : null,
        weapon_enabled: weaponEnabled,
        weapon_confidence: weaponEnabled
          ? Math.max(0.05, Math.min(0.99, Number(weaponConfidence) || 0.45))
          : null,
        footfall_enabled: crowdModuleEnabled ? footfallEnabled : false,
        footfall_mode: footfallMode,
        footfall_line_y: lineY,
        heatmap_enabled: crowdModuleEnabled ? heatmapEnabled : false,
      };
      if (initial) {
        await updateCamera(initial.id, {
          name,
          rtsp_url: rtsp,
          location,
          ...aiPayload,
        });
        toast.success("Camera updated.");
      } else {
        if (isPlatform) {
          if (orgPick === "") {
            toast.error("Select an organization for this camera.");
            setLoading(false);
            return;
          }
        }
        await createCamera({
          name,
          rtsp_url: rtsp,
          location,
          ...(isPlatform ? { organization_id: Number(orgPick) } : {}),
          ...aiPayload,
        });
        toast.success("Camera added.");
      }
      onSave();
      onClose();
    } catch (err: unknown) {
      const msg = (err as {response?:{data?:{detail?:string}}})?.response?.data?.detail ?? "Save failed.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = {
    background: "var(--dash-alerts-bg, #0d1527)",
    border: "1px solid var(--dash-sidebar-border, #1a2540)",
    color: "var(--dash-body-text, #e2e8f0)",
    fontFamily: "var(--font-space-mono)",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl mx-4 lumicams-card p-6 z-10 fade-in max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-bold tracking-widest" style={{ fontFamily: "var(--font-orbitron)", color: "#94a3b8" }}>
            {initial ? "EDIT CAMERA" : "ADD CAMERA"}
          </h3>
          <button onClick={onClose} style={{ color: "#475569" }}><X className="w-4 h-4" /></button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {isPlatform && !initial && (
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-widest" style={{ color: "#475569" }}>
                ORGANIZATION
              </label>
              <select
                value={orgPick === "" ? "" : String(orgPick)}
                onChange={(e) => setOrgPick(e.target.value ? Number(e.target.value) : "")}
                required
                className="w-full px-3 py-2 rounded-md text-sm outline-none transition-all"
                style={inputStyle}
              >
                <option value="">Select organization…</option>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
            </div>
          )}
          {[
            { label: "CAMERA NAME", value: name,     set: setName,     placeholder: "Lobby Entrance", required: true  },
            { label: "RTSP / STREAM URL", value: rtsp, set: setRtsp,   placeholder: "rtsp://192.168.1.100:554/stream", required: true },
            { label: "LOCATION (optional)", value: location, set: setLocation, placeholder: "Building A – Floor 2", required: false },
          ].map(({ label, value, set, placeholder, required }) => (
            <div key={label}>
              <label className="block text-xs font-semibold mb-1.5 tracking-widest" style={{ color: "#475569" }}>
                {label}
              </label>
              <input
                value={value}
                onChange={(e) => set(e.target.value)}
                placeholder={placeholder}
                required={required}
                className="w-full px-3 py-2 rounded-md text-sm outline-none transition-all"
                style={inputStyle}
                onFocus={(e) => (e.target.style.borderColor = "rgba(0,212,255,0.5)")}
                onBlur={(e)  => (e.target.style.borderColor = "var(--dash-sidebar-border, #1a2540)")}
              />
            </div>
          ))}

          <div className="space-y-3 pt-1">
            <p className="text-[10px] font-semibold tracking-widest" style={{ color: "#64748b" }}>
              CAMERA MODULES (SELLABLE)
            </p>
            <p className="text-[10px] leading-relaxed" style={{ color: "#475569" }}>
              Enable only the models sold for this camera. Alerts will be generated only for enabled modules.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <label
                className="lumicams-subcard rounded-md px-3 py-2 flex items-center justify-between cursor-pointer"
                style={{ borderColor: fireEnabled ? "rgba(249,115,22,0.45)" : "#1a2540" }}
              >
                <span className="inline-flex items-center gap-2 text-xs" style={{ color: fireEnabled ? "#fb923c" : "#94a3b8" }}>
                  <Flame className="w-3.5 h-3.5" />
                  Fire Detection
                </span>
                <input type="checkbox" checked={fireEnabled} onChange={(e) => setFireEnabled(e.target.checked)} />
              </label>
              <label
                className="lumicams-subcard rounded-md px-3 py-2 flex items-center justify-between cursor-pointer"
                style={{ borderColor: fallEnabled ? "rgba(245,158,11,0.45)" : "#1a2540" }}
              >
                <span className="inline-flex items-center gap-2 text-xs" style={{ color: fallEnabled ? "#fbbf24" : "#94a3b8" }}>
                  <PersonStanding className="w-3.5 h-3.5" />
                  Fall Detection
                </span>
                <input type="checkbox" checked={fallEnabled} onChange={(e) => setFallEnabled(e.target.checked)} />
              </label>
              <label
                className="lumicams-subcard rounded-md px-3 py-2 flex items-center justify-between cursor-pointer"
                style={{ borderColor: faceEnabled ? "rgba(139,92,246,0.45)" : "#1a2540" }}
              >
                <span className="inline-flex items-center gap-2 text-xs" style={{ color: faceEnabled ? "#a78bfa" : "#94a3b8" }}>
                  <ScanFace className="w-3.5 h-3.5" />
                  Face Intelligence
                </span>
                <input type="checkbox" checked={faceEnabled} onChange={(e) => setFaceEnabled(e.target.checked)} />
              </label>
              <label
                className="lumicams-subcard rounded-md px-3 py-2 flex items-center justify-between cursor-pointer"
                style={{ borderColor: ppeEnabled ? "rgba(16,185,129,0.45)" : "#1a2540" }}
              >
                <span className="inline-flex items-center gap-2 text-xs" style={{ color: ppeEnabled ? "#34d399" : "#94a3b8" }}>
                  <HardHat className="w-3.5 h-3.5" />
                  PPE Compliance
                </span>
                <input type="checkbox" checked={ppeEnabled} onChange={(e) => setPpeEnabled(e.target.checked)} />
              </label>
              <label
                className="lumicams-subcard rounded-md px-3 py-2 flex items-center justify-between cursor-pointer"
                style={{ borderColor: weaponEnabled ? "rgba(239,68,68,0.45)" : "#1a2540" }}
              >
                <span className="inline-flex items-center gap-2 text-xs" style={{ color: weaponEnabled ? "#f87171" : "#94a3b8" }}>
                  <Shield className="w-3.5 h-3.5" />
                  Weapon detection
                </span>
                <input type="checkbox" checked={weaponEnabled} onChange={(e) => setWeaponEnabled(e.target.checked)} />
              </label>
              <label
                className="lumicams-subcard rounded-md px-3 py-2 flex items-center justify-between cursor-pointer sm:col-span-2"
                style={{ borderColor: crowdModuleEnabled ? "rgba(56,189,248,0.45)" : "#1a2540" }}
              >
                <span className="inline-flex items-center gap-2 text-xs" style={{ color: crowdModuleEnabled ? "#38bdf8" : "#94a3b8" }}>
                  <Users className="w-3.5 h-3.5" />
                  Crowd Intelligence (Master)
                </span>
                <input
                  type="checkbox"
                  checked={crowdModuleEnabled}
                  onChange={(e) => setCrowdModuleEnabled(e.target.checked)}
                />
              </label>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
              <label className="lumicams-subcard rounded-md px-3 py-2 flex items-center gap-2 cursor-pointer" style={{ color: crowdModuleEnabled ? "#94a3b8" : "#64748b" }}>
                <input
                  type="checkbox"
                  checked={personDet}
                  onChange={(e) => setPersonDet(e.target.checked)}
                  disabled={!crowdModuleEnabled}
                />
                Person detection
              </label>
              <label className="lumicams-subcard rounded-md px-3 py-2 flex items-center gap-2 cursor-pointer" style={{ color: crowdModuleEnabled ? "#94a3b8" : "#64748b" }}>
                <input
                  type="checkbox"
                  checked={crowdRoi}
                  onChange={(e) => setCrowdRoi(e.target.checked)}
                  disabled={!crowdModuleEnabled}
                />
                Crowd zone (ROI count)
              </label>
              <label className="lumicams-subcard rounded-md px-3 py-2 flex items-center gap-2 cursor-pointer" style={{ color: crowdModuleEnabled ? "#94a3b8" : "#64748b" }}>
                <input
                  type="checkbox"
                  checked={footfallEnabled}
                  onChange={(e) => setFootfallEnabled(e.target.checked)}
                  disabled={!crowdModuleEnabled}
                />
                Footfall counting
              </label>
              <label className="lumicams-subcard rounded-md px-3 py-2 flex items-center gap-2 cursor-pointer" style={{ color: crowdModuleEnabled ? "#94a3b8" : "#64748b" }}>
                <input
                  type="checkbox"
                  checked={heatmapEnabled}
                  onChange={(e) => setHeatmapEnabled(e.target.checked)}
                  disabled={!crowdModuleEnabled}
                />
                Heatmap grid
              </label>
            </div>

            {crowdModuleEnabled && (
              <CrowdLiveCountPanel
                cameraId={initial?.id}
                processorActive={initial?.status === "active"}
                personDetectionEnabled={personDet}
                crowdRoiEnabled={crowdRoi}
                lastCrowdRoiCount={initial?.last_crowd_roi_count}
                crowdLimitEnabled={crowdLimitEnabled}
                crowdMaxPeople={crowdMaxPeople}
              />
            )}

            {(fireEnabled || fallEnabled || faceEnabled || ppeEnabled || weaponEnabled) && (
              <div className="lumicams-subcard rounded-md p-3 grid grid-cols-1 sm:grid-cols-4 gap-2 items-end text-[10px] pt-1">
                {fireEnabled && (
                  <label style={{ color: "#64748b" }}>
                    Fire min confidence
                    <input
                      type="number"
                      min={0.05}
                      max={0.99}
                      step={0.01}
                      value={fireMinConf}
                      onChange={(e) => setFireMinConf(Number(e.target.value))}
                      className="w-full mt-1 px-2 py-1.5 rounded text-xs outline-none"
                      style={inputStyle}
                    />
                  </label>
                )}
                {fallEnabled && (
                  <label style={{ color: "#64748b" }}>
                    Fall confirm frames
                    <input
                      type="number"
                      min={1}
                      max={30}
                      value={fallConsecutive}
                      onChange={(e) => setFallConsecutive(Number(e.target.value))}
                      className="w-full mt-1 px-2 py-1.5 rounded text-xs outline-none"
                      style={inputStyle}
                    />
                  </label>
                )}
                {faceEnabled && (
                  <label style={{ color: "#64748b" }}>
                    Face min similarity
                    <input
                      type="number"
                      min={0.1}
                      max={0.99}
                      step={0.01}
                      value={faceMinSimilarity}
                      onChange={(e) => setFaceMinSimilarity(Number(e.target.value))}
                      className="w-full mt-1 px-2 py-1.5 rounded text-xs outline-none"
                      style={inputStyle}
                    />
                  </label>
                )}
                {ppeEnabled && (
                  <label style={{ color: "#64748b" }}>
                    PPE min confidence
                    <input
                      type="number"
                      min={0.05}
                      max={0.99}
                      step={0.01}
                      value={ppeConfidence}
                      onChange={(e) => setPpeConfidence(Number(e.target.value))}
                      className="w-full mt-1 px-2 py-1.5 rounded text-xs outline-none"
                      style={inputStyle}
                    />
                  </label>
                )}
                {weaponEnabled && (
                  <label style={{ color: "#64748b" }}>
                    Weapon min confidence
                    <input
                      type="number"
                      min={0.05}
                      max={0.99}
                      step={0.01}
                      value={weaponConfidence}
                      onChange={(e) => setWeaponConfidence(Number(e.target.value))}
                      className="w-full mt-1 px-2 py-1.5 rounded text-xs outline-none"
                      style={inputStyle}
                    />
                  </label>
                )}
              </div>
            )}

            {ppeEnabled && (
              <div className="lumicams-subcard rounded-md p-3 space-y-2">
                <label className="block text-[9px] tracking-widest" style={{ color: "#475569" }}>
                  PPE EQUIPMENT CHECKLIST (multi-select)
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px]">
                  {["helmet", "vest", "gloves", "boots", "goggles", "mask", "kit"].map((eq) => {
                    const active = ppeItems.includes(eq);
                    return (
                      <button
                        key={eq}
                        type="button"
                        className="px-2 py-1 rounded border text-left"
                        style={{
                          borderColor: active ? "rgba(16,185,129,0.35)" : "#1a2540",
                          color: active ? "#34d399" : "#64748b",
                          background: active ? "rgba(16,185,129,0.08)" : "transparent",
                        }}
                        onClick={() =>
                          setPpeItems((prev) =>
                            prev.includes(eq) ? prev.filter((x) => x !== eq) : [...prev, eq]
                          )
                        }
                      >
                        {eq.toUpperCase()}
                      </button>
                    );
                  })}
                </div>
                <p className="text-[9px]" style={{ color: "#64748b" }}>
                  Alerts are generated only for selected missing equipment (e.g. helmet only or full kit).
                </p>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 items-center text-[10px] pt-1">
              <label className="lumicams-subcard rounded-md px-3 py-2 flex items-center gap-2 cursor-pointer" style={{ color: "#94a3b8" }}>
                <input
                  type="checkbox"
                  checked={crowdLimitEnabled}
                  onChange={(e) => setCrowdLimitEnabled(e.target.checked)}
                    disabled={!crowdModuleEnabled}
                />
                Crowd limit alert
              </label>
              <label style={{ color: "#64748b" }}>
                Max people allowed
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={crowdMaxPeople}
                  onChange={(e) => setCrowdMaxPeople(Number(e.target.value))}
                  disabled={!crowdModuleEnabled || !crowdLimitEnabled}
                  className="w-full mt-1 px-2 py-1.5 rounded text-xs outline-none"
                  style={inputStyle}
                />
              </label>
            </div>
            {crowdModuleEnabled && crowdLimitEnabled && (
              <p
                className="text-[9px] leading-snug sm:col-span-2"
                style={{ color: "#475569" }}
              >
                With <strong>Crowd zone (ROI)</strong> or footfall <strong>zone</strong> mode on, the
                default server mode counts <strong>people inside the rectangle</strong> for this
                limit (not the whole frame unless the server is set to global).
              </p>
            )}

            {crowdModuleEnabled && footfallEnabled && (
              <div className="pl-1 border-l border-cyan-500/20 space-y-1">
                <label className="block text-[9px] tracking-widest" style={{ color: "#475569" }}>
                  FOOTFALL MODE
                </label>
                <select
                  value={footfallMode}
                  onChange={(e) => setFootfallMode(e.target.value as "line" | "zone")}
                  className="w-full text-xs px-2 py-1.5 rounded"
                  style={{ ...inputStyle, border: "1px solid #1a2540" }}
                >
                  <option value="line">Line — count when crossing horizontal line</option>
                  <option value="zone">Zone — count entry when someone enters ROI (rectangle)</option>
                </select>
              </div>
            )}

            {showRoiSliders && (
              <div className="space-y-2 pt-1 pl-1 border-l border-orange-500/25">
                <RoiDrawEditor
                  cameraId={initial?.id}
                  minX={roiMinX}
                  maxX={roiMaxX}
                  minY={roiMinY}
                  maxY={roiMaxY}
                  onChange={({ minX, maxX, minY, maxY }) => {
                    setRoiMinX(minX);
                    setRoiMaxX(maxX);
                    setRoiMinY(minY);
                    setRoiMaxY(maxY);
                  }}
                />
                <p className="text-[9px] tracking-widest" style={{ color: "#475569" }}>
                  ROI RECTANGLE % (left/right/top/bottom of frame)
                  {footfallMode === "zone" && footfallEnabled && (
                    <span className="block text-[8px] mt-0.5" style={{ color: "#94a3b8" }}>
                      Zone footfall: entry when a person&apos;s foot point moves into this box; exit when leaving.
                    </span>
                  )}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-[9px]" style={{ color: "#64748b" }}>
                    Left {roiMinX}%
                    <input
                      type="range"
                      min={0}
                      max={98}
                      value={roiMinX}
                      onChange={(e) => setRoiMinX(Number(e.target.value))}
                      className="w-full accent-cyan-500"
                    />
                  </label>
                  <label className="text-[9px]" style={{ color: "#64748b" }}>
                    Right {roiMaxX}%
                    <input
                      type="range"
                      min={1}
                      max={100}
                      value={roiMaxX}
                      onChange={(e) => setRoiMaxX(Number(e.target.value))}
                      className="w-full accent-cyan-500"
                    />
                  </label>
                  <label className="text-[9px]" style={{ color: "#64748b" }}>
                    Top {roiMinY}%
                    <input
                      type="range"
                      min={0}
                      max={98}
                      value={roiMinY}
                      onChange={(e) => setRoiMinY(Number(e.target.value))}
                      className="w-full accent-cyan-500"
                    />
                  </label>
                  <label className="text-[9px]" style={{ color: "#64748b" }}>
                    Bottom {roiMaxY}%
                    <input
                      type="range"
                      min={1}
                      max={100}
                      value={roiMaxY}
                      onChange={(e) => setRoiMaxY(Number(e.target.value))}
                      className="w-full accent-cyan-500"
                    />
                  </label>
                </div>
              </div>
            )}

            <p className="text-[10px] font-semibold tracking-widest pt-2" style={{ color: "#475569" }}>
              FOOTFALL LINE (only for &quot;line&quot; mode — Y 0=top, 1=bottom)
            </p>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(lineY * 100)}
              onChange={(e) => setLineY(Number(e.target.value) / 100)}
              className="w-full accent-cyan-500"
              disabled={!crowdModuleEnabled || !footfallEnabled || footfallMode === "zone"}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest transition-all"
              style={{ background: "rgba(71,85,105,0.1)", border: "1px solid #1a2540", color: "#475569" }}
            >
              CANCEL
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest transition-all flex items-center justify-center gap-2"
              style={{ background: "rgba(0,212,255,0.12)", border: "1px solid rgba(0,212,255,0.3)", color: "#00d4ff" }}
            >
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
              {initial ? "UPDATE" : "ADD CAMERA"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main Table ────────────────────────────────────────────────
interface CameraTableProps {
  cameras:   Camera[];
  onRefresh: () => void;
}

export default function CameraTable({ cameras, onRefresh }: CameraTableProps) {
  const isAdmin = useAuth((s) => s.isAdmin);
  const crowdMetrics = useRealtimeStore((s) => s.latestCrowdMetrics);
  const metricByCam = useMemo(() => {
    const m = new Map<number, (typeof crowdMetrics)[0]>();
    for (const row of crowdMetrics) m.set(row.camera_id, row);
    return m;
  }, [crowdMetrics]);
  const showPeopleCol = cameras.some(isCrowdModuleEnabled);
  const [modal,    setModal]    = useState<"add" | Camera | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [toggling, setToggling] = useState<number | null>(null);

  async function handleDelete(cam: Camera) {
    if (!confirm(`Delete camera "${cam.name}"? This cannot be undone.`)) return;
    setDeleting(cam.id);
    try {
      await deleteCamera(cam.id);
      toast.success(`Camera "${cam.name}" deleted.`);
      onRefresh();
    } catch {
      toast.error("Delete failed.");
    } finally {
      setDeleting(null);
    }
  }

  async function handleToggle(cam: Camera) {
    setToggling(cam.id);
    try {
      if (cam.status === "active") {
        await stopProcessor(cam.id);
        toast.success(`${cam.name} paused.`);
      } else {
        await startProcessor(cam.id);
        toast.success(`${cam.name} resumed.`);
      }
      onRefresh();
    } catch {
      toast.error("Action failed.");
    } finally {
      setToggling(null);
    }
  }

  const statusColor = (s: string) =>
    s === "active" ? "#22c55e" : s === "error" ? "#ef4444" : "#475569";

  return (
    <>
      {modal && (
        <CameraModal
          initial={modal === "add" ? null : modal}
          onClose={() => setModal(null)}
          onSave={onRefresh}
        />
      )}

      <div className="lumicams-card overflow-hidden">
        {/* Table header */}
        <div className="flex items-center justify-between px-5 py-3"
             style={{ borderBottom: "1px solid #1a2540" }}>
          <h2 className="text-xs font-bold tracking-widest"
              style={{ fontFamily: "var(--font-orbitron)", color: "#94a3b8" }}>
            CAMERA MANAGEMENT
          </h2>
          {isAdmin && (
            <button
              onClick={() => setModal("add")}
              className="btn-lumicams text-xs py-1.5"
            >
              <Plus className="w-3.5 h-3.5" /> ADD CAMERA
            </button>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full lumicams-table">
            <thead>
              <tr>
                <th className="text-left">ID</th>
                <th className="text-left">NAME</th>
                <th className="text-left">STREAM URL</th>
                <th className="text-left">LOCATION</th>
                <th className="text-left">STATUS</th>
                {showPeopleCol && (
                  <th className="text-left">PEOPLE</th>
                )}
                <th className="text-left">ADDED</th>
                {isAdmin && <th className="text-right">ACTIONS</th>}
              </tr>
            </thead>
            <tbody>
              {cameras.length === 0 ? (
                <tr>
                  <td
                    colSpan={(isAdmin ? 7 : 6) + (showPeopleCol ? 1 : 0)}
                    className="text-center py-10"
                    style={{ color: "#2a3a5c" }}
                  >
                    No cameras found. Add one to get started.
                  </td>
                </tr>
              ) : (
                cameras.map((cam) => (
                  <tr key={cam.id}>
                    <td style={{ color: "#2a3a5c", fontFamily: "var(--font-space-mono)" }}>
                      #{cam.id}
                    </td>
                    <td style={{ color: "#e2e8f0", fontWeight: 600 }}>{cam.name}</td>
                    <td style={{ color: "#475569", fontFamily: "var(--font-space-mono)", fontSize: "0.75rem" }}>
                      {cam.rtsp_url.length > 42 ? cam.rtsp_url.slice(0, 42) + "…" : cam.rtsp_url}
                    </td>
                    <td style={{ color: "#475569" }}>{cam.location ?? "—"}</td>
                    <td>
                      <span className="flex items-center gap-1.5 text-xs font-semibold"
                            style={{ color: statusColor(cam.status) }}>
                        <span className={`status-dot ${cam.status}`} />
                        {cam.status.toUpperCase()}
                      </span>
                    </td>
                    {showPeopleCol && (
                      <td style={{ fontSize: "0.75rem" }}>
                        {!isCrowdModuleEnabled(cam) ? (
                          <span style={{ color: "#475569" }}>—</span>
                        ) : cam.status !== "active" ? (
                          <span style={{ color: "#64748b" }} title="Start processor for live count">
                            {cam.crowd_roi_enabled && cam.last_crowd_roi_count != null
                              ? `Z:${cam.last_crowd_roi_count}`
                              : "—"}
                          </span>
                        ) : (
                          (() => {
                            const live = metricByCam.get(cam.id);
                            if (!live) {
                              return (
                                <span style={{ color: "#64748b" }}>…</span>
                              );
                            }
                            return (
                              <span
                                className="font-mono tabular-nums"
                                style={{ color: "#00d4ff" }}
                                title={
                                  cam.crowd_roi_enabled
                                    ? `Frame: ${live.people_count} · Zone: ${live.roi_count}`
                                    : `People in frame: ${live.people_count}`
                                }
                              >
                                {live.people_count}
                                {cam.crowd_roi_enabled ? (
                                  <span style={{ color: "#fbbf24" }}> / {live.roi_count}</span>
                                ) : null}
                              </span>
                            );
                          })()
                        )}
                      </td>
                    )}
                    <td style={{ color: "#475569", fontSize: "0.75rem" }}>
                      {formatTs(cam.created_at)}
                    </td>
                    {isAdmin && (
                      <td>
                        <div className="flex items-center justify-end gap-2">
                          {/* Start / Stop */}
                          <button
                            onClick={() => handleToggle(cam)}
                            disabled={toggling === cam.id}
                            className="p-1.5 rounded transition-all"
                            style={cam.status === "active"
                              ? { color: "#ef4444", background: "rgba(239,68,68,0.08)" }
                              : { color: "#22c55e", background: "rgba(34,197,94,0.08)" }}
                            title={cam.status === "active" ? "Pause" : "Resume"}
                          >
                            {toggling === cam.id
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : cam.status === "active"
                                ? <Square className="w-3.5 h-3.5" />
                                : <Play   className="w-3.5 h-3.5" />
                            }
                          </button>

                          <Link
                            href={`/dashboard/cameras/${cam.id}`}
                            className="p-1.5 rounded transition-all"
                            style={{ color: "#94a3b8", background: "rgba(148,163,184,0.08)" }}
                            title="View analytics"
                          >
                            <span className="text-[10px] font-bold tracking-wider">VIEW</span>
                          </Link>

                          {/* Edit */}
                          <button
                            onClick={() => setModal(cam)}
                            className="p-1.5 rounded transition-all"
                            style={{ color: "#00d4ff", background: "rgba(0,212,255,0.08)" }}
                            title="Edit"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>

                          {/* Delete */}
                          <button
                            onClick={() => handleDelete(cam)}
                            disabled={deleting === cam.id}
                            className="p-1.5 rounded transition-all"
                            style={{ color: "#ef4444", background: "rgba(239,68,68,0.08)" }}
                            title="Delete"
                          >
                            {deleting === cam.id
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <Trash2  className="w-3.5 h-3.5" />
                            }
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
