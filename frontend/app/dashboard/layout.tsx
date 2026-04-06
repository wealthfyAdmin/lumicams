"use client";

import { useEffect } from "react";
import { Toaster } from "react-hot-toast";
import Navbar from "@/components/dashboard/Navbar";
import Sidebar from "@/components/dashboard/Sidebar";
import LiveAlertSidebar from "@/components/dashboard/LiveAlertSidebar";
import { useAuth } from "@/hooks/useAuth";
import { useAlertsWebSocket } from "@/hooks/useAlerts";
import { useTimezoneStore } from "@/stores/timezoneStore";
import { useThemeStore } from "@/stores/themeStore";

/**
 * Dashboard layout.
 *
 * Renders the persistent Navbar, Sidebar, main content area, and the
 * Live-Alert sidebar.  Also initiates the WebSocket connection for the
 * entire dashboard lifetime.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const hydrate = useAuth((s) => s.hydrate);
  // Re-render dashboard when display timezone changes so formatTs() updates everywhere.
  useTimezoneStore((s) => s.timezone);
  const theme = useThemeStore((s) => s.theme);

  // Restore auth state from cookies on first client render
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Connect WebSocket for live alert feed
  useAlertsWebSocket();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Top nav */}
      <Navbar />

      {/* Body: sidebar + main + alert-panel */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />

        {/* Main scrollable content */}
        <main className="dashboard-main flex-1 overflow-y-auto p-6 space-y-6">
          {children}
        </main>

        {/* Live alerts right-panel */}
        <LiveAlertSidebar />
      </div>

      {/* Toast notifications */}
      <Toaster
        position="bottom-center"
        toastOptions={{
          style: {
            background: theme === "light" ? "#ffffff" : "#0d1527",
            color: theme === "light" ? "#0f172a" : "#e2e8f0",
            border: theme === "light" ? "1px solid #cbd5e1" : "1px solid #1a2540",
            fontFamily: "var(--font-rajdhani)",
            fontSize: "14px",
            borderRadius: "8px",
            boxShadow: theme === "light" ? "0 4px 20px rgba(15,23,42,0.08)" : undefined,
          },
          success: {
            iconTheme: {
              primary: "#22c55e",
              secondary: theme === "light" ? "#ffffff" : "#0d1527",
            },
          },
          error: {
            iconTheme: {
              primary: "#ef4444",
              secondary: theme === "light" ? "#ffffff" : "#0d1527",
            },
          },
        }}
      />
    </div>
  );
}
