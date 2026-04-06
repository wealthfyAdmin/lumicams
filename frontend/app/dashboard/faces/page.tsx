"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, ScanFace, ShieldAlert, UserCheck, UserCircle2, Plus, Trash2, Wand2 } from "lucide-react";
import toast from "react-hot-toast";
import {
  createFaceIdentity,
  deleteFaceIdentity,
  enrollFaceIdentityByImage,
  extractFaceEmbeddingFromStoredPhoto,
  getFaceModuleStatus,
  getFaceAttendance,
  getFaceIdentities,
  getFaceSightings,
  repairMissingFaceEmbeddings,
  updateFaceIdentity,
  type FaceModuleStatus,
} from "@/lib/api";
import { FaceCategory, FaceIdentity, FaceSighting } from "@/types";
import { formatTs, timeAgo } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";

export default function FaceIntelligencePage() {
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [refreshTs, setRefreshTs] = useState(Date.now());
  const [identities, setIdentities] = useState<FaceIdentity[]>([]);
  const [sightings, setSightings] = useState<FaceSighting[]>([]);
  const [attendance, setAttendance] = useState<FaceSighting[]>([]);
  const isAdmin = useAuth((s) => s.isAdmin);
  const [savingIdentity, setSavingIdentity] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [employeeCode, setEmployeeCode] = useState("");
  const [category, setCategory] = useState<FaceCategory>("whitelist");
  const [embeddingsRaw, setEmbeddingsRaw] = useState("");
  const [faceFile, setFaceFile] = useState<File | null>(null);
  const [faceMode, setFaceMode] = useState<"embedding" | "image_only">("image_only");
  const [faceStatus, setFaceStatus] = useState<FaceModuleStatus | null>(null);
  const [repairingEmbeddings, setRepairingEmbeddings] = useState(false);
  const [repairingId, setRepairingId] = useState<number | null>(null);

  const refresh = useCallback(() => setRefreshTs(Date.now()), []);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [ids, s, a] = await Promise.all([
          getFaceIdentities({ active_only: true }),
          getFaceSightings({ hours, limit: 200 }),
          getFaceAttendance({ hours, limit: 200 }),
        ]);
        setIdentities(ids);
        setSightings(s);
        setAttendance(a);
        try {
          const st = await getFaceModuleStatus();
          setFaceStatus(st);
          setFaceMode(st.enroll_mode);
        } catch {
          setFaceStatus(null);
          setFaceMode("image_only");
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [hours, refreshTs]);

  const counts = useMemo(() => {
    const whitelist = identities.filter((x) => x.category === "whitelist").length;
    const blacklist = identities.filter((x) => x.category === "blacklist").length;
    const neutral = identities.filter((x) => x.category === "neutral").length;
    const blackAlerts = sightings.filter((x) => x.event_type === "blacklist_alert").length;
    return { whitelist, blacklist, neutral, blackAlerts };
  }, [identities, sightings]);

  async function handleCreateIdentity(e: React.FormEvent) {
    e.preventDefault();
    if (!isAdmin) return;
    setSavingIdentity(true);
    setStatusMsg(null);
    try {
      const nm = name.trim();
      if (!nm) throw new Error("Name is required.");
      if (faceFile) {
        await enrollFaceIdentityByImage({
          name: nm,
          employee_code: employeeCode.trim() || undefined,
          category,
          image: faceFile,
        });
      } else {
        let embeddings: number[][] = [];
        const raw = embeddingsRaw.trim();
        if (raw) {
          const parsed = JSON.parse(raw) as unknown;
          if (!Array.isArray(parsed)) {
            throw new Error("Embeddings must be a JSON array.");
          }
          if (parsed.length && Array.isArray(parsed[0])) {
            embeddings = parsed as number[][];
          } else {
            embeddings = [parsed as number[]];
          }
        }
        await createFaceIdentity({
          name: nm,
          employee_code: employeeCode.trim() || undefined,
          category,
          embeddings,
          is_active: true,
        });
      }
      setName("");
      setEmployeeCode("");
      setEmbeddingsRaw("");
      setFaceFile(null);
      setCategory("whitelist");
      setStatusMsg("Identity added.");
      refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to add identity.";
      setStatusMsg(msg);
    } finally {
      setSavingIdentity(false);
    }
  }

  async function handleQuickCategory(idn: FaceIdentity, next: FaceCategory) {
    if (!isAdmin || idn.category === next) return;
    await updateFaceIdentity(idn.id, { category: next });
    refresh();
  }

  async function handleDeleteIdentity(idn: FaceIdentity) {
    if (!isAdmin) return;
    const ok = confirm(`Delete identity "${idn.name}"?`);
    if (!ok) return;
    await deleteFaceIdentity(idn.id);
    refresh();
  }

  async function handleRepairAllEmbeddings() {
    if (!isAdmin) return;
    setRepairingEmbeddings(true);
    try {
      const r = await repairMissingFaceEmbeddings();
      if (r.repaired_count > 0) {
        toast.success(`Built embeddings for ${r.repaired_count} person(s). Blacklist matching is ready after refresh.`);
      }
      if (r.failed_count > 0) {
        const first = r.failed[0];
        toast.error(
          `${r.failed_count} could not be fixed${first ? ` (${first.name}: ${first.reason})` : ""}. Try a clearer photo.`
        );
      }
      if (r.repaired_count === 0 && r.failed_count === 0) {
        toast("No identities needed repair.", { icon: "ℹ️" });
      }
      refresh();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      toast.error(ax.response?.data?.detail ?? "Repair failed.");
    } finally {
      setRepairingEmbeddings(false);
    }
  }

  async function handleExtractOne(idn: FaceIdentity) {
    if (!isAdmin) return;
    setRepairingId(idn.id);
    try {
      await extractFaceEmbeddingFromStoredPhoto(idn.id);
      toast.success(`Embedding saved for ${idn.name}.`);
      refresh();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      toast.error(ax.response?.data?.detail ?? "Extraction failed.");
    } finally {
      setRepairingId(null);
    }
  }

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1
            className="text-xl font-bold tracking-widest flex items-center gap-2"
            style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}
          >
            <ScanFace className="w-6 h-6" />
            FACE INTELLIGENCE
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            Whitelist attendance · blacklist watchlist · neutral recognition
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="aegis-control cursor-pointer"
          >
            <option value={12}>Last 12h</option>
            <option value={24}>Last 24h</option>
            <option value={72}>Last 72h</option>
            <option value={168}>Last 7d</option>
          </select>
          <button onClick={refresh} className="btn-aegis text-xs">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            REFRESH
          </button>
        </div>
      </div>

      {faceStatus?.camera_pipeline_enabled === false && (
        <div className="aegis-banner aegis-banner--warn">
          <strong>Camera matching is currently off.</strong> Enable Face Intelligence for cameras from admin settings.
        </div>
      )}
      {faceStatus?.camera_pipeline_enabled && faceStatus.enroll_mode === "embedding" && (
        <div className="aegis-banner aegis-banner--success">
          <strong>Face recognition is active.</strong> Blacklist, whitelist attendance, and neutral recognition are enabled.
        </div>
      )}
      {faceStatus?.camera_pipeline_enabled && faceStatus.enroll_mode === "image_only" && (
        <div className="aegis-banner aegis-banner--warn">
          <strong>Face recognition is not ready yet.</strong> Please contact system admin to enable backend recognition service.
        </div>
      )}
      {faceStatus?.camera_pipeline_enabled &&
        faceStatus.enroll_mode === "embedding" &&
        (faceStatus.identities_with_embeddings ?? 0) === 0 &&
        (faceStatus.active_identities ?? 0) > 0 && (
          <div className="aegis-banner aegis-banner--danger flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p>
              <strong>No embeddings on file.</strong> Your blacklist person was saved before vectors were available, or
              the photo could not be analyzed. Use the saved photo to build vectors automatically (one click), or re-upload
              a clear single face.
            </p>
            {isAdmin && (
              <button
                type="button"
                disabled={repairingEmbeddings}
                onClick={() => void handleRepairAllEmbeddings()}
                className="btn-aegis text-xs shrink-0 whitespace-nowrap"
              >
                <Wand2 className={`w-3.5 h-3.5 ${repairingEmbeddings ? "animate-spin" : ""}`} />
                {repairingEmbeddings ? "BUILDING…" : "BUILD FROM SAVED PHOTOS"}
              </button>
            )}
          </div>
        )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat title="WHITELIST" value={counts.whitelist} icon={<UserCheck className="w-4 h-4" />} color="#22c55e" />
        <Stat title="BLACKLIST" value={counts.blacklist} icon={<ShieldAlert className="w-4 h-4" />} color="#ef4444" />
        <Stat title="NEUTRAL" value={counts.neutral} icon={<UserCircle2 className="w-4 h-4" />} color="#94a3b8" />
        <Stat title="BLACKLIST ALERTS" value={counts.blackAlerts} icon={<ShieldAlert className="w-4 h-4" />} color="#f43f5e" />
      </div>

      <section className="aegis-card p-4">
        <h2 className="text-xs font-bold tracking-widest mb-3" style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
          ADD IDENTITY (WHITELIST / BLACKLIST / NEUTRAL)
        </h2>
        {!isAdmin ? (
          <p className="text-xs" style={{ color: "var(--dash-subtle)" }}>
            Only admin can add or modify face identities.
          </p>
        ) : (
          <form onSubmit={handleCreateIdentity} className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs" style={{ color: "var(--dash-subtle)" }}>
              Name
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="aegis-field"
              />
            </label>
            <label className="text-xs" style={{ color: "var(--dash-subtle)" }}>
              Employee Code (optional)
              <input
                value={employeeCode}
                onChange={(e) => setEmployeeCode(e.target.value)}
                className="aegis-field"
              />
            </label>
            <label className="text-xs" style={{ color: "var(--dash-subtle)" }}>
              Category
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as FaceCategory)}
                className="aegis-field cursor-pointer"
              >
                <option value="whitelist">whitelist</option>
                <option value="blacklist">blacklist</option>
                <option value="neutral">neutral</option>
              </select>
            </label>
            <label className="text-xs" style={{ color: "var(--dash-subtle)" }}>
              Face Image (recommended)
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setFaceFile(e.target.files?.[0] ?? null)}
                className="aegis-field file:mr-2 file:text-xs"
              />
            </label>
            <label className="text-xs md:col-span-2" style={{ color: "var(--dash-subtle)" }}>
              Embeddings JSON (optional now, required for real matching)
              <textarea
                value={embeddingsRaw}
                onChange={(e) => setEmbeddingsRaw(e.target.value)}
                rows={3}
                placeholder='Example: [[0.12, -0.03, ...], [0.10, -0.02, ...]]'
                className="aegis-field font-mono"
              />
            </label>
            <div className="md:col-span-2 flex items-center justify-between">
              <p
                className="text-[10px]"
                style={{
                  color: statusMsg?.toLowerCase().includes("fail") ? "#dc2626" : "var(--dash-subtle)",
                }}
              >
                {statusMsg ?? "Upload one clear front-face photo for automatic enrollment (best)."}
              </p>
              <button type="submit" disabled={savingIdentity} className="btn-aegis text-xs">
                <Plus className={`w-3.5 h-3.5 ${savingIdentity ? "animate-spin" : ""}`} />
                ADD IDENTITY
              </button>
            </div>
            {faceMode === "image_only" && (
              <div className="aegis-banner aegis-banner--warn md:col-span-2 text-[10px]">
                Recognition vectors are not available currently. Uploaded faces will be saved, but live blacklist matching remains off.
              </div>
            )}
          </form>
        )}
      </section>

      <section className="aegis-card p-4">
        <h2 className="text-xs font-bold tracking-widest mb-3" style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
          WATCHLIST EVENTS (BLACKLIST)
        </h2>
        <FaceList rows={sightings.filter((x) => x.event_type === "blacklist_alert")} empty="No blacklist events." />
      </section>

      <section className="aegis-card p-4">
        <h2 className="text-xs font-bold tracking-widest mb-3" style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
          ATTENDANCE LOG (WHITELIST)
        </h2>
        <FaceList rows={attendance} empty="No attendance sightings." />
      </section>

      <section className="aegis-card p-4">
        <h2 className="text-xs font-bold tracking-widest mb-3" style={{ color: "var(--dash-body-text)", fontFamily: "var(--font-orbitron)" }}>
          KNOWN IDENTITIES
        </h2>
        {identities.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--dash-subtle)" }}>
            No identities registered yet. Add whitelist, blacklist, or neutral people to start face monitoring.
          </p>
        ) : (
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-2">
            {identities.map((idn) => (
              <div key={idn.id} className="aegis-subcard p-3 rounded">
                <div className="flex items-center gap-2">
                  <FaceAvatar path={idn.face_image_path ?? undefined} />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate aegis-text-title">
                      Person: {idn.name}
                    </p>
                    <p className="text-[11px] font-mono mt-0.5 truncate" style={{ color: "var(--dash-subtle)" }}>
                      Employee: {idn.employee_code || "—"}
                    </p>
                  </div>
                </div>
                <p
                  className="text-[10px] mt-1 uppercase tracking-wider"
                  style={{
                    color:
                      idn.category === "whitelist"
                        ? "#22c55e"
                        : idn.category === "blacklist"
                          ? "#ef4444"
                          : "#94a3b8",
                  }}
                >
                  {idn.category}
                </p>
                {!identityHasEmbeddings(idn) && idn.face_image_path && isAdmin && (
                  <button
                    type="button"
                    disabled={repairingId === idn.id}
                    onClick={() => void handleExtractOne(idn)}
                    className="mt-2 w-full btn-aegis text-[10px] py-1.5 justify-center"
                  >
                    <Wand2 className={`w-3 h-3 ${repairingId === idn.id ? "animate-spin" : ""}`} />
                    {repairingId === idn.id ? "EXTRACTING…" : "BUILD EMBEDDING FROM PHOTO"}
                  </button>
                )}
                {isAdmin && (
                  <div className="mt-2 flex items-center gap-1.5">
                    {(["whitelist", "blacklist", "neutral"] as FaceCategory[]).map((c) => (
                      <button
                        key={c}
                        onClick={() => void handleQuickCategory(idn, c)}
                        className="text-[10px] px-1.5 py-0.5 rounded border"
                        style={{
                          borderColor: idn.category === c ? "rgba(0,212,255,0.35)" : "var(--dash-sidebar-border)",
                          color: idn.category === c ? "#00d4ff" : "var(--dash-subtle)",
                          background: idn.category === c ? "rgba(0,212,255,0.08)" : "transparent",
                        }}
                      >
                        {c}
                      </button>
                    ))}
                    <button
                      onClick={() => void handleDeleteIdentity(idn)}
                      className="ml-auto p-1 rounded border"
                      style={{ borderColor: "var(--dash-sidebar-border)", color: "#ef4444" }}
                      title="Delete identity"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function identityHasEmbeddings(idn: FaceIdentity): boolean {
  const e = idn.embeddings;
  return Array.isArray(e) && e.length > 0 && e.some((x) => Array.isArray(x) && x.length > 0);
}

function FaceList({ rows, empty }: { rows: FaceSighting[]; empty: string }) {
  if (!rows.length) {
    return <p className="text-xs" style={{ color: "var(--dash-subtle)" }}>{empty}</p>;
  }
  return (
    <div className="space-y-1.5 max-h-[320px] overflow-y-auto">
      {rows.slice(0, 120).map((r) => (
        <div
          key={r.id}
          className="aegis-subcard flex items-center justify-between gap-2 p-2 rounded"
        >
          <div className="min-w-0">
            <p className="text-xs font-semibold truncate aegis-text-title">
              {r.identity_name || `Identity #${r.identity_id ?? "Unknown"}`}
            </p>
            <p className="text-[10px] truncate" style={{ color: "var(--dash-subtle)" }}>
              Cam #{r.camera_id} · {r.event_type}
              {r.confidence != null ? ` · ${(r.confidence * 100).toFixed(1)}%` : ""}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-[10px]" style={{ color: "var(--dash-subtle)", fontFamily: "var(--font-space-mono)" }}>
              {timeAgo(r.timestamp)}
            </p>
            <p className="text-[10px]" style={{ color: "var(--dash-meta)", fontFamily: "var(--font-space-mono)" }}>
              {formatTs(r.timestamp)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function Stat({
  title,
  value,
  icon,
  color,
}: {
  title: string;
  value: number;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <div className="aegis-card p-3">
      <p className="text-[10px] tracking-widest flex items-center gap-1.5" style={{ color: "var(--dash-subtle)" }}>
        {icon} {title}
      </p>
      <p className="text-2xl font-bold mt-1" style={{ color, fontFamily: "var(--font-orbitron)" }}>
        {value}
      </p>
    </div>
  );
}

function FaceAvatar({ path }: { path?: string }) {
  const src = faceImageUrl(path);
  if (!src) {
    return (
      <div
        className="w-11 h-11 rounded-md border flex items-center justify-center text-[9px]"
        style={{ borderColor: "var(--dash-sidebar-border)", color: "var(--dash-subtle)" }}
      >
        N/A
      </div>
    );
  }
  return (
    <img
      src={src}
      alt="Person face"
      className="w-11 h-11 rounded-md object-cover border"
      style={{ borderColor: "var(--dash-sidebar-border)" }}
    />
  );
}

function faceImageUrl(path?: string): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/$/, "");
  const clean = path.replace(/\\/g, "/");
  if (clean.startsWith("/")) return `${apiBase}${clean}`;
  if (clean.startsWith("snapshots/")) return `${apiBase.replace(/\/api$/, "")}/${clean}`;
  return `${apiBase}/${clean}`;
}

