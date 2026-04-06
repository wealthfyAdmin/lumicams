import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import { DEFAULT_TIMEZONE, useTimezoneStore } from "@/stores/timezoneStore";

/** Build absolute URL for alert / Re-ID snapshot paths served by the API or static mount. */
export function snapshotPathToUrl(snapshotPath?: string | null): string {
  if (!snapshotPath) return "";
  if (/^https?:\/\//i.test(snapshotPath)) return snapshotPath;
  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/$/, "");
  const originNoApi = apiBase.replace(/\/api$/, "");
  const normalized = snapshotPath.replace(/\\/g, "/");
  if (normalized.startsWith("/")) {
    if (normalized.startsWith("/snapshots")) return `${originNoApi}${normalized}`;
    return `${apiBase}${normalized}`;
  }
  // DB stores paths relative to SNAPSHOT_DIR (e.g. reid/cam1_t1.jpg) or with snapshots/ prefix.
  const underSnapshots = normalized.startsWith("snapshots/")
    ? normalized
    : `snapshots/${normalized}`;
  return `${originNoApi}/${underSnapshots}`;
}

/**
 * Merges Tailwind CSS class names with conflict resolution.
 * Combines clsx (conditional logic) with tailwind-merge (deduplication).
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function currentDisplayTimeZone(): string {
  if (typeof window === "undefined") {
    return DEFAULT_TIMEZONE;
  }
  try {
    return useTimezoneStore.getState().timezone || DEFAULT_TIMEZONE;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

/**
 * Backend often sends naive UTC timestamps like "2026-03-27T14:05:12.123456".
 * Browsers interpret naive ISO as local time, which shifts displayed alerts.
 * Normalize by forcing UTC when tz offset/Z is missing.
 */
function parseApiDate(iso: string): Date {
  const raw = (iso || "").trim();
  const hasTz = /(?:Z|[+-]\d{2}:\d{2})$/.test(raw);
  const normalized = hasTz ? raw : `${raw}Z`;
  return new Date(normalized);
}

/**
 * Format ISO timestamp for operators (respects dashboard timezone selector).
 * Default storage uses Asia/Kolkata for India operations.
 */
export function formatTs(iso: string): string {
  const tz = currentDisplayTimeZone();
  try {
    return parseApiDate(iso).toLocaleString("en-IN", {
      timeZone: tz,
      month: "short",
      day: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
    });
  } catch {
    return parseApiDate(iso).toLocaleString("en-IN", { hour12: true });
  }
}

/** Return a relative time string like "2m ago" */
export function timeAgo(iso: string): string {
  const diff = (Date.now() - parseApiDate(iso).getTime()) / 1000;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}
