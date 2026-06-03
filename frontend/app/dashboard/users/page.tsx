"use client";

import { useEffect, useState, useCallback } from "react";
import { Users, Plus, Trash2, Loader2, X, Check, ShieldCheck, User } from "lucide-react";
import { Organization, User as UserType } from "@/types";
import { createUser, deleteUser, getOrganizations, getUsers } from "@/lib/api";
import { formatTs } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import toast from "react-hot-toast";

function AddUserModal({ onClose, onSave }: { onClose: () => void; onSave: () => void }) {
  const me = useAuth((s) => s.user);
  const isPlatform = me?.role === "super_admin";
  const [email,    setEmail]    = useState("");
  const [name,     setName]     = useState("");
  const [password, setPassword] = useState("");
  const [role,     setRole]     = useState<"operator" | "org_admin" | "super_admin">("operator");
  const [orgs,     setOrgs]     = useState<Organization[]>([]);
  const [orgId,    setOrgId]    = useState<number | "">("");
  const [loading,  setLoading]  = useState(false);

  useEffect(() => {
    if (!isPlatform) return;
    getOrganizations().then(setOrgs).catch(() => setOrgs([]));
  }, [isPlatform]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const apiRole =
        role === "super_admin" ? "super_admin" : role === "org_admin" ? "org_admin" : "operator";
      const payload: Parameters<typeof createUser>[0] = {
        email,
        full_name: name,
        password,
        role: apiRole,
      };
      if (isPlatform && apiRole !== "super_admin") {
        if (orgId === "") {
          toast.error("Select an organization.");
          setLoading(false);
          return;
        }
        payload.organization_id = Number(orgId);
      }
      await createUser(payload);
      toast.success("User created.");
      onSave();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Create failed.";
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
      <div className="relative w-full max-w-md mx-4 lumicams-card p-6 z-10 fade-in">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-bold tracking-widest"
              style={{ fontFamily: "var(--font-orbitron)", color: "var(--dash-body-text)" }}>
            CREATE USER
          </h3>
          <button onClick={onClose} style={{ color: "var(--dash-subtle)" }}><X className="w-4 h-4" /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {[
            { label: "EMAIL", value: email, set: setEmail, type: "email", placeholder: "user@lumicams.com" },
            { label: "FULL NAME", value: name, set: setName, type: "text", placeholder: "John Doe" },
            { label: "PASSWORD (min 8 chars)", value: password, set: setPassword, type: "password", placeholder: "••••••••" },
          ].map(({ label, value, set, type, placeholder }) => (
            <div key={label}>
              <label className="block text-xs font-semibold mb-1.5 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
                {label}
              </label>
              <input
                type={type}
                value={value}
                onChange={(e) => set(e.target.value)}
                placeholder={placeholder}
                required={label !== "FULL NAME"}
                minLength={label.includes("PASSWORD") ? 8 : undefined}
                className="w-full px-3 py-2 rounded-md text-sm outline-none transition-all"
                style={inputStyle}
                onFocus={(e) => (e.target.style.borderColor = "rgba(0,212,255,0.5)")}
                onBlur={(e)  => (e.target.style.borderColor = "var(--dash-sidebar-border, #1a2540)")}
              />
            </div>
          ))}

          {/* Role select */}
          <div>
            <label className="block text-xs font-semibold mb-1.5 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
              ROLE
            </label>
            <div className="flex flex-wrap gap-2">
              {(
                isPlatform
                  ? (["operator", "org_admin", "super_admin"] as const)
                  : (["operator", "org_admin"] as const)
              ).map((r) => (
                <button
                  type="button"
                  key={r}
                  onClick={() => setRole(r)}
                  className="flex-1 min-w-[100px] py-2 rounded-md text-xs font-semibold tracking-widest transition-all"
                  style={role === r
                    ? { background: "rgba(0,212,255,0.12)", border: "1px solid rgba(0,212,255,0.3)", color: "#00d4ff" }
                    : { background: "rgba(71,85,105,0.08)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-subtle)" }
                  }
                >
                  {r.replace("_", " ").toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {isPlatform && role !== "super_admin" && (
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-widest" style={{ color: "var(--dash-subtle)" }}>
                ORGANIZATION
              </label>
              <select
                value={orgId === "" ? "" : String(orgId)}
                onChange={(e) => setOrgId(e.target.value ? Number(e.target.value) : "")}
                required
                className="w-full px-3 py-2 rounded-md text-sm outline-none"
                style={inputStyle}
              >
                <option value="">Select organization…</option>
                {orgs.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
                    className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest transition-all"
                    style={{ background: "rgba(71,85,105,0.08)", border: "1px solid var(--dash-sidebar-border)", color: "var(--dash-subtle)" }}>
              CANCEL
            </button>
            <button type="submit" disabled={loading}
                    className="flex-1 py-2 rounded-md text-xs font-semibold tracking-widest transition-all flex items-center justify-center gap-2"
                    style={{ background: "rgba(0,212,255,0.12)", border: "1px solid rgba(0,212,255,0.3)", color: "#00d4ff" }}>
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
              CREATE
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const currentUser = useAuth((s) => s.user);
  const [users,      setUsers]      = useState<UserType[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [showModal,  setShowModal]  = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [refreshTs,  setRefreshTs]  = useState(Date.now());

  const refresh = useCallback(() => setRefreshTs(Date.now()), []);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getUsers();
        setUsers(data);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [refreshTs]);

  async function handleDelete(user: UserType) {
    if (user.id === currentUser?.id) { toast.error("Cannot delete your own account."); return; }
    if (!confirm(`Delete user "${user.email}"?`)) return;
    setDeletingId(user.id);
    try {
      await deleteUser(user.id);
      toast.success("User deleted.");
      refresh();
    } catch { toast.error("Delete failed."); }
    finally { setDeletingId(null); }
  }

  return (
    <>
      {showModal && <AddUserModal onClose={() => setShowModal(false)} onSave={refresh} />}

      <div className="space-y-6 fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-widest"
                style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}>
              USER MANAGEMENT
            </h1>
            <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
              Lumicams platform admin, org admin, and operator roles
            </p>
          </div>
          <button onClick={() => setShowModal(true)} className="btn-lumicams text-xs">
            <Plus className="w-3.5 h-3.5" /> ADD USER
          </button>
        </div>

        <div className="lumicams-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full lumicams-table">
              <thead>
                <tr>
                  <th className="text-left">ID</th>
                  <th className="text-left">EMAIL</th>
                  <th className="text-left">NAME</th>
                  <th className="text-left">ROLE</th>
                  <th className="text-left">STATUS</th>
                  <th className="text-left">CREATED</th>
                  <th className="text-right">ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center">
                      <Loader2 className="w-5 h-5 animate-spin mx-auto" style={{ color: "var(--dash-subtle)" }} />
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-12 text-center" style={{ color: "var(--dash-meta)" }}>
                      No users found.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id}>
                      <td style={{ color: "var(--dash-meta)", fontFamily: "var(--font-space-mono)" }}>#{u.id}</td>
                      <td style={{ color: "var(--dash-body-text)" }}>
                        <div className="flex items-center gap-2">
                          {(u.role === "admin" || u.role === "org_admin" || u.role === "super_admin")
                            ? <ShieldCheck className="w-3.5 h-3.5 shrink-0" style={{ color: "#00d4ff" }} />
                            : <User        className="w-3.5 h-3.5 shrink-0" style={{ color: "var(--dash-subtle)" }} />
                          }
                          {u.email}
                          {u.id === currentUser?.id && (
                            <span className="text-xs px-1.5 py-0.5 rounded"
                                  style={{ background: "rgba(0,212,255,0.08)", color: "#00d4ff", fontSize: "10px" }}>
                              YOU
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ color: "var(--dash-body-text)" }}>{u.full_name ?? "—"}</td>
                      <td>
                        <span className="text-xs font-semibold tracking-wider px-2 py-0.5 rounded"
                              style={(u.role === "admin" || u.role === "org_admin" || u.role === "super_admin")
                                ? { background: "rgba(0,212,255,0.08)", color: "#00d4ff", border: "1px solid rgba(0,212,255,0.2)" }
                                : { background: "rgba(71,85,105,0.1)", color: "var(--dash-body-text)", border: "1px solid var(--dash-sidebar-border)" }
                              }>
                          {u.role.replace("_", " ").toUpperCase()}
                        </span>
                      </td>
                      <td>
                        <span className={`status-dot ${u.is_active ? "active" : "inactive"} mr-1.5`} />
                        <span className="text-xs" style={{ color: u.is_active ? "#22c55e" : "var(--dash-subtle)" }}>
                          {u.is_active ? "ACTIVE" : "DISABLED"}
                        </span>
                      </td>
                      <td style={{ color: "var(--dash-subtle)", fontSize: "0.75rem" }}>
                        {formatTs(u.created_at)}
                      </td>
                      <td>
                        <div className="flex items-center justify-end">
                          {u.id !== currentUser?.id && (
                            <button
                              onClick={() => handleDelete(u)}
                              disabled={deletingId === u.id}
                              className="p-1.5 rounded transition-all"
                              style={{ color: "#ef4444", background: "rgba(239,68,68,0.08)" }}
                              title="Delete user"
                            >
                              {deletingId === u.id
                                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                : <Trash2  className="w-3.5 h-3.5" />
                              }
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
