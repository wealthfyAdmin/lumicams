"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { Eye, EyeOff, Loader2, AlertTriangle } from "lucide-react";
import { loginUser, getMe } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const router   = useRouter();
  const setAuth  = useAuth((s) => s.setAuth);
  const hydrate  = useAuth((s) => s.hydrate);

  const [email,    setEmail]    = useState("admin@lumicams.com");
  const [password, setPassword] = useState("");
  const [showPwd,  setShowPwd]  = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  useEffect(() => { hydrate(); }, [hydrate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { access_token } = await loginUser(email, password);
      // Temporarily set cookie so getMe() request can auth
      document.cookie = `lumicams_token=${access_token}; path=/; max-age=3600; SameSite=Strict`;
      const user = await getMe();
      setAuth(access_token, user);
      router.push("/dashboard");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      // FastAPI returns a string on auth errors but an array of objects
      // on 422 validation errors — safely convert either to a display string.
      const msg =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join(", ")
          : "Login failed. Check your credentials.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Ambient background orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full opacity-5"
           style={{ background: "radial-gradient(circle, #00d4ff, transparent 70%)" }} />
      <div className="absolute bottom-1/4 right-1/4 w-64 h-64 rounded-full opacity-5"
           style={{ background: "radial-gradient(circle, #ff4500, transparent 70%)" }} />

      <div className="w-full max-w-md px-6 fade-in">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="mx-auto relative w-64 h-20 mb-4">
            <Image src="/logo.png" alt="Lumicams" fill priority className="object-contain" />
          </div>
          
          <p className="text-sm mt-1" style={{ color: "#475569", letterSpacing: "0.15em" }}>
            AI SURVEILLANCE PLATFORM
          </p>
        </div>

        {/* Card */}
        <div className="lumicams-card p-8">
          <h2 className="text-md font-semibold mb-6" style={{ color: "#94a3b8", letterSpacing: "0.08em" }}>
            OPERATOR LOGIN
          </h2>

          {error && (
            <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded text-sm"
                 style={{ background: "rgba(255,69,0,0.1)", border: "1px solid rgba(255,69,0,0.3)", color: "#ff6b35" }}>
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email */}
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-widest"
                     style={{ color: "#475569" }}>
                EMAIL ADDRESS
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="operator@lumicams.com"
                className="w-full px-4 py-2.5 rounded-md text-sm outline-none transition-all"
                style={{
                  background: "#080d1a",
                  border: "1px solid #1a2540",
                  color: "#e2e8f0",
                  fontFamily: "var(--font-space-mono)",
                }}
                onFocus={(e) => (e.target.style.borderColor = "rgba(0,212,255,0.5)")}
                onBlur={(e)  => (e.target.style.borderColor = "#1a2540")}
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold mb-1.5 tracking-widest"
                     style={{ color: "#475569" }}>
                PASSWORD
              </label>
              <div className="relative">
                <input
                  type={showPwd ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  placeholder="••••••••"
                  className="w-full px-4 py-2.5 pr-10 rounded-md text-sm outline-none transition-all"
                  style={{
                    background: "#080d1a",
                    border: "1px solid #1a2540",
                    color: "#e2e8f0",
                    fontFamily: "var(--font-space-mono)",
                  }}
                  onFocus={(e) => (e.target.style.borderColor = "rgba(0,212,255,0.5)")}
                  onBlur={(e)  => (e.target.style.borderColor = "#1a2540")}
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 opacity-40 hover:opacity-70 transition-opacity"
                >
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-md font-bold tracking-widest text-sm transition-all flex items-center justify-center gap-2"
              style={{
                background: loading ? "rgba(0,212,255,0.05)" : "rgba(0,212,255,0.12)",
                border: "1px solid rgba(0,212,255,0.4)",
                color: "#00d4ff",
                boxShadow: loading ? "none" : "0 0 20px rgba(0,212,255,0.15)",
                fontFamily: "var(--font-orbitron)",
              }}
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> AUTHENTICATING…</>
              ) : (
                "ACCESS SYSTEM"
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-xs mt-6" style={{ color: "#2a3a5c" }}>
          LUMICAMS v1.0 · SECURED WITH AES-256 · ALL ACCESS LOGGED
        </p>
      </div>
    </div>
  );
}