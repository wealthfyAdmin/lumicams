"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Camera,
  BellRing,
  Users,
  Settings,
  Activity,
  Footprints,
  ScanFace,
  HardHat,
  Shield,
  Building2,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard",          label: "OVERVIEW",  icon: LayoutDashboard },
  { href: "/dashboard/cameras",  label: "CAMERAS",   icon: Camera },
  { href: "/dashboard/crowd",    label: "CROWD",     icon: Footprints },
  { href: "/dashboard/faces",    label: "FACES",     icon: ScanFace },
  { href: "/dashboard/ppe",      label: "PPE",       icon: HardHat },
  { href: "/dashboard/weapon",   label: "WEAPON",    icon: Shield },
  { href: "/dashboard/alerts",   label: "ALERTS",    icon: BellRing },
  { href: "/dashboard/activity", label: "ACTIVITY",  icon: Activity },
];

const adminItems = [
  { href: "/dashboard/users",      label: "USERS",      icon: Users },
  { href: "/dashboard/settings",   label: "SETTINGS",   icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const isAdmin = useAuth((s) => s.isAdmin);
  const isPlatform = useAuth((s) => s.user?.role === "super_admin");

  return (
    <aside className="dashboard-sidebar w-56 shrink-0 flex flex-col py-6 px-3 gap-1">
      <p
        className="text-xs px-3 mb-2 font-semibold tracking-widest"
        style={{ color: "var(--dash-nav-label)" }}
      >
        NAVIGATION
      </p>

      {navItems.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-widest transition-all",
              active ? "text-[#00d4ff]" : "text-[var(--dash-nav-inactive)] hover:text-[var(--dash-nav-hover)]"
            )}
            style={
              active
                ? {
                    background: "rgba(0,212,255,0.07)",
                    border: "1px solid rgba(0,212,255,0.15)",
                    boxShadow: "inset 0 0 12px rgba(0,212,255,0.05)",
                  }
                : {
                    border: "1px solid transparent",
                  }
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
            {active && (
              <span className="ml-auto w-1.5 h-1.5 rounded-full blink" style={{ background: "#00d4ff" }} />
            )}
          </Link>
        );
      })}

      {isPlatform && (
        <>
          <div className="my-3 mx-3 border-t" style={{ borderColor: "var(--dash-sidebar-border)" }} />
          <p
            className="text-xs px-3 mb-2 font-semibold tracking-widest"
            style={{ color: "var(--dash-nav-label)" }}
          >
            PLATFORM
          </p>
          <Link
            href="/dashboard/organizations"
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-widest transition-all",
              pathname.startsWith("/dashboard/organizations")
                ? "text-[#00d4ff]"
                : "text-[var(--dash-nav-inactive)] hover:text-[var(--dash-nav-hover)]"
            )}
            style={
              pathname.startsWith("/dashboard/organizations")
                ? { background: "rgba(0,212,255,0.07)", border: "1px solid rgba(0,212,255,0.15)" }
                : { border: "1px solid transparent" }
            }
          >
            <Building2 className="w-4 h-4 shrink-0" />
            ORGANIZATIONS
          </Link>
        </>
      )}

      {isAdmin && (
        <>
          <div className="my-3 mx-3 border-t" style={{ borderColor: "var(--dash-sidebar-border)" }} />
          <p
            className="text-xs px-3 mb-2 font-semibold tracking-widest"
            style={{ color: "var(--dash-nav-label)" }}
          >
            ADMIN
          </p>
          {adminItems.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-widest transition-all",
                  active ? "text-[#00d4ff]" : "text-[var(--dash-nav-inactive)] hover:text-[var(--dash-nav-hover)]"
                )}
                style={
                  active
                    ? { background: "rgba(0,212,255,0.07)", border: "1px solid rgba(0,212,255,0.15)" }
                    : { border: "1px solid transparent" }
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </>
      )}

      {/* Bottom status */}
      <div className="mt-auto mx-3 pt-4 border-t" style={{ borderColor: "var(--dash-sidebar-border)" }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: "var(--dash-meta)" }}>
          <span className="status-dot active" />
          SYSTEM NOMINAL
        </div>
      </div>
    </aside>
  );
}
