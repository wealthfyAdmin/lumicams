"use client";

import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title:     string;
  value:     string | number;
  icon:      LucideIcon;
  color:     "cyan" | "fire" | "fall" | "safe" | "muted";
  subtitle?: string;
  pulse?:    boolean;
  /** Optional bar fill 0–100 for mini progress indicator */
  fillPct?:  number;
}

const colorMap = {
  cyan:  { text: "#00d4ff", bg: "rgba(0,212,255,0.08)",  border: "rgba(0,212,255,0.22)",  glow: "rgba(0,212,255,0.18)",  bar: "#00d4ff" },
  fire:  { text: "#ff6b35", bg: "rgba(255,107,53,0.10)", border: "rgba(255,107,53,0.28)",  glow: "rgba(255,107,53,0.18)", bar: "#ff6b35" },
  fall:  { text: "#fbbf24", bg: "rgba(251,191,36,0.09)", border: "rgba(251,191,36,0.28)",  glow: "rgba(251,191,36,0.14)", bar: "#fbbf24" },
  safe:  { text: "#22c55e", bg: "rgba(34,197,94,0.08)",  border: "rgba(34,197,94,0.22)",   glow: "rgba(34,197,94,0.14)",  bar: "#22c55e" },
  muted: { text: "#94a3b8", bg: "rgba(71,85,105,0.07)",  border: "#1a2540",                glow: "none",                  bar: "#475569" },
};

export default function StatCard({ title, value, icon: Icon, color, subtitle, pulse, fillPct }: StatCardProps) {
  const c = colorMap[color];
  const numericVal = typeof value === "number" ? value : parseFloat(value as string);
  const hasAlert = !isNaN(numericVal) && numericVal > 0 && color !== "cyan" && color !== "muted";

  return (
    <div
      className={cn("aegis-card relative overflow-hidden flex flex-col gap-3 p-4 fade-in transition-all duration-200 hover:scale-[1.02]")}
      style={{
        borderColor: c.border,
        boxShadow: hasAlert
          ? `0 0 0 1px ${c.border}, 0 4px 24px ${c.glow}`
          : `0 0 0 1px rgba(0,212,255,0.04), 0 4px 16px rgba(0,0,0,0.35)`,
      }}
    >
      {/* Accent top stripe */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px] rounded-t"
        style={{ background: hasAlert ? `linear-gradient(90deg, transparent, ${c.text}, transparent)` : "transparent" }}
      />

      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-bold tracking-[0.14em] uppercase leading-tight" style={{ color: "var(--dash-subtle)" }}>
          {title}
        </p>
        <div
          className={cn("flex items-center justify-center w-8 h-8 rounded-md shrink-0", pulse && "pulse-ring")}
          style={{ background: c.bg, border: `1px solid ${c.border}` }}
        >
          <Icon className="w-4 h-4" style={{ color: c.text }} />
        </div>
      </div>

      {/* Value */}
      <div className="flex items-end gap-2">
        <p
          className="text-3xl font-black leading-none"
          style={{ fontFamily: "var(--font-orbitron)", color: c.text }}
        >
          {value}
        </p>
        {hasAlert && (
          <span
            className="mb-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded-full tracking-wider"
            style={{ background: c.bg, color: c.text, border: `1px solid ${c.border}` }}
          >
            ACTIVE
          </span>
        )}
      </div>

      {/* Mini progress bar */}
      {fillPct !== undefined && (
        <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${Math.min(100, Math.max(0, fillPct))}%`, background: c.bar }}
          />
        </div>
      )}

      {/* Subtitle */}
      {subtitle && (
        <p className="text-[10px] leading-snug" style={{ color: "var(--dash-meta)" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
