"use client";

import { useCallback, useEffect, useState } from "react";
import { Mail, MessageCircle, Server, Brain, Shield, Database, Save, Send } from "lucide-react";
import toast from "react-hot-toast";
import { useAuth } from "@/hooks/useAuth";
import {
  getNotificationSettings,
  patchNotificationSettings,
  testNotificationSettings,
  type NotificationSettingsDTO,
} from "@/lib/api";

interface SettingRow {
  key: string;
  value: string;
  note?: string;
}

function SettingsSection({ title, icon: Icon, rows }: { title: string; icon: React.ElementType; rows: SettingRow[] }) {
  return (
    <div className="aegis-card overflow-hidden">
      <div
        className="flex items-center gap-2 px-5 py-3"
        style={{ borderBottom: "1px solid var(--dash-sidebar-border)" }}
      >
        <Icon className="w-4 h-4" style={{ color: "#00d4ff" }} />
        <h2
          className="text-xs font-bold tracking-widest"
          style={{ fontFamily: "var(--font-orbitron)", color: "var(--dash-body-text)" }}
        >
          {title}
        </h2>
      </div>
      <table className="w-full aegis-table">
        <tbody>
          {rows.map(({ key, value, note }) => (
            <tr key={key}>
              <td className="w-1/3" style={{ color: "var(--dash-subtle)" }}>
                {key}
              </td>
              <td style={{ color: "#00d4ff", fontFamily: "var(--font-space-mono)", fontSize: "0.8rem" }}>{value}</td>
              {note && (
                <td style={{ color: "var(--dash-meta)", fontSize: "0.75rem" }}>
                  {note}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function labelCls() {
  return "block text-[0.65rem] font-bold tracking-wider mb-1";
}

function inputCls() {
  return "w-full rounded-md px-3 py-2 text-sm border outline-none transition-colors";
}

export default function SettingsPage() {
  const isAdmin = useAuth((s) => s.isAdmin);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [ns, setNs] = useState<NotificationSettingsDTO | null>(null);
  const [emailList, setEmailList] = useState("");
  const [waList, setWaList] = useState("");
  const [newSmtpPass, setNewSmtpPass] = useState("");
  const [newWaToken, setNewWaToken] = useState("");

  const load = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const data = await getNotificationSettings();
      setNs(data);
      setEmailList(
        (data.email_recipients && data.email_recipients.length > 0
          ? data.email_recipients
          : data.default_owner_email
          ? [data.default_owner_email]
          : []
        ).join(", ")
      );
      setWaList((data.whatsapp_recipients || []).join(", "));
    } catch {
      toast.error("Could not load notification settings (admin only).");
      setNs(null);
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    if (!ns) return;
    setSaving(true);
    try {
      const emails = emailList
        .split(/[,;\n]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const phones = waList
        .split(/[,;\n\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const patchBody: Parameters<typeof patchNotificationSettings>[0] = {
        smtp_enabled: ns.smtp_enabled,
        smtp_host: ns.smtp_host,
        smtp_port: ns.smtp_port,
        smtp_use_implicit_ssl: ns.smtp_use_implicit_ssl,
        smtp_username: ns.smtp_username,
        smtp_from_email: ns.smtp_from_email,
        default_owner_email: ns.default_owner_email,
        email_recipients: emails,
        public_dashboard_url: ns.public_dashboard_url,
        whatsapp_enabled: ns.whatsapp_enabled,
        ultramsg_instance_id: ns.ultramsg_instance_id,
        whatsapp_recipients: phones,
        email_subject_template: ns.email_subject_template,
        email_body_template: ns.email_body_template,
        whatsapp_body_template: ns.whatsapp_body_template,
      };
      if (newSmtpPass.trim()) patchBody.smtp_password = newSmtpPass.trim();
      if (newWaToken.trim()) patchBody.ultramsg_token = newWaToken.trim();

      const updated = await patchNotificationSettings(patchBody);
      setNs(updated);
      setNewSmtpPass("");
      setNewWaToken("");
      toast.success("Notification settings saved.");
      await load();
    } catch {
      toast.error("Save failed. Check fields and try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    try {
      const r = await testNotificationSettings();
      const em = r.email;
      if (em?.ok) toast.success("Test email sent.");
      else toast(em?.detail ? `Email: ${em.detail}` : "Email test skipped or failed.", { icon: "✉️" });
      const wa = r.whatsapp;
      if (Array.isArray(wa)) {
        wa.forEach((x) => {
          if (x.ok) toast.success(`WhatsApp OK → ${x.to}`);
          else toast.error(`WhatsApp ${x.to}: ${x.detail}`);
        });
      } else if (wa && "ok" in wa && !wa.ok) {
        toast(wa.detail || "WhatsApp test skipped.", { icon: "💬" });
      }
    } catch {
      toast.error("Test request failed.");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-6 fade-in">
      <div>
        <h1
          className="text-xl font-bold tracking-widest"
          style={{ fontFamily: "var(--font-orbitron)", color: "#00d4ff" }}
        >
          SYSTEM SETTINGS
        </h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--dash-subtle)" }}>
          Reference values below; admins can configure alert delivery ({`email + WhatsApp`}) in the first panel.
        </p>
      </div>

      {isAdmin && (
        <div
          className="aegis-card overflow-hidden p-5 space-y-5"
          style={{ borderColor: "var(--dash-sidebar-border)" }}
        >
          <div className="flex items-center gap-2 flex-wrap justify-between">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-cyan-400" />
              <h2
                className="text-xs font-bold tracking-widest"
                style={{ fontFamily: "var(--font-orbitron)", color: "var(--dash-body-text)" }}
              >
                ALERT NOTIFICATIONS
              </h2>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleTest}
                disabled={testing || loading || !ns}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border transition-opacity disabled:opacity-50"
                style={{
                  borderColor: "var(--dash-sidebar-border)",
                  color: "var(--dash-body-text)",
                }}
              >
                <Send className="w-3.5 h-3.5" />
                {testing ? "Testing…" : "Send test"}
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || loading || !ns}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold text-black bg-cyan-400 hover:bg-cyan-300 transition-colors disabled:opacity-50"
              >
                <Save className="w-3.5 h-3.5" />
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>

          {loading && (
            <p className="text-xs" style={{ color: "var(--dash-subtle)" }}>
              Loading…
            </p>
          )}
          {ns && (
            <>
              <p className="text-[0.7rem] leading-relaxed" style={{ color: "var(--dash-meta)" }}>
                When any alert is saved (fire, fall, crowd, face, PPE), the server sends a detailed plain-text and HTML
                email (optional snapshot attachment) and/or a WhatsApp message per{" "}
                <a
                  href="https://docs.ultramsg.com/"
                  target="_blank"
                  rel="noreferrer"
                  className="underline text-cyan-400"
                >
                  Ultramsg
                </a>{" "}
                (<code className="text-[0.65rem]">POST …/messages/chat</code>). Leave password or token blank to keep the
                current saved secret.
              </p>

              <div className="grid gap-4 md:grid-cols-2">
                <div
                  className="rounded-lg p-4 space-y-3"
                  style={{ background: "var(--dash-surface-2)", border: "1px solid var(--dash-sidebar-border)" }}
                >
                  <div className="flex items-center gap-2 text-cyan-400">
                    <Mail className="w-4 h-4" />
                    <span className="text-[0.7rem] font-bold tracking-wider">SMTP email</span>
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer text-xs">
                    <input
                      type="checkbox"
                      checked={ns.smtp_enabled}
                      onChange={(e) => setNs({ ...ns, smtp_enabled: e.target.checked })}
                    />
                    Enable email alerts
                  </label>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      SMTP host
                    </span>
                    <input
                      className={inputCls()}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      value={ns.smtp_host}
                      onChange={(e) => setNs({ ...ns, smtp_host: e.target.value })}
                      placeholder="smtp.example.com"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                        Port
                      </span>
                      <input
                        type="number"
                        className={inputCls()}
                        style={{
                          background: "var(--dash-bg)",
                          borderColor: "var(--dash-sidebar-border)",
                          color: "var(--dash-body-text)",
                        }}
                        value={ns.smtp_port}
                        onChange={(e) => setNs({ ...ns, smtp_port: Number(e.target.value) || 465 })}
                      />
                    </div>
                    <label className="flex items-end gap-2 cursor-pointer text-xs pb-2">
                      <input
                        type="checkbox"
                        checked={ns.smtp_use_implicit_ssl}
                        onChange={(e) => setNs({ ...ns, smtp_use_implicit_ssl: e.target.checked })}
                      />
                      SSL (port 465)
                    </label>
                  </div>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      Username
                    </span>
                    <input
                      className={inputCls()}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      value={ns.smtp_username}
                      onChange={(e) => setNs({ ...ns, smtp_username: e.target.value })}
                    />
                  </div>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      Password {ns.smtp_password_configured ? "(saved — leave blank to keep)" : ""}
                    </span>
                    <input
                      type="password"
                      className={inputCls()}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      placeholder="••••••••"
                      autoComplete="new-password"
                      value={newSmtpPass}
                      onChange={(e) => setNewSmtpPass(e.target.value)}
                    />
                  </div>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      From (sender) address
                    </span>
                    <input
                      className={inputCls()}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      value={ns.smtp_from_email}
                      onChange={(e) => setNs({ ...ns, smtp_from_email: e.target.value })}
                    />
                  </div>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      Default / owner email (always notified if SMTP on)
                    </span>
                    <input
                      className={inputCls()}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      value={ns.default_owner_email}
                      onChange={(e) => setNs({ ...ns, default_owner_email: e.target.value })}
                    />
                  </div>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      Extra recipients (comma-separated)
                    </span>
                    <textarea
                      className={`${inputCls()} min-h-[72px]`}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      value={emailList}
                      onChange={(e) => setEmailList(e.target.value)}
                      placeholder="ops@company.com, security@company.com"
                    />
                  </div>
                </div>

                <div
                  className="rounded-lg p-4 space-y-3"
                  style={{ background: "var(--dash-surface-2)", border: "1px solid var(--dash-sidebar-border)" }}
                >
                  <div className="flex items-center gap-2 text-emerald-400">
                    <MessageCircle className="w-4 h-4" />
                    <span className="text-[0.7rem] font-bold tracking-wider">WhatsApp (Ultramsg)</span>
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer text-xs">
                    <input
                      type="checkbox"
                      checked={ns.whatsapp_enabled}
                      onChange={(e) => setNs({ ...ns, whatsapp_enabled: e.target.checked })}
                    />
                    Enable WhatsApp alerts
                  </label>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      Instance ID
                    </span>
                    <input
                      className={inputCls()}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      value={ns.ultramsg_instance_id}
                      onChange={(e) => setNs({ ...ns, ultramsg_instance_id: e.target.value })}
                      placeholder="from Ultramsg dashboard"
                    />
                  </div>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      API token {ns.ultramsg_token_configured ? "(saved — leave blank to keep)" : ""}
                    </span>
                    <input
                      type="password"
                      className={inputCls()}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      placeholder="••••••••"
                      autoComplete="new-password"
                      value={newWaToken}
                      onChange={(e) => setNewWaToken(e.target.value)}
                    />
                  </div>
                  <div>
                    <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                      Recipient numbers (international, comma-separated)
                    </span>
                    <textarea
                      className={`${inputCls()} min-h-[72px]`}
                      style={{
                        background: "var(--dash-bg)",
                        borderColor: "var(--dash-sidebar-border)",
                        color: "var(--dash-body-text)",
                      }}
                      value={waList}
                      onChange={(e) => setWaList(e.target.value)}
                      placeholder="+9198XXXXXXXX, +9198YYYYYYYY"
                    />
                  </div>
                </div>
              </div>

              <div>
                <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                  Public dashboard URL (for snapshot links in email/WhatsApp)
                </span>
                <input
                  className={inputCls()}
                  style={{
                    background: "var(--dash-bg)",
                    borderColor: "var(--dash-sidebar-border)",
                    color: "var(--dash-body-text)",
                  }}
                  value={ns.public_dashboard_url}
                  onChange={(e) => setNs({ ...ns, public_dashboard_url: e.target.value })}
                  placeholder="https://your-domain.com"
                />
              </div>

              <div
                className="rounded-lg p-4 space-y-3"
                style={{ background: "var(--dash-surface-2)", border: "1px solid var(--dash-sidebar-border)" }}
              >
                <h3 className="text-[0.7rem] font-bold tracking-wider" style={{ color: "var(--dash-body-text)" }}>
                  Message templates
                </h3>
                <p className="text-[11px]" style={{ color: "var(--dash-meta)" }}>
                  Available placeholders: {"{alert_id} {alert_type} {confidence} {timestamp_utc} {camera_id} {camera_name} {camera_location} {notes} {snapshot_path} {snapshot_url}"}
                </p>
                <div>
                  <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                    Email subject template
                  </span>
                  <input
                    className={inputCls()}
                    style={{
                      background: "var(--dash-bg)",
                      borderColor: "var(--dash-sidebar-border)",
                      color: "var(--dash-body-text)",
                    }}
                    value={ns.email_subject_template}
                    onChange={(e) => setNs({ ...ns, email_subject_template: e.target.value })}
                  />
                </div>
                <div>
                  <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                    Email body template
                  </span>
                  <textarea
                    className={`${inputCls()} min-h-[140px]`}
                    style={{
                      background: "var(--dash-bg)",
                      borderColor: "var(--dash-sidebar-border)",
                      color: "var(--dash-body-text)",
                      fontFamily: "var(--font-space-mono)",
                    }}
                    value={ns.email_body_template}
                    onChange={(e) => setNs({ ...ns, email_body_template: e.target.value })}
                  />
                </div>
                <div>
                  <span className={labelCls()} style={{ color: "var(--dash-subtle)" }}>
                    WhatsApp body template
                  </span>
                  <textarea
                    className={`${inputCls()} min-h-[120px]`}
                    style={{
                      background: "var(--dash-bg)",
                      borderColor: "var(--dash-sidebar-border)",
                      color: "var(--dash-body-text)",
                      fontFamily: "var(--font-space-mono)",
                    }}
                    value={ns.whatsapp_body_template}
                    onChange={(e) => setNs({ ...ns, whatsapp_body_template: e.target.value })}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {!isAdmin && (
        <p className="text-xs" style={{ color: "var(--dash-meta)" }}>
          Sign in as admin to edit notification credentials.
        </p>
      )}

      <SettingsSection
        title="API SERVER"
        icon={Server}
        rows={[
          {
            key: "Backend URL",
            value: process.env.NEXT_PUBLIC_API_URL ?? "/api (Next → NEXT_PUBLIC_BACKEND_URL)",
            note: "Direct: http://127.0.0.1:8001/api",
          },
          {
            key: "WebSocket",
            value:
              process.env.NEXT_PUBLIC_WS_URL ??
              "(ws from NEXT_PUBLIC_API_URL host + /ws/alerts)",
            note: "Alerts + footfall + heatmap; set NEXT_PUBLIC_BACKEND_URL for proxy port",
          },
          { key: "Docs", value: "http://localhost:8000/api/docs", note: "Swagger UI" },
          { key: "CORS Origins", value: "http://localhost:3000" },
        ]}
      />

      <SettingsSection
        title="AI ENGINE"
        icon={Brain}
        rows={[
          { key: "Fire Model", value: "YOLO fire/smoke (.pt)", note: "YOLO_FIRE_MODEL=models/fire.pt — run scripts/download_fire_model.py" },
          { key: "Fall Detection", value: "YOLO pose (3.14) / MediaPipe (3.12)", note: "POSE_YOLO_MODEL=yolo11n-pose.pt; /cameras/{id}/fall-status" },
          { key: "Infer Every N Frames", value: "2", note: "INFER_EVERY_N_FRAMES env" },
          { key: "Fire Confidence", value: "0.45", note: "FIRE_CONF_THRESHOLD env" },
          { key: "Fall Ratio", value: "1.4", note: "FALL_RATIO_THRESHOLD env" },
          { key: "Alert Cooldown", value: "10 seconds", note: "ALERT_COOLDOWN_SECONDS env" },
        ]}
      />

      <SettingsSection
        title="AUTHENTICATION"
        icon={Shield}
        rows={[
          { key: "Algorithm", value: "HS256 JWT" },
          { key: "Token Expiry", value: "60 minutes", note: "ACCESS_TOKEN_EXPIRE_MINUTES env" },
          { key: "Password Hashing", value: "bcrypt (passlib)" },
          { key: "Roles", value: "admin, operator" },
        ]}
      />

      <SettingsSection
        title="DATABASE"
        icon={Database}
        rows={[
          { key: "Engine", value: "PostgreSQL", note: "via psycopg2-binary" },
          { key: "ORM", value: "SQLAlchemy 2.0" },
          { key: "Pool Size", value: "10 connections (max overflow 20)" },
          { key: "Snapshots", value: "backend/snapshots/", note: "SNAPSHOT_DIR env" },
        ]}
      />

      <p className="text-xs pb-4" style={{ color: "var(--dash-meta)" }}>
        Many inference tunables still live in{" "}
        <code style={{ fontFamily: "var(--font-space-mono)", color: "var(--dash-subtle)" }}>backend/.env</code> — restart
        the API after changing those. Notification SMTP/WhatsApp values above are stored in the database and apply without
        restart.
      </p>
    </div>
  );
}
