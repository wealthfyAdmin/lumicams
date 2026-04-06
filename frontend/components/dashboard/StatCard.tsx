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
}

const colorMap = {
  cyan: { text: "#00d4ff", bg: "rgba(0,212,255,0.08)", border: "rgba(0,212,255,0.2)",  glow: "rgba(0,212,255,0.15)"  },
  fire: { text: "#ff6b35", bg: "rgba(255,69,0,0.08)",  border: "rgba(255,69,0,0.25)",  glow: "rgba(255,69,0,0.15)"   },
  fall: { text: "#fbbf24", bg: "rgba(245,158,11,0.08)",border: "rgba(245,158,11,0.25)",glow: "rgba(245,158,11,0.12)" },
  safe: { text: "#22c55e", bg: "rgba(34,197,94,0.08)", border: "rgba(34,197,94,0.2)",  glow: "rgba(34,197,94,0.12)"  },
  muted:{ text: "#94a3b8", bg: "rgba(71,85,105,0.06)", border: "#1a2540",              glow: "none"                   },
};

export default function StatCard({ title, value, icon: Icon, color, subtitle, pulse }: StatCardProps) {
  const c = colorMap[color];

  return (
    <div
      className="aegis-card p-5 flex items-center gap-4 fade-in"
      style={{ borderColor: c.border, boxShadow: `0 0 20px ${c.glow}` }}
    >
      <div
        className={cn("flex items-center justify-center w-12 h-12 rounded-lg shrink-0", pulse && "pulse-ring")}
        style={{ background: c.bg, border: `1px solid ${c.border}` }}
      >
        <Icon className="w-5 h-5" style={{ color: c.text }} />
      </div>

      <div className="min-w-0">
        <p className="text-xs font-semibold tracking-widest truncate" style={{ color: "#475569" }}>
          {title}
        </p>
        <p className="text-2xl font-bold mt-0.5 leading-none" style={{ fontFamily: "var(--font-orbitron)", color: c.text }}>
          {value}
        </p>
        {subtitle && (
          <p className="text-xs mt-1" style={{ color: "#2a3a5c" }}>{subtitle}</p>
        )}
      </div>
    </div>
  );
}
