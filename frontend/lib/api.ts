/**
 * api.ts
 * ------
 * Axios client pre-configured for Aegis-Eye FastAPI backend.
 *
 * - Automatically attaches `Authorization: Bearer <token>` header.
 * - On 401 responses, clears auth and redirects to /login.
 * - Base URL is read from NEXT_PUBLIC_API_URL env variable,
 *   falling back to /api (which is proxied by Next.js rewrites).
 */

import axios from "axios";
import Cookies from "js-cookie";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

/**
 * MJPEG preview URL for `/cameras/{id}/video`. Same-origin `/api` uses the JWT cookie from axios;
 * for absolute NEXT_PUBLIC_API_URL the img request may need credentials — use same host as API or proxy.
 */
export function getCameraVideoSrc(cameraId: number, cacheBust?: number): string {
  const base = BASE_URL.replace(/\/$/, "");
  const t = cacheBust ?? Date.now();
  const token =
    typeof window !== "undefined" ? Cookies.get("aegis_token") : undefined;
  const q = new URLSearchParams({ t: String(t) });
  if (token) q.set("token", token);
  return `${base}/cameras/${cameraId}/video?${q.toString()}`;
}

// ── Request interceptor: inject JWT ──────────────────────────
api.interceptors.request.use((config) => {
  const token = Cookies.get("aegis_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor: handle 401 ─────────────────────────
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      Cookies.remove("aegis_token");
      Cookies.remove("aegis_user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// ── Auth ──────────────────────────────────────────────────────

export async function loginUser(email: string, password: string) {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  const res = await api.post<{ access_token: string; token_type: string }>(
    "/auth/login",
    form,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
  );
  return res.data;
}

export async function getMe() {
  const res = await api.get("/users/me");
  return res.data;
}

// ── Cameras ───────────────────────────────────────────────────

export async function getCameras() {
  const res = await api.get("/cameras/");
  return res.data;
}

export async function createCamera(payload: {
  name: string;
  rtsp_url: string;
  organization_id?: number | null;
  location?: string;
  person_detection_enabled?: boolean;
  crowd_roi_enabled?: boolean;
  crowd_roi_x1?: number;
  crowd_roi_y1?: number;
  crowd_roi_x2?: number;
  crowd_roi_y2?: number;
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
  footfall_enabled?: boolean;
  footfall_mode?: "line" | "zone";
  footfall_line_y?: number;
  heatmap_enabled?: boolean;
}) {
  const res = await api.post("/cameras/", payload);
  return res.data;
}

export async function updateCamera(
  id: number,
  payload: Partial<{
    name: string;
    rtsp_url: string;
    location: string;
    status: string;
    person_detection_enabled: boolean;
    crowd_roi_enabled: boolean;
    crowd_roi_x1: number;
    crowd_roi_y1: number;
    crowd_roi_x2: number;
    crowd_roi_y2: number;
    crowd_limit_enabled: boolean;
    crowd_max_people: number;
    fire_enabled: boolean;
    fire_min_confidence: number | null;
    fall_enabled: boolean;
    fall_consecutive_frames: number | null;
    face_enabled: boolean;
    face_min_similarity: number | null;
    ppe_enabled: boolean;
    ppe_items: string[];
    ppe_confidence: number | null;
    weapon_enabled: boolean;
    weapon_confidence: number | null;
    footfall_enabled: boolean;
    footfall_mode: "line" | "zone";
    footfall_line_y: number;
    heatmap_enabled: boolean;
  }>
) {
  const res = await api.patch(`/cameras/${id}`, payload);
  return res.data;
}

export async function deleteCamera(id: number) {
  await api.delete(`/cameras/${id}`);
}

export async function startProcessor(id: number) {
  const res = await api.post(`/cameras/${id}/start`);
  return res.data;
}

export async function stopProcessor(id: number) {
  const res = await api.post(`/cameras/${id}/stop`);
  return res.data;
}

export async function getProcessorStatus(id: number) {
  const res = await api.get(`/cameras/${id}/status`);
  return res.data;
}

export type CameraPpeStatus = {
  running: boolean;
  ppe_enabled: boolean;
  model_loaded: boolean;
  model_path: string;
  aux_model_loaded?: boolean;
  aux_model_path?: string;
  required_items: string[];
  confidence_threshold: number;
  model_classes: string[];
  message?: string;
};

export async function getCameraPpeStatus(id: number) {
  const res = await api.get<CameraPpeStatus>(`/cameras/${id}/ppe-status`);
  return res.data;
}

export type CameraWeaponStatus = {
  running: boolean;
  weapon_enabled: boolean;
  model_loaded: boolean;
  model_path: string;
  confidence_threshold: number;
  model_classes: string[];
  class_filter: string[] | string;
  message?: string;
};

export async function getCameraWeaponStatus(id: number) {
  const res = await api.get<CameraWeaponStatus>(`/cameras/${id}/weapon-status`);
  return res.data;
}

// ── Alerts ────────────────────────────────────────────────────

export async function getAlerts(params?: {
  skip?: number;
  limit?: number;
  camera_id?: number;
  alert_type?: string;
  acknowledged?: boolean;
}) {
  const res = await api.get("/alerts/", { params });
  return res.data;
}

export async function getAlertStats(hours = 24) {
  const res = await api.get("/alerts/stats", { params: { hours } });
  return res.data;
}

export async function acknowledgeAlert(id: number, notes?: string) {
  const res = await api.patch(`/alerts/${id}/ack`, { notes });
  return res.data;
}

export async function deleteAlert(id: number) {
  await api.delete(`/alerts/${id}`);
}

// ── Users ─────────────────────────────────────────────────────

export async function getUsers() {
  const res = await api.get("/users/");
  return res.data;
}

export async function createUser(payload: {
  email: string;
  full_name?: string;
  password: string;
  role: string;
  organization_id?: number | null;
}) {
  const res = await api.post("/users/", payload);
  return res.data;
}

export async function getOrganizations() {
  const res = await api.get("/organizations/");
  return res.data;
}

export async function createOrganization(payload: { name: string; slug?: string }) {
  const res = await api.post("/organizations/", payload);
  return res.data;
}

export async function updateOrganization(
  id: number,
  payload: { name?: string; slug?: string | null; is_active?: boolean }
) {
  const res = await api.patch(`/organizations/${id}`, payload);
  return res.data;
}

export async function deleteOrganization(id: number) {
  await api.delete(`/organizations/${id}`);
}

export async function deleteUser(id: number) {
  await api.delete(`/users/${id}`);
}

// ── Analytics ─────────────────────────────────────────────────

export async function getAnalyticsOverview(hours = 24) {
  const res = await api.get("/analytics/overview", { params: { hours } });
  return res.data;
}

export async function getCameraAnalytics(cameraId: number, hours = 72) {
  const res = await api.get(`/analytics/cameras/${cameraId}`, { params: { hours } });
  return res.data;
}

// ── Crowd: footfall & heatmap ─────────────────────────────────

export async function getFootfallSummary(hours = 168, cameraId?: number) {
  const res = await api.get("/crowd/footfall/summary", {
    params: { hours, ...(cameraId != null ? { camera_id: cameraId } : {}) },
  });
  return res.data;
}

export async function getHeatmapCamera(cameraId: number, hours = 168) {
  const res = await api.get(`/crowd/heatmap/cameras/${cameraId}`, { params: { hours } });
  return res.data;
}

// ── Face Intelligence ─────────────────────────────────────────

export async function getFaceIdentities(params?: {
  category?: "whitelist" | "blacklist" | "neutral";
  active_only?: boolean;
}) {
  const res = await api.get("/faces/identities", { params });
  return res.data;
}

export type FaceModuleStatus = {
  insightface_available: boolean;
  enroll_mode: "embedding" | "image_only";
  /** insightface | onnxruntime | none */
  face_engine?: string;
  camera_pipeline_enabled?: boolean;
  active_identities?: number;
  identities_with_embeddings?: number;
};

export async function getFaceModuleStatus() {
  const res = await api.get("/faces/status");
  return res.data as FaceModuleStatus;
}

export async function createFaceIdentity(payload: {
  name: string;
  employee_code?: string;
  category: "whitelist" | "blacklist" | "neutral";
  embeddings?: number[][];
  is_active?: boolean;
}) {
  const res = await api.post("/faces/identities", payload);
  return res.data;
}

export async function enrollFaceIdentityByImage(payload: {
  name: string;
  employee_code?: string;
  category: "whitelist" | "blacklist" | "neutral";
  image: File;
}) {
  const form = new FormData();
  form.append("name", payload.name);
  if (payload.employee_code) form.append("employee_code", payload.employee_code);
  form.append("category", payload.category);
  form.append("image", payload.image);
  const res = await api.post("/faces/identities/enroll-image", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function updateFaceIdentity(
  identityId: number,
  payload: Partial<{
    name: string;
    employee_code: string;
    category: "whitelist" | "blacklist" | "neutral";
    embeddings: number[][];
    is_active: boolean;
  }>
) {
  const res = await api.patch(`/faces/identities/${identityId}`, payload);
  return res.data;
}

export async function deleteFaceIdentity(identityId: number) {
  await api.delete(`/faces/identities/${identityId}`);
}

/** Rebuild embeddings from stored enrollment photo for one identity (admin). */
export async function extractFaceEmbeddingFromStoredPhoto(identityId: number) {
  const res = await api.post(`/faces/identities/${identityId}/extract-embedding`);
  return res.data;
}

export type RepairEmbeddingsResult = {
  repaired: { identity_id: number; name: string }[];
  failed: { identity_id: number; name: string; reason: string }[];
  repaired_count: number;
  failed_count: number;
};

/** Repair all active identities that have a photo but no embedding vectors (admin). */
export async function repairMissingFaceEmbeddings() {
  const res = await api.post("/faces/identities/repair-missing-embeddings");
  return res.data as RepairEmbeddingsResult;
}

export async function getFaceSightings(params?: {
  hours?: number;
  camera_id?: number;
  category?: "whitelist" | "blacklist" | "neutral";
  event_type?: string;
  limit?: number;
}) {
  const res = await api.get("/faces/sightings", { params });
  return res.data;
}

export async function getFaceAttendance(params?: {
  hours?: number;
  camera_id?: number;
  limit?: number;
}) {
  const res = await api.get("/faces/attendance", { params });
  return res.data;
}

// ── Notification settings (admin): SMTP + Ultramsg WhatsApp ─────────────

export type NotificationSettingsDTO = {
  smtp_enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_use_implicit_ssl: boolean;
  smtp_username: string;
  smtp_from_email: string;
  email_recipients: string[];
  default_owner_email: string;
  smtp_password_configured: boolean;
  whatsapp_enabled: boolean;
  ultramsg_instance_id: string;
  ultramsg_token_configured: boolean;
  whatsapp_recipients: string[];
  public_dashboard_url: string;
  email_subject_template: string;
  email_body_template: string;
  whatsapp_body_template: string;
  updated_at?: string | null;
};

export type NotificationSettingsUpdateDTO = Partial<{
  smtp_enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_use_implicit_ssl: boolean;
  smtp_username: string;
  smtp_password: string;
  smtp_from_email: string;
  email_recipients: string[];
  default_owner_email: string;
  whatsapp_enabled: boolean;
  ultramsg_instance_id: string;
  ultramsg_token: string;
  whatsapp_recipients: string[];
  public_dashboard_url: string;
  email_subject_template: string;
  email_body_template: string;
  whatsapp_body_template: string;
}>;

export async function getNotificationSettings(): Promise<NotificationSettingsDTO> {
  const res = await api.get("/settings/notifications");
  return res.data;
}

export async function patchNotificationSettings(
  payload: NotificationSettingsUpdateDTO
): Promise<NotificationSettingsDTO> {
  const res = await api.patch("/settings/notifications", payload);
  return res.data;
}

export async function testNotificationSettings(): Promise<{
  email: { ok: boolean; detail: string } | null;
  whatsapp:
    | { ok: boolean; detail: string }
    | Array<{ to: string; ok: boolean; detail: string }>
    | null;
}> {
  const res = await api.post("/settings/notifications/test");
  return res.data;
}
