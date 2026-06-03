"use client";

import { useCallback, useEffect, useState } from "react";
import { Building2, Loader2, Plus, Trash2, X, Check, Pencil } from "lucide-react";
import { Organization } from "@/types";
import {
  createOrganization,
  deleteOrganization,
  getOrganizations,
  updateOrganization,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import toast from "react-hot-toast";
import { formatTs } from "@/lib/utils";

export default function OrganizationsPage() {
  const user = useAuth((s) => s.user);
  const isPlatform = user?.role === "super_admin";
  const [rows, setRows] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Organization | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getOrganizations();
      setRows(data);
    } catch {
      toast.error("Failed to load organizations.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isPlatform) load();
  }, [isPlatform, load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await createOrganization({
        name: name.trim(),
        slug: slug.trim() || undefined,
      });
      toast.success("Organization created.");
      setShowCreate(false);
      setName("");
      setSlug("");
      load();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Create failed.";
      toast.error(String(msg));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(o: Organization) {
    if (!confirm(`Delete organization "${o.name}"? This only works if there are no users or cameras in it.`)) return;
    setDeletingId(o.id);
    try {
      await deleteOrganization(o.id);
      toast.success("Deleted.");
      load();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Delete failed.";
      toast.error(String(msg));
    } finally {
      setDeletingId(null);
    }
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setSaving(true);
    try {
      await updateOrganization(editing.id, {
        name: editing.name.trim(),
        slug: editing.slug?.trim() || null,
        is_active: editing.is_active,
      });
      toast.success("Saved.");
      setEditing(null);
      load();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Save failed.";
      toast.error(String(msg));
    } finally {
      setSaving(false);
    }
  }

  if (!isPlatform) {
    return (
      <div className="lumicams-card p-8 text-center fade-in" style={{ color: "var(--dash-subtle)" }}>
        <Building2 className="w-10 h-10 mx-auto mb-3 opacity-40" />
        <p className="text-sm font-semibold tracking-widest">PLATFORM ADMIN ONLY</p>
        <p className="text-xs mt-2 max-w-md mx-auto">
          Organization management is available to Lumicams super administrators. Create cameras and users with an
          organization from the Cameras and Users pages after an org exists.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-widest" style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}>
            ORGANIZATIONS
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
            Tenants — assign cameras and org users to each organization
          </p>
        </div>
        <button type="button" onClick={() => setShowCreate(true)} className="btn-lumicams text-xs">
          <Plus className="w-3.5 h-3.5" /> NEW ORGANIZATION
        </button>
      </div>

      <div className="lumicams-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full lumicams-table">
            <thead>
              <tr>
                <th className="text-left">ID</th>
                <th className="text-left">NAME</th>
                <th className="text-left">SLUG</th>
                <th className="text-left">ACTIVE</th>
                <th className="text-left">CREATED</th>
                <th className="text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto" style={{ color: "var(--dash-subtle)" }} />
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center" style={{ color: "var(--dash-meta)" }}>
                    No organizations yet. Create one to use in Users and Cameras.
                  </td>
                </tr>
              ) : (
                rows.map((o) => (
                  <tr key={o.id}>
                    <td style={{ color: "var(--dash-meta)", fontFamily: "var(--font-space-mono)" }}>#{o.id}</td>
                    <td style={{ color: "var(--dash-body-text)" }}>{o.name}</td>
                    <td style={{ color: "var(--dash-subtle)" }}>{o.slug ?? "—"}</td>
                    <td>
                      <span className={`status-dot ${o.is_active ? "active" : "inactive"} mr-1.5`} />
                      <span className="text-xs">{o.is_active ? "YES" : "NO"}</span>
                    </td>
                    <td style={{ color: "var(--dash-subtle)", fontSize: "0.75rem" }}>{formatTs(o.created_at)}</td>
                    <td>
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => setEditing(o)}
                          className="p-1.5 rounded transition-all"
                          style={{ color: "#00d4ff", background: "rgba(0,212,255,0.08)" }}
                          title="Edit"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(o)}
                          disabled={deletingId === o.id}
                          className="p-1.5 rounded transition-all"
                          style={{ color: "#ef4444", background: "rgba(239,68,68,0.08)" }}
                          title="Delete"
                        >
                          {deletingId === o.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setShowCreate(false)} />
          <div className="relative w-full max-w-md mx-4 lumicams-card p-6 z-10 fade-in">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-sm font-bold tracking-widest" style={{ fontFamily: "var(--font-orbitron)" }}>
                NEW ORGANIZATION
              </h3>
              <button type="button" onClick={() => setShowCreate(false)} style={{ color: "var(--dash-subtle)" }}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold mb-1 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
                  NAME
                </label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-md text-sm outline-none"
                  style={{
                    background: "var(--dash-alerts-bg, #0d1527)",
                    border: "1px solid var(--dash-sidebar-border)",
                    color: "var(--dash-body-text)",
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
                  SLUG (optional)
                </label>
                <input
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="acme-corp"
                  className="w-full px-3 py-2 rounded-md text-sm outline-none"
                  style={{
                    background: "var(--dash-alerts-bg, #0d1527)",
                    border: "1px solid var(--dash-sidebar-border)",
                    color: "var(--dash-body-text)",
                  }}
                />
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest"
                  style={{ background: "rgba(71,85,105,0.08)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-subtle)" }}
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest flex items-center justify-center gap-2"
                  style={{ background: "rgba(0,212,255,0.12)", border: "1px solid rgba(0,212,255,0.3)", color: "#00d4ff" }}
                >
                  {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                  CREATE
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setEditing(null)} />
          <div className="relative w-full max-w-md mx-4 lumicams-card p-6 z-10 fade-in">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-sm font-bold tracking-widest" style={{ fontFamily: "var(--font-orbitron)" }}>
                EDIT ORGANIZATION
              </h3>
              <button type="button" onClick={() => setEditing(null)} style={{ color: "var(--dash-subtle)" }}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleSaveEdit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold mb-1 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
                  NAME
                </label>
                <input
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  required
                  className="w-full px-3 py-2 rounded-md text-sm outline-none"
                  style={{
                    background: "var(--dash-alerts-bg, #0d1527)",
                    border: "1px solid var(--dash-sidebar-border)",
                    color: "var(--dash-body-text)",
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
                  SLUG
                </label>
                <input
                  value={editing.slug ?? ""}
                  onChange={(e) => setEditing({ ...editing, slug: e.target.value || null })}
                  className="w-full px-3 py-2 rounded-md text-sm outline-none"
                  style={{
                    background: "var(--dash-alerts-bg, #0d1527)",
                    border: "1px solid var(--dash-sidebar-border)",
                    color: "var(--dash-body-text)",
                  }}
                />
              </div>
              <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: "var(--dash-body-text)" }}>
                <input
                  type="checkbox"
                  checked={editing.is_active}
                  onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })}
                />
                Active
              </label>
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => setEditing(null)}
                  className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest"
                  style={{ background: "rgba(71,85,105,0.08)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-subtle)" }}
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest flex items-center justify-center gap-2"
                  style={{ background: "rgba(0,212,255,0.12)", border: "1px solid rgba(0,212,255,0.3)", color: "#00d4ff" }}
                >
                  {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                  SAVE
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
