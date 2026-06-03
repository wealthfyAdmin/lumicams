"use client";

import { useEffect, useMemo, useState } from "react";
import { Shield, Save, ShieldAlert, Settings2, CheckCircle2 } from "lucide-react";
import {
  getAlerts,
  getCameraWeaponStatus,
  getCameras,
  updateCamera,
  type CameraWeaponStatus,
} from "@/lib/api";
import { Camera } from "@/types";
import { formatTs, timeAgo } from "@/lib/utils";

export default function WeaponPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [weaponStatus, setWeaponStatus] = useState<CameraWeaponStatus | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [cams, weaponAlerts] = await Promise.all([
          getCameras(),
          getAlerts({ limit: 100, alert_type: "Weapon" }),
        ]);
        setCameras(cams);
        setAlerts(weaponAlerts);
        const probe = cams.find((c: Camera) => c.status === "active") ?? cams[0];
        if (probe) {
          try {
            const st = await getCameraWeaponStatus(probe.id);
            setWeaponStatus(st);
          } catch {
            setWeaponStatus(null);
          }
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function saveCamera(cam: Camera) {
    setSavingId(cam.id);
    try {
      await updateCamera(cam.id, {
        weapon_enabled: Boolean(cam.weapon_enabled),
        weapon_confidence: cam.weapon_enabled ? (cam.weapon_confidence ?? 0.45) : null,
      });
    } finally {
      setSavingId(null);
    }
  }

  const activeCount = useMemo(() => cameras.filter((c) => c.weapon_enabled).length, [cameras]);

  const filterInfo =
    weaponStatus &&
    typeof weaponStatus.class_filter === "string"
      ? weaponStatus.class_filter
      : Array.isArray(weaponStatus?.class_filter)
        ? (weaponStatus.class_filter as string[]).join(", ")
        : "";

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1
            className="text-md font-bold tracking-widest"
            style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}
          >
            WEAPON DETECTION
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            Enable YOLO weapon inference per camera, tune confidence, and review alerts (VLM verifies snapshots).
          </p>
        </div>
        <div
          className="text-[11px] px-3 py-1.5 rounded-md border inline-flex items-center gap-2"
          style={{
            color: "var(--dash-body-text)",
            borderColor: "var(--dash-sidebar-border)",
            background: "rgba(239,68,68,0.06)",
          }}
        >
          <Settings2 className="w-3.5 h-3.5" />
          Security / law-enforcement style monitoring
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="aegis-card p-4">
          <p className="text-xs tracking-widest" style={{ color: "var(--dash-subtle)" }}>
            CAMERAS WITH WEAPON ON
          </p>
          <p className="text-xl font-bold mt-1" style={{ color: "#f87171" }}>
            {activeCount}
          </p>
        </div>
        <div className="aegis-card p-4">
          <p className="text-xs tracking-widest" style={{ color: "var(--dash-subtle)" }}>
            WEAPON ALERTS (RECENT)
          </p>
          <p className="text-xl font-bold mt-1" style={{ color: "#ef4444" }}>
            {alerts.length}
          </p>
        </div>
        <div className="aegis-card p-4 flex items-center gap-3">
          <Shield className="w-6 h-6" style={{ color: "#f87171" }} />
          <p className="text-xs" style={{ color: "var(--dash-body-text)" }}>
            Place <code className="text-[10px]">YOLO_WEAPON_MODEL</code> on the server and restart inference.
          </p>
        </div>
      </div>

      {weaponStatus && (
        <div className={`aegis-banner ${weaponStatus.model_loaded ? "aegis-banner--success" : "aegis-banner--warn"}`}>
          {weaponStatus.model_loaded ? (
            <span>
              Weapon model is loaded from <code>{weaponStatus.model_path}</code>
              {filterInfo ? (
                <>
                  . Class filter: <strong>{filterInfo}</strong>.
                </>
              ) : null}
            </span>
          ) : (
            <span>
              Weapon model is not loaded. Start a camera processor and set{" "}
              <code>YOLO_WEAPON_MODEL</code> (or add weights under <code>backend/models/</code>). Current path:{" "}
              <code>{weaponStatus.model_path}</code>.
            </span>
          )}
        </div>
      )}

      <div className="aegis-card p-5 space-y-4">
        <h2
          className="text-xs font-bold tracking-widest"
          style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
        >
          CAMERA WEAPON SETTINGS
        </h2>
        {loading ? (
          <p className="text-sm" style={{ color: "var(--dash-meta)" }}>
            Loading cameras...
          </p>
        ) : (
          <div className="space-y-3">
            {cameras.map((cam) => (
              <div key={cam.id} className="aegis-subcard p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold aegis-text-title">{cam.name}</p>
                    <p className="text-[10px]" style={{ color: "var(--dash-subtle)" }}>
                      Detections above min confidence create alerts; VLM reduces false positives.
                    </p>
                  </div>
                  <label
                    className="text-xs flex items-center gap-2 px-2 py-1 rounded border"
                    style={{
                      color: Boolean(cam.weapon_enabled) ? "#f87171" : "var(--dash-subtle)",
                      borderColor: Boolean(cam.weapon_enabled) ? "rgba(248,113,113,0.4)" : "var(--dash-sidebar-border)",
                      background: Boolean(cam.weapon_enabled) ? "rgba(239,68,68,0.08)" : "transparent",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={Boolean(cam.weapon_enabled)}
                      onChange={(e) =>
                        setCameras((prev) =>
                          prev.map((x) => (x.id === cam.id ? { ...x, weapon_enabled: e.target.checked } : x))
                        )
                      }
                    />
                    {Boolean(cam.weapon_enabled) ? "WEAPON ON" : "WEAPON OFF"}
                  </label>
                </div>
                <div className="flex items-end justify-between gap-3 flex-wrap">
                  <label className="text-[11px]">
                    <span style={{ color: "var(--dash-subtle)" }}>Weapon min confidence</span>
                    <input
                      type="number"
                      min={0.05}
                      max={0.99}
                      step={0.01}
                      disabled={!cam.weapon_enabled}
                      value={cam.weapon_confidence ?? 0.45}
                      onChange={(e) =>
                        setCameras((prev) =>
                          prev.map((x) =>
                            x.id === cam.id ? { ...x, weapon_confidence: Number(e.target.value) } : x
                          )
                        )
                      }
                      className="aegis-field w-32"
                    />
                  </label>
                  <button type="button" onClick={() => saveCamera(cam)} className="btn-aegis text-xs px-3 py-2">
                    <Save className="w-3.5 h-3.5" />
                    {savingId === cam.id ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="aegis-card p-5">
        <h2
          className="text-xs font-bold tracking-widest mb-3"
          style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}
        >
          RECENT WEAPON ALERTS
        </h2>
        {alerts.length === 0 ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--dash-subtle)" }}>
            <ShieldAlert className="w-4 h-4" />
            No weapon alerts yet.
          </div>
        ) : (
          <div className="space-y-2">
            {alerts.slice(0, 20).map((a) => (
              <div key={a.id} className="aegis-subcard p-3 text-xs">
                <div className="flex items-center justify-between">
                  <p className="inline-flex items-center gap-1.5" style={{ color: "#ef4444" }}>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {a.type} - Camera #{a.camera_id}
                  </p>
                  <p style={{ color: "var(--dash-subtle)" }}>{timeAgo(a.timestamp)}</p>
                </div>
                <p style={{ color: "var(--dash-subtle)" }}>{formatTs(a.timestamp)}</p>
                {a.notes ? <p style={{ color: "var(--dash-body-text)" }}>{String(a.notes)}</p> : null}
                {a.vlm_explanation ? (
                  <p className="mt-1 text-[10px]" style={{ color: "var(--dash-meta)" }}>
                    VLM: {String(a.vlm_explanation)}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
