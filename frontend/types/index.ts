// ─── Enums ────────────────────────────────────────────────────
export type Role =
  | "super_admin"
  | "org_admin"
  | "operator"
  | "admin"; // legacy — maps to org_admin after backend migration
export type CameraStatus   = "active" | "inactive" | "error";
export type AlertType      = "Fire" | "Fall" | "Crowd" | "Face" | "PPE" | "Weapon";

// ─── Entities ─────────────────────────────────────────────────
export interface User {
  id:         number;
  email:      string;
  full_name?: string;
  role:       Role;
  is_active:  boolean;
  created_at: string;
  organization_id?: number | null;
}

export interface Organization {
  id: number;
  name: string;
  slug?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Camera {
  id:         number;
  name:       string;
  rtsp_url:   string;
  location?:  string;
  status:     CameraStatus;
  user_id:    number;
  organization_id: number;
  created_at: string;
  updated_at?: string;
  /** Bounding boxes + "person" label (YOLO). */
  person_detection_enabled?: boolean;
  /** Count people whose foot point lies inside the ROI rectangle. */
  crowd_roi_enabled?: boolean;
  crowd_roi_x1?: number;
  crowd_roi_y1?: number;
  crowd_roi_x2?: number;
  crowd_roi_y2?: number;
  last_crowd_roi_count?: number;
  crowd_limit_enabled?: boolean;
  crowd_max_people?: number;
  fire_enabled?: boolean;
  fire_min_confidence?: number | null;
  fall_enabled?: boolean;
  fall_consecutive_frames?: number | null;
  face_enabled?: boolean;
  face_min_similarity?: number | null;
  ppe_enabled?: boolean;
  ppe_items?: string[];
  ppe_confidence?: number | null;
  weapon_enabled?: boolean;
  weapon_confidence?: number | null;
  /** Virtual line crossing (entry/exit). */
  footfall_enabled?: boolean;
  /** "line" = horizontal line; "zone" = count entry/exit when entering/leaving ROI box */
  footfall_mode?: "line" | "zone";
  footfall_line_y?: number;
  /** Full-frame occupancy grid (aggregated hourly). */
  heatmap_enabled?: boolean;
}

export interface Alert {
  id:             number;
  camera_id:      number;
  type:           AlertType;
  confidence?:    string;
  timestamp:      string;
  snapshot_path?: string;
  acknowledged:   boolean;
  notes?:         string;
  vlm_status?:    "pending" | "confirmed" | "rejected" | "skipped" | "error" | null;
  vlm_explanation?: string | null;
  vlm_checked_at?: string | null;
}

export interface AlertStats {
  total:            number;
  unacknowledged:   number;
  by_type:          Record<string, number>;
  since:            string;
}

// ─── WebSocket Payloads ───────────────────────────────────────
export interface AlertBroadcast {
  event:          "alert" | "pong";
  alert_id:       number;
  camera_id:      number;
  camera_name:    string;
  type:           AlertType;
  confidence?:    string;
  timestamp:      string;
  snapshot_path?: string;
  subtype?:       "Overcrowd" | "CounterFlow" | "QueueHigh" | string;
  people_count?:  number;
  max_people?:    number;
}

export interface CrowdMetricBroadcast {
  event: "crowd_metric";
  camera_id: number;
  camera_name: string;
  timestamp: string;
  /** People detected in full frame (stabilized). */
  people_count: number;
  /** People whose foot point is inside the ROI rectangle. */
  roi_count: number;
  /** Same value used for overcrowd vs max_people (frame or zone per CROWD_LIMIT_COUNT_MODE). */
  limit_count?: number;
  /** none | frame | zone */
  limit_basis?: string;
  crowd_roi_enabled?: boolean;
  /** True when ROI rectangle is used for counting (crowd ROI and/or footfall zone). */
  roi_active?: boolean;
  crowd_limit_enabled: boolean;
  max_people: number;
  overcrowded: boolean;
  entry_60s: number;
  exit_60s: number;
  net_60s: number;
  counterflow?: boolean;
}

export interface ProcessorStatus {
  camera_id: number;
  running:   boolean;
  message:   string;
}

export interface AnalyticsOverview {
  window_hours: number;
  since: string;
  summary: {
    total_cameras: number;
    active_cameras: number;
    total_alerts: number;
    unacknowledged_alerts: number;
    alert_rate_per_hour: number;
    risk_level: "low" | "medium" | "high";
  };
  by_type: Record<string, number>;
  top_cameras: Array<{
    camera_id: number;
    camera_name: string;
    alert_count: number;
  }>;
  hourly_trend: Array<{
    hour: string;
    count: number;
  }>;
  intelligent_insights: string[];
}

export interface CameraAnalytics {
  window_hours: number;
  since: string;
  camera: {
    id: number;
    name: string;
    location?: string;
    status: CameraStatus;
  };
  summary: {
    total_alerts: number;
    unacknowledged_alerts: number;
    by_type: Record<string, number>;
    dominant_model: string;
    latest_alert_at?: string | null;
  };
  model_alerts: Array<{
    model: string;
    alert_type: AlertType;
    count: number;
    active: boolean;
  }>;
  hourly_trend: Array<{
    hour: string;
    count: number;
  }>;
  recent_alerts: Array<{
    id: number;
    type: AlertType;
    confidence?: string;
    acknowledged: boolean;
    timestamp: string;
    snapshot_path?: string;
  }>;
  intelligent_recommendations: string[];
}

export interface FootfallSummary {
  window_hours: number;
  since: string;
  totals: { entry: number; exit: number; net_flow: number };
  hourly: Array<{ hour: string; entry: number; exit: number }>;
  by_day: Array<{ date: string; entry: number; exit: number }>;
  peak_hour: string | null;
  peak_hour_total_crossings: number;
  insights: string[];
}

export interface HeatmapResponse {
  camera_id: number;
  window_hours: number;
  grid_size: number;
  merged_cells: number[];
  hot_zones: Array<{
    grid_x: number;
    grid_y: number;
    weight: number;
    normalized: number;
    label: string;
  }>;
  insights: string[];
}

export type FaceCategory = "whitelist" | "blacklist" | "neutral";

export interface FaceIdentity {
  id: number;
  organization_id?: number | null;
  name: string;
  employee_code?: string | null;
  face_image_path?: string | null;
  category: FaceCategory;
  embeddings: number[][];
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface FaceSighting {
  id: number;
  camera_id: number;
  identity_id?: number | null;
  identity_name?: string | null;
  category: FaceCategory;
  confidence?: number | null;
  event_type: string;
  timestamp: string;
  snapshot_path?: string | null;
  notes?: string | null;
}
