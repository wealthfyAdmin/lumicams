"use client";

import { useEffect, useMemo, useState } from "react";
import { HardHat, Save, ShieldAlert, Settings2, CheckCircle2 } from "lucide-react";
import { getAlerts, getCameraPpeStatus, getCameras, updateCamera, type CameraPpeStatus } from "@/lib/api";
import { Camera } from "@/types";
import { formatTs, timeAgo } from "@/lib/utils";

const EQUIPMENT = ["helmet", "vest", "gloves", "boots", "goggles", "mask", "kit"];
const EQ_LABEL: Record<string, string> = {
  helmet: "HELMET / HARDHAT",
  vest: "SAFETY VEST",
  gloves: "GLOVES",
  boots: "BOOTS / SHOES",
  goggles: "GOGGLES",
  mask: "MASK",
  kit: "FULL KIT",
};

export default function PpePage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [ppeStatus, setPpeStatus] = useState<CameraPpeStatus | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [cams, ppeAlerts] = await Promise.all([
          getCameras(),
          getAlerts({ limit: 100, alert_type: "PPE" }),
        ]);
        setCameras(cams);
        setAlerts(ppeAlerts);
        const probe = cams.find((c: Camera) => c.status === "active") ?? cams[0];
        if (probe) {
          try {
            const st = await getCameraPpeStatus(probe.id);
            setPpeStatus(st);
          } catch {
            setPpeStatus(null);
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
        ppe_enabled: Boolean(cam.ppe_enabled),
        ppe_items: Array.isArray(cam.ppe_items) ? cam.ppe_items : [],
        ppe_confidence: cam.ppe_enabled ? (cam.ppe_confidence ?? 0.45) : null,
      });
    } finally {
      setSavingId(null);
    }
  }

  const activeCount = useMemo(() => cameras.filter((c) => c.ppe_enabled).length, [cameras]);

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-md font-bold tracking-widest" style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}>
            PPE COMPLIANCE
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            Configure camera-wise PPE checks (helmet only or full kit) and monitor PPE alerts.
          </p>
        </div>
        <div className="text-[11px] px-3 py-1.5 rounded-md border inline-flex items-center gap-2"
             style={{ color: "var(--dash-body-text)", borderColor: "var(--dash-sidebar-border)", background: "rgba(0,212,255,0.06)" }}>
          <Settings2 className="w-3.5 h-3.5" />
          Per-camera configurable PPE module
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="aegis-card p-4">
          <p className="text-xs tracking-widest" style={{ color: "var(--dash-subtle)" }}>CAMERAS WITH PPE ON</p>
          <p className="text-xl font-bold mt-1" style={{ color: "#34d399" }}>{activeCount}</p>
        </div>
        <div className="aegis-card p-4">
          <p className="text-xs tracking-widest" style={{ color: "var(--dash-subtle)" }}>PPE ALERTS (RECENT)</p>
          <p className="text-xl font-bold mt-1" style={{ color: "#f59e0b" }}>{alerts.length}</p>
        </div>
        <div className="aegis-card p-4 flex items-center gap-3">
          <HardHat className="w-6 h-6" style={{ color: "#00d4ff" }} />
          <p className="text-xs" style={{ color: "var(--dash-body-text)" }}>
            Alerts trigger only for selected missing equipment.
          </p>
        </div>
      </div>

      {ppeStatus && (
        <div className={`aegis-banner ${ppeStatus.model_loaded ? "aegis-banner--success" : "aegis-banner--warn"}`}>
          {ppeStatus.model_loaded ? (
            <span>
              PPE engine is ready
              {ppeStatus.aux_model_loaded ? " (dual-model)." : "."}
              {" "}Required items: {(ppeStatus.required_items ?? []).join(", ") || "none"}.
            </span>
          ) : (
            <span>
              PPE engine is not ready. Start camera processor and ensure model file exists at
              {" "}
              <code>{ppeStatus.model_path}</code>.
            </span>
          )}
        </div>
      )}

      <div className="aegis-card p-5 space-y-4">
        <h2 className="text-xs font-bold tracking-widest" style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
          CAMERA PPE SETTINGS
        </h2>
        {loading ? (
          <p className="text-sm" style={{ color: "var(--dash-meta)" }}>Loading cameras...</p>
        ) : (
          <div className="space-y-3">
            {cameras.map((cam) => (
              <div key={cam.id} className="aegis-subcard p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold aegis-text-title">{cam.name}</p>
                    <p className="text-[10px]" style={{ color: "var(--dash-subtle)" }}>
                      Select missing safety equipment to trigger alerts
                    </p>
                  </div>
                  <label className="text-xs flex items-center gap-2 px-2 py-1 rounded border"
                         style={{
                           color: Boolean(cam.ppe_enabled) ? "#34d399" : "var(--dash-subtle)",
                           borderColor: Boolean(cam.ppe_enabled) ? "rgba(52,211,153,0.4)" : "var(--dash-sidebar-border)",
                           background: Boolean(cam.ppe_enabled) ? "rgba(16,185,129,0.08)" : "transparent",
                         }}>
                    <input
                      type="checkbox"
                      checked={Boolean(cam.ppe_enabled)}
                      onChange={(e) =>
                        setCameras((prev) =>
                          prev.map((x) => (x.id === cam.id ? { ...x, ppe_enabled: e.target.checked } : x))
                        )
                      }
                    />
                    {Boolean(cam.ppe_enabled) ? "PPE ON" : "PPE OFF"}
                  </label>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
                  {EQUIPMENT.map((eq) => {
                    const active = (cam.ppe_items ?? []).includes(eq);
                    return (
                      <button
                        key={eq}
                        type="button"
                        disabled={!cam.ppe_enabled}
                        className="px-2 py-1.5 text-[10px] rounded border font-semibold tracking-wide"
                        style={{
                          borderColor: active ? "rgba(16,185,129,0.35)" : "var(--dash-sidebar-border)",
                          background: active ? "rgba(16,185,129,0.08)" : "transparent",
                          color: active ? "#34d399" : "var(--dash-body-text)",
                          opacity: cam.ppe_enabled ? 1 : 0.55,
                        }}
                        onClick={() =>
                          setCameras((prev) =>
                            prev.map((x) =>
                              x.id !== cam.id
                                ? x
                                : {
                                    ...x,
                                    ppe_items: (x.ppe_items ?? []).includes(eq)
                                      ? (x.ppe_items ?? []).filter((i) => i !== eq)
                                      : [...(x.ppe_items ?? []), eq],
                                  }
                            )
                          )
                        }
                      >
                        {EQ_LABEL[eq] ?? eq.toUpperCase()}
                      </button>
                    );
                  })}
                </div>
                <div className="flex items-end justify-between gap-3 flex-wrap">
                  <label className="text-[11px]">
                    <span style={{ color: "var(--dash-subtle)" }}>PPE Min Confidence</span>
                    <input
                      type="number"
                      min={0.05}
                      max={0.99}
                      step={0.01}
                      disabled={!cam.ppe_enabled}
                      value={cam.ppe_confidence ?? 0.45}
                      onChange={(e) =>
                        setCameras((prev) =>
                          prev.map((x) =>
                            x.id === cam.id ? { ...x, ppe_confidence: Number(e.target.value) } : x
                          )
                        )
                      }
                      className="aegis-field w-32"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => saveCamera(cam)}
                    className="btn-aegis text-xs px-3 py-2"
                  >
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
        <h2 className="text-xs font-bold tracking-widest mb-3" style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
          RECENT PPE ALERTS
        </h2>
        {alerts.length === 0 ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--dash-subtle)" }}>
            <ShieldAlert className="w-4 h-4" />
            No PPE alerts yet.
          </div>
        ) : (
          <div className="space-y-2">
            {alerts.slice(0, 20).map((a) => (
              <div key={a.id} className="aegis-subcard p-3 text-xs">
                <div className="flex items-center justify-between">
                  <p className="inline-flex items-center gap-1.5" style={{ color: "#f59e0b" }}>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {a.type} - Camera #{a.camera_id}
                  </p>
                  <p style={{ color: "var(--dash-subtle)" }}>{timeAgo(a.timestamp)}</p>
                </div>
                <p style={{ color: "var(--dash-subtle)" }}>{formatTs(a.timestamp)}</p>
                {a.notes ? (
                  <>
                    <p style={{ color: "var(--dash-body-text)" }}>
                      {String(a.notes).split("|")[0].trim()}
                    </p>
                    {String(a.notes).includes("| required:") && (
                      <p style={{ color: "var(--dash-subtle)" }}>
                        {String(a.notes).split("|")[1].trim()}
                      </p>
                    )}
                  </>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
