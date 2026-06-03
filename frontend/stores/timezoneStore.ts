import { create } from "zustand";
import { persist } from "zustand/middleware";

/** IANA timezone for alert/history display (stored in localStorage). */
export const DEFAULT_TIMEZONE = "Asia/Kolkata";

export const TIMEZONE_OPTIONS: { value: string; label: string }[] = [
  { value: "Asia/Kolkata", label: "India (IST)" },
  { value: "Asia/Dubai", label: "UAE (GST)" },
  { value: "Asia/Singapore", label: "Singapore" },
  { value: "Asia/Tokyo", label: "Japan" },
  { value: "Europe/London", label: "UK" },
  { value: "UTC", label: "UTC" },
  { value: "America/New_York", label: "US Eastern" },
];

interface TimezoneState {
  timezone: string;
  setTimezone: (tz: string) => void;
}

export const useTimezoneStore = create<TimezoneState>()(
  persist(
    (set) => ({
      timezone: DEFAULT_TIMEZONE,
      setTimezone: (timezone) => set({ timezone }),
    }),
    { name: "lumicams-display-timezone" }
  )
);
