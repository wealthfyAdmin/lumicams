import { create } from "zustand";

export interface FootfallLiveEvent {
  camera_id: number;
  camera_name: string;
  direction: "entry" | "exit";
  crossed_at: string;
  track_id?: number;
}

export interface CrowdMetricLiveEvent {
  camera_id: number;
  camera_name: string;
  timestamp: string;
  people_count: number;
  roi_count: number;
  limit_count: number;
  /** none | frame | zone */
  limit_basis: string;
  crowd_roi_enabled: boolean;
  roi_active: boolean;
  crowd_limit_enabled: boolean;
  max_people: number;
  overcrowded: boolean;
  entry_60s: number;
  exit_60s:  number;
  net_60s: number;
  counterflow: boolean;
}

interface RealtimeState {
  /** Incremented on footfall or heatmap flush — use to refetch analytics APIs. */
  dataRevision: number;
  recentFootfall: FootfallLiveEvent[];
  latestCrowdMetrics: CrowdMetricLiveEvent[];
  pushFootfall: (e: FootfallLiveEvent) => void;
  upsertCrowdMetric: (e: CrowdMetricLiveEvent) => void;
  bumpData: () => void;
}

export const useRealtimeStore = create<RealtimeState>((set) => ({
  dataRevision: 0,
  recentFootfall: [],
  latestCrowdMetrics: [],
  pushFootfall: (e) =>
    set((s) => ({
      dataRevision: s.dataRevision + 1,
      recentFootfall: [e, ...s.recentFootfall].slice(0, 40),
    })),
  /** Live tiles read `latestCrowdMetrics` directly; do not bump `dataRevision` here or the
   * overview dashboard would refetch /api/cameras + analytics on every WS tick (~1/s per cam). */
  upsertCrowdMetric: (e) =>
    set((s) => {
      const rest = s.latestCrowdMetrics.filter((m) => m.camera_id !== e.camera_id);
      return {
        latestCrowdMetrics: [e, ...rest].slice(0, 20),
      };
    }),
  bumpData: () => set((s) => ({ dataRevision: s.dataRevision + 1 })),
}));
