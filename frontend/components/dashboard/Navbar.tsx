"use client";

import { Wifi, WifiOff, LogOut, User, Bell, Clock, Moon, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { useAuth } from "@/hooks/useAuth";
import { useAlertStore } from "@/hooks/useAlerts";
import { TIMEZONE_OPTIONS, useTimezoneStore } from "@/stores/timezoneStore";
import { useThemeStore } from "@/stores/themeStore";

export default function Navbar() {
  const router     = useRouter();
  const { user, clearAuth } = useAuth();
  const isConnected = useAlertStore((s) => s.isConnected);
  const unread      = useAlertStore((s) => s.liveAlerts.filter((a) => a.event === "alert").length);
  const timezone    = useTimezoneStore((s) => s.timezone);
  const setTimezone = useTimezoneStore((s) => s.setTimezone);
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

  function handleLogout() {
    clearAuth();
    router.push("/login");
  }

  return (
    <nav
      className="nav-glow h-14 flex items-center justify-between px-6 shrink-0"
      style={{
        background: theme === "dark" ? "#0a0f1e" : "#ffffff",
        borderBottom: theme === "dark" ? "1px solid #1a2540" : "1px solid #dbe5f4",
      }}
    >
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div className="h-8 w-36 relative">
          <Image
            src="/logo.png"
            alt="Lumicams"
            fill
            priority
            className="object-contain object-left"
          />
        </div>
        <span
          className="text-xs px-2 py-0.5 rounded"
          style={{ background: "rgba(0,212,255,0.08)", color: "#475569", fontFamily: "var(--font-space-mono)", letterSpacing: "0.1em" }}
        >
          v1.0
        </span>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-4">
        <div
          className="flex items-center gap-1 shrink-0 text-[10px]"
          style={{ color: "#64748b" }}
          title="Alert logs & charts use this timezone (stored in this browser)"
        >
          <Clock className="w-3.5 h-3.5 shrink-0" style={{ color: "#00d4ff" }} />
          <label htmlFor="aegis-tz" className="sr-only">
            Display timezone
          </label>
          <select
            id="aegis-tz"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="max-w-[118px] sm:max-w-[140px] rounded px-1 py-0.5 sm:px-1.5 sm:py-1 font-mono cursor-pointer outline-none text-[9px] sm:text-[10px]"
            style={{
              background: theme === "dark" ? "#0d1527" : "#f8fbff",
              border: theme === "dark" ? "1px solid #1a2540" : "1px solid #cbd5e1",
              color: theme === "dark" ? "#94a3b8" : "#334155",
            }}
          >
            {TIMEZONE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded border transition-colors"
          style={{
            color: theme === "dark" ? "#94a3b8" : "#475569",
            borderColor: theme === "dark" ? "#1a2540" : "#cbd5e1",
            background: theme === "dark" ? "rgba(15,23,42,0.6)" : "#f1f5f9",
          }}
        >
          {theme === "dark" ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          {theme === "dark" ? "LIGHT" : "DARK"}
        </button>

        {/* WebSocket status */}
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "#475569" }}>
          {isConnected ? (
            <>
              <Wifi className="w-3.5 h-3.5 blink" style={{ color: "#22c55e" }} />
              <span style={{ color: "#22c55e" }}>LIVE</span>
            </>
          ) : (
            <>
              <WifiOff className="w-3.5 h-3.5" style={{ color: "#ef4444" }} />
              <span style={{ color: "#ef4444" }}>OFFLINE</span>
            </>
          )}
        </div>

        {/* Alert bell */}
        <div className="relative">
          <Bell className="w-4 h-4" style={{ color: "#475569" }} />
          {unread > 0 && (
            <span
              className="absolute -top-1.5 -right-1.5 flex items-center justify-center w-4 h-4 rounded-full text-xs font-bold"
              style={{ background: "#ff4500", color: "#fff", fontSize: "9px" }}
            >
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </div>

        {/* User info */}
        <div
          className="flex items-center gap-2 pl-4"
          style={{ borderLeft: theme === "dark" ? "1px solid #1a2540" : "1px solid #e2e8f0" }}
        >
          <div className="flex items-center justify-center w-7 h-7 rounded-full"
               style={{ background: "rgba(0,212,255,0.1)", border: "1px solid rgba(0,212,255,0.2)" }}>
            <User className="w-3.5 h-3.5" style={{ color: "#00d4ff" }} />
          </div>
          <div className="hidden sm:block">
            <p
              className="text-xs font-semibold leading-none"
              style={{ color: theme === "dark" ? "#94a3b8" : "#334155" }}
            >
              {user?.full_name ?? user?.email?.split("@")[0] ?? "User"}
            </p>
            <p
              className="text-xs leading-none mt-0.5"
              style={{
                color: theme === "dark" ? "#2a3a5c" : "#64748b",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              {user?.role}
            </p>
          </div>
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          title="Logout"
          className="flex items-center justify-center w-8 h-8 rounded transition-all hover:bg-red-950/30"
          style={{ color: "#475569" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#ef4444")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#475569")}
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </nav>
  );
}
