import asyncio
import json
import logging
import math
import os
import sys
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy dependencies
# ---------------------------------------------------------------------------

try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    logger.warning("ultralytics not installed – falling back to HSV fire heuristic.")

_MP_AVAILABLE = False
_MP_BACKEND: Optional[str] = None 
_mp_pose = None
_PoseLandmarker = None
_PoseLandmarkerOptions = None
_Image = None
_ImageFormat = None
_VisionTaskRunningMode = None
_BaseOptions = None

try:
    from mediapipe.tasks.python.core import base_options as _mp_base_options
    from mediapipe.tasks.python.vision import pose_landmarker as _mp_pose_landmarker
    from mediapipe.tasks.python.vision.core import image as _mp_image_module
    from mediapipe.tasks.python.vision.core import vision_task_running_mode as _mp_vision_running_mode

    _PoseLandmarker = _mp_pose_landmarker.PoseLandmarker
    _PoseLandmarkerOptions = _mp_pose_landmarker.PoseLandmarkerOptions
    _Image = _mp_image_module.Image
    _ImageFormat = _mp_image_module.ImageFormat
    _VisionTaskRunningMode = _mp_vision_running_mode.VisionTaskRunningMode
    _BaseOptions = _mp_base_options.BaseOptions
    _MP_AVAILABLE = True
    _MP_BACKEND = "tasks"
except ImportError:
    try:
        import mediapipe as mp
        if hasattr(mp, "solutions") and hasattr(mp.solutions, "pose"):
            _mp_pose = mp.solutions.pose
            _MP_AVAILABLE = True
            _MP_BACKEND = "legacy"
    except ImportError:
        logger.info(
            "MediaPipe not installed (normal on Python 3.13+); fall uses YOLO pose when ultralytics is available."
        )


def _yolo_class_id_by_name(yolo_model, name: str) -> Optional[int]:
    """Resolve YOLO class index by label (case-insensitive)."""
    target = name.strip().lower()
    names = getattr(yolo_model, "names", None)
    if isinstance(names, dict):
        for i, n in names.items():
            if str(n).strip().lower() == target:
                return int(i)
    elif isinstance(names, list):
        for i, n in enumerate(names):
            if str(n).strip().lower() == target:
                return int(i)
    return None


# ---------------------------------------------------------------------------
# Constants / Tunables (Optimized for Shibuya Crossing)
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "snapshots"))
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

YOLO_MODEL_PATH = os.getenv("YOLO_FIRE_MODEL", "yolo11n.pt")
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_POSE_MODEL = _BACKEND_ROOT / "models" / "pose_landmarker_lite.task"
POSE_LANDMARKER_MODEL_PATH = Path(os.getenv("MEDIAPIPE_POSE_MODEL", str(_DEFAULT_POSE_MODEL)))
POSE_LANDMARKER_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
# YOLO pose (Ultralytics) — works on Python 3.13+ / 3.14 where MediaPipe has no wheel.
POSE_YOLO_MODEL: str = os.getenv("POSE_YOLO_MODEL", "models/yolo11n-pose.pt")
POSE_YOLO_CONF: float = float(os.getenv("POSE_YOLO_CONF", "0.5"))
POSE_YOLO_IMGSZ: int = int(os.getenv("POSE_YOLO_IMGSZ", "640"))
# auto | mediapipe | yolo — on 3.13+ default is yolo when MediaPipe is unavailable.
POSE_BACKEND_PREF: str = os.getenv("POSE_BACKEND", "auto").strip().lower()
_USE_YOLO_POSE_FIRST: bool = POSE_BACKEND_PREF == "yolo" or (
    POSE_BACKEND_PREF == "auto" and sys.version_info >= (3, 13)
)
# Skeleton joint indices per backend (normalized x,y + visibility).
_POSE_MP_JOINTS: Dict[str, int] = {"nose": 0, "l_sh": 11, "r_sh": 12, "l_hp": 23, "r_hp": 24}
_POSE_YOLO_JOINTS: Dict[str, int] = {"nose": 0, "l_sh": 5, "r_sh": 6, "l_hp": 11, "r_hp": 12}

# --- Footfall / heatmap (YOLO COCO person class 0) ---
# yolov8m.pt = better recall in crowds; yolov8n.pt = faster CPU
FOOTFALL_YOLO_MODEL: str = os.getenv("FOOTFALL_YOLO_MODEL", "yolo11n.pt")
PERSON_DETECT_MODEL: str = os.getenv("PERSON_DETECT_MODEL", FOOTFALL_YOLO_MODEL)
PEOPLE_TRACKER_BACKEND: str = os.getenv("PEOPLE_TRACKER_BACKEND", "bytetrack").strip().lower()
FOOTFALL_PERSON_CONF: float = float(os.getenv("FOOTFALL_PERSON_CONF", "0.38"))
FOOTFALL_INFER_IMGSZ: int = int(os.getenv("FOOTFALL_INFER_IMGSZ", "640"))
INFER_EVERY_N_FRAMES: int = int(os.getenv("INFER_EVERY_N_FRAMES", "2"))
PERSON_MIN_BOX_AREA_NORM: float = float(os.getenv("PERSON_MIN_BOX_AREA_NORM", "0.00115"))
PERSON_MIN_BOX_HEIGHT_NORM: float = float(os.getenv("PERSON_MIN_BOX_HEIGHT_NORM", "0.052"))
PERSON_MAX_BOX_ASPECT: float = float(os.getenv("PERSON_MAX_BOX_ASPECT", "2.2"))
# Min width/height of bbox (COCO person). Helps drop spurious vertical slivers; 0 = off.
PERSON_MIN_W_OVER_H: float = float(os.getenv("PERSON_MIN_W_OVER_H", "0.2"))
# Stricter per-box score for counting (reduces chair / clutter false positives vs FOOTFALL_PERSON_CONF).
PERSON_COUNT_CONF_MIN: float = float(os.getenv("PERSON_COUNT_CONF_MIN", "0.42"))
# Merge overlapping person boxes (same person detected twice); lower = stricter merge.
PERSON_DEDUPE_IOU: float = float(os.getenv("PERSON_DEDUPE_IOU", "0.45"))
FOOTFALL_YOLO_MAX_DET: int = max(1, int(os.getenv("FOOTFALL_YOLO_MAX_DET", "50")))
# Extra floor on per-detection score after global conf filter (reduces weak boxes).
PERSON_MIN_PER_BOX_CONF: float = float(os.getenv("PERSON_MIN_PER_BOX_CONF", "0.0"))

FIRE_CONF_THRESHOLD: float = float(os.getenv("FIRE_CONF_THRESHOLD", "0.35"))
# Ultralytics pre-filter; keep low so smoke-only models (often ~0.1–0.2 conf) still return boxes.
FIRE_YOLO_PREDICT_CONF: float = float(os.getenv("FIRE_YOLO_PREDICT_CONF", "0.10"))
FIRE_YOLO_IMGSZ: int = int(os.getenv("FIRE_YOLO_IMGSZ", "640"))
FIRE_USE_HSV_WITH_YOLO: bool = os.getenv("FIRE_USE_HSV_WITH_YOLO", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
# HSV-only path: reject logos/UI (bright white + blue) — warm orange/red must dominate the mask.
FIRE_HSV_MIN_WARM_FRAC: float = float(os.getenv("FIRE_HSV_MIN_WARM_FRAC", "0.38"))
FIRE_HSV_MAX_BLUE_FRAC: float = float(os.getenv("FIRE_HSV_MAX_BLUE_FRAC", "0.22"))
FIRE_HSV_MAX_CONF: float = float(os.getenv("FIRE_HSV_MAX_CONF", "0.55"))
FIRE_MIN_AREA_NORM: float = float(os.getenv("FIRE_MIN_AREA_NORM", "0.0010"))
FIRE_CONSECUTIVE_FRAMES: int = max(1, int(os.getenv("FIRE_CONSECUTIVE_FRAMES", "2")))
FIRE_ALLOWED_CLASS_NAMES: tuple[str, ...] = tuple(
    x.strip().lower()
    for x in os.getenv("FIRE_ALLOWED_CLASS_NAMES", "fire,smoke,flame").split(",")
    if x.strip()
)
FIRE_MODEL_CANDIDATES: tuple[str, ...] = tuple(
    x.strip()
    for x in os.getenv(
        "FIRE_MODEL_CANDIDATES",
        "models/fire.pt,models/fire_yolov8n.pt,models/fire_smoke.pt,"
        "fire.pt,models/best_fire.pt",
    ).split(",")
    if x.strip()
)
# Generic COCO checkpoints must not be used for fire (no fire/smoke classes).
FIRE_SKIP_GENERIC_YOLO_NAMES: tuple[str, ...] = tuple(
    x.strip().lower()
    for x in os.getenv(
        "FIRE_SKIP_GENERIC_YOLO_NAMES",
        "yolo11n.pt,yolo11s.pt,yolov5su.pt,yolov8n.pt,yolov8s.pt,yolov8m.pt",
    ).split(",")
    if x.strip()
)
PPE_MODEL_PATH: str = os.getenv("YOLO_PPE_MODEL", "ppe.pt")
PPE_AUX_MODEL_PATH: str = os.getenv("YOLO_PPE_AUX_MODEL", "").strip()
PPE_CONF_THRESHOLD: float = float(os.getenv("PPE_CONF_THRESHOLD", "0.45"))
PPE_MODEL_CANDIDATES: tuple[str, ...] = tuple(
    x.strip()
    for x in os.getenv(
        "PPE_MODEL_CANDIDATES",
        "ppe.pt,ppe_best.pt,best.pt,models/ppe.pt,models/ppe_best.pt",
    ).split(",")
    if x.strip()
)
PPE_DEFAULT_ITEMS: tuple[str, ...] = tuple(
    x.strip().lower()
    for x in os.getenv("PPE_DEFAULT_ITEMS", "helmet,vest").split(",")
    if x.strip()
)
WEAPON_MODEL_PATH: str = os.getenv("YOLO_WEAPON_MODEL", "").strip()
WEAPON_CONF_THRESHOLD: float = float(os.getenv("WEAPON_CONF_THRESHOLD", "0.45"))
WEAPON_ALERT_MIN_INTERVAL_SECONDS: int = max(
    int(os.getenv("ALERT_COOLDOWN_SECONDS", "10")),
    int(os.getenv("WEAPON_ALERT_MIN_INTERVAL_SECONDS", "45")),
)
WEAPON_ALLOWED_CLASS_NAMES: tuple[str, ...] = tuple(
    x.strip().lower()
    for x in os.getenv(
        "WEAPON_ALLOWED_CLASS_NAMES",
        "gun,pistol,rifle,revolver,knife,weapon,blade,firearm,sword,machete,shotgun",
    ).split(",")
    if x.strip()
)
WEAPON_MATCH_ALL_CLASSES: bool = os.getenv("WEAPON_MATCH_ALL_CLASSES", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
# When no weapon .pt is found, use these COCO class names on PERSON_DETECT_MODEL (no firearm class in COCO).
WEAPON_COCO_KNIFE_FALLBACK: bool = os.getenv("WEAPON_COCO_KNIFE_FALLBACK", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
WEAPON_COCO_FALLBACK_CLASS_NAMES: tuple[str, ...] = tuple(
    x.strip().lower()
    for x in os.getenv("WEAPON_COCO_FALLBACK_CLASS_NAMES", "knife,baseball bat").split(",")
    if x.strip()
) or ("knife",)
WEAPON_MODEL_CANDIDATES: tuple[str, ...] = tuple(
    x.strip()
    for x in os.getenv(
        "WEAPON_MODEL_CANDIDATES",
        "weapon.pt,models/weapon.pt,best_weapon.pt,models/yolov8_weapon.pt,models/yolo11_weapon.pt",
    ).split(",")
    if x.strip()
)
# Weapon alert JPEG: crop to detection union when it is small in frame (clearer than a distant full scene).
WEAPON_SNAPSHOT_CROP: bool = os.getenv("WEAPON_SNAPSHOT_CROP", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
# Many public .pt files only have "pistol"+"knife"; elongated boxes are often rifles/long guns — refine label for display.
WEAPON_GEOM_REFINE: bool = os.getenv("WEAPON_GEOM_REFINE", "true").strip().lower() in ("1", "true", "yes")
WEAPON_RIFLE_MIN_ASPECT: float = float(os.getenv("WEAPON_RIFLE_MIN_ASPECT", "2.05"))


def _refine_weapon_display_label(raw_lbl: str, x1: int, y1: int, x2: int, y2: int) -> str:
    """
    If the model only predicts coarse classes (e.g. pistol), use bbox shape: long thin boxes → "rifle".
    Does not change labels that already name rifle/shotgun/knife/baseball bat etc.
    """
    if not WEAPON_GEOM_REFINE:
        return raw_lbl
    s = str(raw_lbl).strip().lower()
    if any(
        tok in s
        for tok in (
            "rifle",
            "shotgun",
            "sniper",
            "carbine",
            "long gun",
            "long_gun",
            "knife",
            "bat",
            "blade",
            "machete",
            "bow",
        )
    ):
        return raw_lbl
    if s not in ("pistol", "gun", "firearm", "weapon", "handgun"):
        return raw_lbl
    w = max(1, abs(int(x2) - int(x1)))
    h = max(1, abs(int(y2) - int(y1)))
    ar = max(w, h) / float(min(w, h))
    if ar >= WEAPON_RIFLE_MIN_ASPECT:
        return "rifle"
    return raw_lbl


# Legacy width/height of full pose bbox; used only when torso is ambiguous (not for upright rejection).
FALL_RATIO_THRESHOLD: float = float(os.getenv("FALL_RATIO_THRESHOLD", "1.65"))
POSE_DETECTION_CONF: float = float(os.getenv("POSE_DETECTION_CONF", "0.5"))
# Torso: shoulder-mid to hip-mid must be mostly vertical (|dy|/norm) to count as upright/seated.
FALL_MIN_UPRIGHT_VERTICALITY: float = float(os.getenv("FALL_MIN_UPRIGHT_VERTICALITY", "0.42"))
# If shoulder–hip vertical separation (norm coords) is at least this, hips are clearly below shoulders → not a fall.
FALL_MIN_SHOULDER_HIP_DY_NORM: float = float(os.getenv("FALL_MIN_SHOULDER_HIP_DY_NORM", "0.055"))
# If |dy| is tiny (e.g. overhead camera), use head-vs-hips: head above hips → not a fall.
FALL_AMBIGUOUS_DY_NORM: float = float(os.getenv("FALL_AMBIGUOUS_DY_NORM", "0.048"))
# Require this many consecutive “fall candidate” frames before alerting (reduces flicker / false positives).
FALL_CONSECUTIVE_FRAMES: int = max(1, int(os.getenv("FALL_CONSECUTIVE_FRAMES", "5")))
# Draw shoulder–hip line + label on MJPEG preview when pose is available.
FALL_DRAW_POSE_OVERLAY: bool = os.getenv("FALL_DRAW_POSE_OVERLAY", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
ALERT_COOLDOWN_SECONDS: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", "10"))
# Fire/smoke: one incident per camera per window (YOLO can re-trigger every few frames; VLM runs after save).
FIRE_ALERT_MIN_INTERVAL_SECONDS: int = max(
    int(os.getenv("ALERT_COOLDOWN_SECONDS", "10")),
    int(os.getenv("FIRE_ALERT_MIN_INTERVAL_SECONDS", "180")),
)
STREAM_RECONNECT_DELAY: int = 5
HEATMAP_GRID_SIZE: int = int(os.getenv("HEATMAP_GRID_SIZE", "16"))
# MJPEG preview (same frame as AI overlays — must match inference, not a second VideoCapture)
PREVIEW_MAX_WIDTH: int = int(os.getenv("PREVIEW_MAX_WIDTH", "960"))
PREVIEW_JPEG_QUALITY: int = int(os.getenv("PREVIEW_JPEG_QUALITY", "78"))
FOOTFALL_MAX_MATCH_DIST: float = float(os.getenv("FOOTFALL_MAX_MATCH_DIST", "0.12"))
FOOTFALL_TRACK_MAX_MISSED: int = int(os.getenv("FOOTFALL_TRACK_MAX_MISSED", "18"))
HEATMAP_FLUSH_SECONDS: int = int(os.getenv("HEATMAP_FLUSH_SECONDS", "60"))
# Min seconds between counting another crossing for the same track (reduces jitter / bounce)
FOOTFALL_PER_TRACK_COOLDOWN: float = float(os.getenv("FOOTFALL_PER_TRACK_COOLDOWN", "0.4"))
SETTINGS_REFRESH_INFER_FRAMES: int = int(os.getenv("SETTINGS_REFRESH_INFER_FRAMES", "45"))
CROWD_LIMIT_ALERT_COOLDOWN_SECONDS: int = int(os.getenv("CROWD_LIMIT_ALERT_COOLDOWN_SECONDS", "45"))
# After an overcrowd alert, skip duplicate DB rows for same camera (seconds), e.g. processor restart.
CROWD_OVERCROWD_ALERT_MIN_INTERVAL_SECONDS: int = max(
    int(os.getenv("CROWD_LIMIT_ALERT_COOLDOWN_SECONDS", "45")),
    int(os.getenv("CROWD_OVERCROWD_ALERT_MIN_INTERVAL_SECONDS", "180")),
)
FLOW_WINDOW_SECONDS: int = int(os.getenv("FLOW_WINDOW_SECONDS", "60"))
CROWD_METRIC_EMIT_SECONDS: float = float(os.getenv("CROWD_METRIC_EMIT_SECONDS", "1.0"))
CROWD_OVER_LIMIT_CONSEC_FRAMES: int = max(1, int(os.getenv("CROWD_OVER_LIMIT_CONSEC_FRAMES", "4")))
PRESENCE_TRACK_MAX_DIST: float = float(os.getenv("PRESENCE_TRACK_MAX_DIST", "0.08"))
PRESENCE_TRACK_MAX_MISSED: int = int(os.getenv("PRESENCE_TRACK_MAX_MISSED", "6"))
CROWD_LIMIT_COUNT_MODE: str = os.getenv("CROWD_LIMIT_COUNT_MODE", "auto").strip().lower()
CROWD_EVENT_COOLDOWN_SECONDS: int = int(os.getenv("CROWD_EVENT_COOLDOWN_SECONDS", "30"))
COUNTERFLOW_MIN_EVENTS_60S: int = int(os.getenv("COUNTERFLOW_MIN_EVENTS_60S", "6"))
COUNTERFLOW_MAX_DIR_RATIO: float = float(os.getenv("COUNTERFLOW_MAX_DIR_RATIO", "1.7"))
QUEUE_HIGH_ROI_THRESHOLD: int = int(os.getenv("QUEUE_HIGH_ROI_THRESHOLD", "12"))
QUEUE_HIGH_CONSEC_FRAMES: int = max(1, int(os.getenv("QUEUE_HIGH_CONSEC_FRAMES", "6")))
# Person point for footfall line + heatmap: "foot" = bottom-center of bbox (typical for counting lines);
# "center" = bbox center (legacy).
FOOTFALL_TRACK_POINT: str = os.getenv("FOOTFALL_TRACK_POINT", "foot").strip().lower()
FACE_RECOGNITION_ENABLED: bool = os.getenv("FACE_RECOGNITION_ENABLED", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.42"))
FACE_COOLDOWN_SECONDS: int = int(os.getenv("FACE_COOLDOWN_SECONDS", "45"))
FACE_ATTENDANCE_COOLDOWN_SECONDS: int = int(os.getenv("FACE_ATTENDANCE_COOLDOWN_SECONDS", "120"))
FACE_INFER_EVERY_N_FRAMES: int = max(1, int(os.getenv("FACE_INFER_EVERY_N_FRAMES", "5")))
_face_min_sim_raw = os.getenv("FACE_MIN_SIMILARITY", "").strip()
FACE_MIN_SIMILARITY: Optional[float] = float(_face_min_sim_raw) if _face_min_sim_raw else None
FACE_IDENTITY_REFRESH_SECONDS: float = max(1.0, float(os.getenv("FACE_IDENTITY_REFRESH_SECONDS", "5")))
PERSON_REID_SAMPLE_EVERY_FRAMES: int = max(1, int(os.getenv("PERSON_REID_SAMPLE_EVERY_FRAMES", "45")))
PERSON_REID_TRACK_COOLDOWN: float = float(os.getenv("PERSON_REID_TRACK_COOLDOWN", "8.0"))


def _norm_face_category(cat: object) -> str:
    """Normalize DB / enum category to lowercase token (whitelist | blacklist | neutral)."""
    if hasattr(cat, "value"):
        cat = getattr(cat, "value")
    s = str(cat)
    return s.rsplit(".", 1)[-1].lower()


def _normalize_ppe_item_token(item: object) -> Optional[str]:
    s = str(item).strip().lower()
    if not s:
        return None
    aliases = {
        "hardhat": "helmet",
        "safetyvest": "vest",
        "safety_vest": "vest",
        "glove": "gloves",
        "shoe": "boots",
        "shoes": "boots",
        "safetyshoe": "boots",
        "safetyshoes": "boots",
    }
    return aliases.get(s, s)


def _fire_class_ids_from_names(names: object) -> set[int]:
    """Return YOLO class indices whose labels match FIRE_ALLOWED_CLASS_NAMES."""
    ids: set[int] = set()
    if isinstance(names, dict):
        for i, n in names.items():
            label = str(n).strip().lower()
            if any(label == target or target in label for target in FIRE_ALLOWED_CLASS_NAMES):
                ids.add(int(i))
    elif isinstance(names, list):
        for i, n in enumerate(names):
            label = str(n).strip().lower()
            if any(label == target or target in label for target in FIRE_ALLOWED_CLASS_NAMES):
                ids.add(int(i))
    return ids


def _is_generic_coco_fire_path(path: Path) -> bool:
    return path.name.lower() in FIRE_SKIP_GENERIC_YOLO_NAMES


def _iter_fire_model_candidate_paths() -> List[Path]:
    """Ordered fire-weight paths; skips generic COCO filenames unless explicitly configured."""
    candidates: List[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        if not p.name.lower().endswith(".pt"):
            return
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            return
        seen.add(key)
        candidates.append(p)

    env_primary = Path(YOLO_MODEL_PATH)
    add(env_primary)
    if not env_primary.is_absolute():
        add(_BACKEND_ROOT / env_primary)

    for raw in FIRE_MODEL_CANDIDATES:
        cp = Path(raw)
        add(cp)
        if not cp.is_absolute():
            add(_BACKEND_ROOT / cp)

    for pat in ("*fire*.pt", "*smoke*.pt"):
        for p in sorted((_BACKEND_ROOT / "models").glob(pat)):
            add(p)

    # Legacy fallbacks only when primary env path is not a generic COCO name
    if not _is_generic_coco_fire_path(env_primary):
        for legacy in (
            _BACKEND_ROOT / "yolo11n.pt",
            _BACKEND_ROOT / "yolo11s.pt",
            _BACKEND_ROOT / "yolov8n.pt",
            _BACKEND_ROOT / "yolov8s.pt",
        ):
            add(legacy)

    # Drop generic COCO weights unless user explicitly set YOLO_FIRE_MODEL to that file
    explicit_generic = _is_generic_coco_fire_path(env_primary)
    out: List[Path] = []
    for p in candidates:
        if _is_generic_coco_fire_path(p) and not (
            explicit_generic and p.name.lower() == env_primary.name.lower()
        ):
            continue
        out.append(p)
    return out


def _try_load_fire_yolo(path: Path) -> Tuple[Optional[object], Optional[set[int]]]:
    """Load YOLO weights if they contain fire/smoke class labels."""
    if not _YOLO_AVAILABLE or not path.is_file():
        return None, None
    try:
        model = YOLO(str(path))
        class_ids = _fire_class_ids_from_names(getattr(model, "names", None))
        if not class_ids:
            logger.warning(
                "Skipping %s for fire: no classes in %s",
                path,
                FIRE_ALLOWED_CLASS_NAMES,
            )
            return None, None
        return model, class_ids
    except Exception as exc:
        logger.warning("Fire YOLO load failed for %s: %s", path, exc)
        return None, None


def _resolve_fire_yolo() -> Tuple[Optional[object], Optional[set[int]], Optional[str]]:
    """First valid fire/smoke YOLO checkpoint, else HSV-only."""
    checked: List[str] = []
    for path in _iter_fire_model_candidate_paths():
        checked.append(str(path))
        if not path.is_file():
            continue
        model, class_ids = _try_load_fire_yolo(path)
        if model is not None and class_ids:
            logger.info(
                "Fire YOLO ready: %s (class ids=%s, labels=%s)",
                path,
                class_ids,
                FIRE_ALLOWED_CLASS_NAMES,
            )
            return model, class_ids, str(path.resolve())
    logger.warning(
        "No fire/smoke YOLO weights found. Checked: %s. "
        "Run: python scripts/download_fire_model.py — using HSV color fallback.",
        ", ".join(checked[:12]) + ("..." if len(checked) > 12 else ""),
    )
    return None, None, None


class _NormLandmark:
    """Normalized landmark (x,y in 0–1) compatible with fall detection + overlay."""

    __slots__ = ("x", "y", "visibility")

    def __init__(self, x: float, y: float, visibility: float = 1.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.visibility = float(visibility)


def _resolve_pose_yolo_path() -> Optional[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            return
        seen.add(key)
        candidates.append(p)

    primary = Path(POSE_YOLO_MODEL)
    add(primary)
    if not primary.is_absolute():
        add(_BACKEND_ROOT / primary)
    for name in ("yolo11n-pose.pt", "yolov8n-pose.pt", "yolo11s-pose.pt"):
        add(_BACKEND_ROOT / "models" / name)
        add(_BACKEND_ROOT / name)
    return next((p for p in candidates if p.is_file()), candidates[0] if candidates else None)


def _iter_pose_yolo_load_paths() -> List[str]:
    """Paths to pass to YOLO(); missing files trigger Ultralytics auto-download."""
    p = _resolve_pose_yolo_path()
    if p is None:
        return [POSE_YOLO_MODEL]
    if p.is_file():
        return [str(p.resolve())]
    return [str(p), POSE_YOLO_MODEL]


def _ensure_pose_landmarker_model() -> Optional[Path]:
    path = POSE_LANDMARKER_MODEL_PATH.resolve()
    if path.is_file(): return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        logger.info("Downloading pose model...")
        urllib.request.urlretrieve(POSE_LANDMARKER_MODEL_URL, str(path))
    except Exception: return None
    return path if path.is_file() else None

def _crosses_horizontal_line(py: float, ny: float, ly: float) -> bool:
    """True if segment (py→ny) straddles horizontal line y=ly (handles skipped frames)."""
    eps = 1e-5
    a, b = py - ly, ny - ly
    if abs(a) < eps and abs(b) < eps:
        return False
    return a * b < 0


def _iso_utc(dt: datetime) -> str:
    """Return ISO-8601 UTC with explicit Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now_iso() -> str:
    return _iso_utc(datetime.now(timezone.utc))


def _iou_xyxy(
    a: Tuple[float, float, float, float],
    b: Tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / (area_a + area_b - inter + 1e-9)


def _dedupe_person_detections(
    items: List[Tuple[Tuple[float, float, float, float], float, Tuple[float, float]]],
    iou_thresh: float,
) -> List[Tuple[Tuple[float, float, float, float], float, Tuple[float, float]]]:
    """Greedy NMS on person boxes (reduces double-counts when YOLO fires twice on one body)."""
    if len(items) <= 1:
        return items
    work = sorted(items, key=lambda x: -x[1])
    keep: List[Tuple[Tuple[float, float, float, float], float, Tuple[float, float]]] = []
    while work:
        cur = work.pop(0)
        keep.append(cur)
        ba = cur[0]
        work = [it for it in work if _iou_xyxy(ba, it[0]) < iou_thresh]
    return keep


class SimpleCentroidTracker:
    def __init__(self, max_dist: float, max_missed: int) -> None:
        self.max_dist = max_dist
        self.max_missed = max_missed
        self._next_id = 1
        self._state: Dict[int, Dict] = {}

    def update(self, dets: List[Tuple[float, float]], line_y: float) -> List[Tuple[int, str]]:
        """Detect line straddle between previous and current centroid (entry = downward in image)."""
        events: List[Tuple[int, str]] = []
        ly = float(max(0.01, min(0.99, line_y)))

        if not dets:
            for tid in list(self._state.keys()):
                self._state[tid]["missed"] += 1
                if self._state[tid]["missed"] > self.max_missed:
                    del self._state[tid]
            return events

        prev = {tid: (self._state[tid]["x"], self._state[tid]["y"]) for tid in self._state}
        pairs: List[Tuple[float, int, int]] = []
        for j, (nx, ny) in enumerate(dets):
            for tid, (px, py) in prev.items():
                d = math.hypot(nx - px, ny - py)
                if d <= self.max_dist:
                    pairs.append((d, tid, j))
        pairs.sort(key=lambda x: x[0])

        match_t: Dict[int, int] = {}
        match_d: Dict[int, int] = {}
        for _d, tid, j in pairs:
            if tid in match_t or j in match_d:
                continue
            match_t[tid] = j
            match_d[j] = tid

        for tid, j in match_t.items():
            nx, ny = dets[j]
            px, py = prev[tid]
            if _crosses_horizontal_line(py, ny, ly):
                if ny > py:
                    events.append((tid, "entry"))
                else:
                    events.append((tid, "exit"))
            self._state[tid] = {"x": nx, "y": ny, "missed": 0}

        prev_tids = set(prev.keys())
        for tid in prev_tids:
            if tid not in match_t and tid in self._state:
                self._state[tid]["missed"] += 1
                if self._state[tid]["missed"] > self.max_missed:
                    del self._state[tid]

        for j, (nx, ny) in enumerate(dets):
            if j not in match_d:
                tid = self._next_id
                self._next_id += 1
                self._state[tid] = {"x": nx, "y": ny, "missed": 0}

        return events


class ZoneFootfallTracker:
    """
    Same centroid association as SimpleCentroidTracker, but counts:
    - entry: foot point transitions outside ROI → inside
    - exit:  inside → outside
    """

    def __init__(self, max_dist: float, max_missed: int) -> None:
        self.max_dist = max_dist
        self.max_missed = max_missed
        self._next_id = 1
        self._state: Dict[int, Dict] = {}

    def update(
        self,
        dets: List[Tuple[float, float]],
        roi_bounds: Tuple[float, float, float, float],
    ) -> List[Tuple[int, str]]:
        rx1, rx2, ry1, ry2 = roi_bounds
        events: List[Tuple[int, str]] = []

        def inside(nx: float, ny: float) -> bool:
            return rx1 <= nx <= rx2 and ry1 <= ny <= ry2

        if not dets:
            for tid in list(self._state.keys()):
                self._state[tid]["missed"] += 1
                if self._state[tid]["missed"] > self.max_missed:
                    del self._state[tid]
            return events

        prev = {tid: (self._state[tid]["x"], self._state[tid]["y"]) for tid in self._state}
        pairs: List[Tuple[float, int, int]] = []
        for j, (nx, ny) in enumerate(dets):
            for tid, (px, py) in prev.items():
                d = math.hypot(nx - px, ny - py)
                if d <= self.max_dist:
                    pairs.append((d, tid, j))
        pairs.sort(key=lambda x: x[0])

        match_t: Dict[int, int] = {}
        match_d: Dict[int, int] = {}
        for _d, tid, j in pairs:
            if tid in match_t or j in match_d:
                continue
            match_t[tid] = j
            match_d[j] = tid

        for tid, j in match_t.items():
            nx, ny = dets[j]
            was_in = bool(self._state[tid].get("was_inside", False))
            now_in = inside(nx, ny)
            if not was_in and now_in:
                events.append((tid, "entry"))
            elif was_in and not now_in:
                events.append((tid, "exit"))
            self._state[tid] = {"x": nx, "y": ny, "missed": 0, "was_inside": now_in}

        prev_tids = set(prev.keys())
        for tid in prev_tids:
            if tid not in match_t and tid in self._state:
                self._state[tid]["missed"] += 1
                if self._state[tid]["missed"] > self.max_missed:
                    del self._state[tid]

        for j, (nx, ny) in enumerate(dets):
            if j not in match_d:
                tid = self._next_id
                self._next_id += 1
                now_in = inside(nx, ny)
                if now_in:
                    events.append((tid, "entry"))
                self._state[tid] = {"x": nx, "y": ny, "missed": 0, "was_inside": now_in}

        return events


class PresenceTracker:
    """Lightweight tracker to stabilize occupancy counts against one-frame false detections."""

    def __init__(self, max_dist: float, max_missed: int) -> None:
        self.max_dist = max_dist
        self.max_missed = max_missed
        self._next_id = 1
        self._state: Dict[int, Dict[str, float]] = {}

    def update(self, dets: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if not dets:
            for tid in list(self._state.keys()):
                self._state[tid]["missed"] += 1
                if self._state[tid]["missed"] > self.max_missed:
                    del self._state[tid]
            return [
                (float(st["x"]), float(st["y"]))
                for st in self._state.values()
                if st.get("missed", 0) <= self.max_missed
            ]

        prev = {tid: (self._state[tid]["x"], self._state[tid]["y"]) for tid in self._state}
        pairs: List[Tuple[float, int, int]] = []
        for j, (nx, ny) in enumerate(dets):
            for tid, (px, py) in prev.items():
                d = math.hypot(nx - px, ny - py)
                if d <= self.max_dist:
                    pairs.append((d, tid, j))
        pairs.sort(key=lambda x: x[0])

        match_t: Dict[int, int] = {}
        match_d: Dict[int, int] = {}
        for _d, tid, j in pairs:
            if tid in match_t or j in match_d:
                continue
            match_t[tid] = j
            match_d[j] = tid

        for tid, j in match_t.items():
            nx, ny = dets[j]
            self._state[tid] = {"x": float(nx), "y": float(ny), "missed": 0}

        for tid in list(prev.keys()):
            if tid not in match_t and tid in self._state:
                self._state[tid]["missed"] += 1
                if self._state[tid]["missed"] > self.max_missed:
                    del self._state[tid]

        for j, (nx, ny) in enumerate(dets):
            if j not in match_d:
                tid = self._next_id
                self._next_id += 1
                self._state[tid] = {"x": float(nx), "y": float(ny), "missed": 0}

        return [
            (float(st["x"]), float(st["y"]))
            for st in self._state.values()
            if st.get("missed", 0) <= self.max_missed
        ]


class VideoProcessor:
    def __init__(self, camera_id, rtsp_url, camera_name, db_factory, ws_manager, loop):
        self.camera_id, self.rtsp_url, self.camera_name = camera_id, rtsp_url, camera_name
        self._db_factory, self._ws_manager, self._loop = db_factory, ws_manager, loop
        self._stop_event, self._thread = threading.Event(), None
        self._last_alert, self._pose_ts_ms = {}, 0
        self._infer_frame_counter = 0
        self._last_footfall_cross_ts: Dict[int, float] = {}
        self._fire_consecutive = 0
        self._fall_consecutive = 0
        self._fire_enabled = True
        self._fall_enabled = True
        self._face_enabled = True
        self._ppe_enabled = False
        self._fire_conf_threshold = FIRE_CONF_THRESHOLD
        self._fall_consecutive_required = FALL_CONSECUTIVE_FRAMES
        self._face_min_similarity_override: Optional[float] = FACE_MIN_SIMILARITY
        self._ppe_conf_threshold = PPE_CONF_THRESHOLD
        self._ppe_items_required: set[str] = {
            t for t in (_normalize_ppe_item_token(x) for x in PPE_DEFAULT_ITEMS) if t
        }
        self._ppe_label_warn_ts = 0.0
        self._ppe_overlay_boxes: List[Tuple[Tuple[int, int, int, int], Tuple[int, int, int], str]] = []
        self._weapon_enabled = False
        self._weapon_disabled_hint_logged = False
        self._weapon_conf_threshold = WEAPON_CONF_THRESHOLD
        self._weapon_overlay_boxes: List[Tuple[Tuple[int, int, int, int], str, float]] = []
        self._fire_overlay_boxes: List[Tuple[Tuple[int, int, int, int], float]] = []
        self._last_pose_landmarks = None
        self._last_crowd_limit_alert_ts = 0.0
        self._last_crowd_metric_ws_ts = 0.0
        self._flow_recent: deque[Tuple[float, str]] = deque()
        self._crowd_over_limit_consecutive = 0
        # One overcrowd alert per "incident": active while count stays above max; clears when count <= max.
        self._overcrowd_incident_active = False
        self._crowd_event_last_ts: Dict[str, float] = {}
        self._queue_high_consecutive = 0
        self._track_backend = PEOPLE_TRACKER_BACKEND if PEOPLE_TRACKER_BACKEND in ("bytetrack", "centroid") else "centroid"
        self._bt_prev_points: Dict[int, Tuple[float, float]] = {}
        self._bt_last_seen: Dict[int, float] = {}

        # Fire model (must contain fire/smoke classes — generic COCO .pt is skipped)
        self._fire_model = None
        self._fire_class_ids: Optional[set[int]] = None
        self._fire_model_resolved_path: Optional[str] = None
        self._fire_backend = "hsv"
        if _YOLO_AVAILABLE:
            fm, fids, fpath = _resolve_fire_yolo()
            if fm is not None and fids:
                self._fire_model = fm
                self._fire_class_ids = fids
                self._fire_model_resolved_path = fpath
                self._fire_backend = "yolo"
                raw_names = getattr(fm, "names", None)
                labels = (
                    [str(raw_names[k]).lower() for k in raw_names]
                    if isinstance(raw_names, dict)
                    else [str(x).lower() for x in raw_names]
                    if isinstance(raw_names, list)
                    else []
                )
                if labels and all("smoke" in x for x in labels) and not any("fire" in x for x in labels):
                    if self._fire_conf_threshold > 0.2:
                        logger.warning(
                            "Fire model is smoke-only (%s) but FIRE_CONF_THRESHOLD=%.2f is high; "
                            "detections are often 0.10–0.20. Set FIRE_CONF_THRESHOLD=0.12 in .env.",
                            labels,
                            self._fire_conf_threshold,
                        )
        else:
            logger.warning("YOLO not available; fire detection will use HSV fallback only")

        self._ppe_model = None
        self._ppe_model_resolved_path: Optional[str] = None
        self._ppe_names: dict[int, str] = {}
        self._ppe_aux_model = None
        self._ppe_aux_model_resolved_path: Optional[str] = None
        self._ppe_aux_names: dict[int, str] = {}
        if _YOLO_AVAILABLE:
            try:
                ppe_candidates: List[Path] = []
                # 1) explicit env path
                env_p = Path(PPE_MODEL_PATH)
                ppe_candidates.append(env_p)
                if not env_p.is_absolute():
                    ppe_candidates.append(_BACKEND_ROOT / env_p)
                # 2) candidate list from env / defaults
                for raw in PPE_MODEL_CANDIDATES:
                    cp = Path(raw)
                    ppe_candidates.append(cp)
                    if not cp.is_absolute():
                        ppe_candidates.append(_BACKEND_ROOT / cp)
                # 3) auto-discover likely PPE weights in backend root
                for pat in ("*ppe*.pt", "*helmet*.pt", "*safety*.pt"):
                    ppe_candidates.extend((_BACKEND_ROOT).glob(pat))
                    ppe_candidates.extend((_BACKEND_ROOT / "models").glob(pat))

                # de-duplicate while preserving order
                uniq: List[Path] = []
                seen: set[str] = set()
                for p in ppe_candidates:
                    k = str(p.resolve()) if p.exists() else str(p)
                    if k in seen:
                        continue
                    seen.add(k)
                    uniq.append(p)

                ppe_model_path = next((p for p in uniq if p.exists()), None)
                if ppe_model_path is None:
                    raise FileNotFoundError(
                        f"PPE model file not found. Checked: {', '.join(str(p) for p in uniq[:16])}"
                    )

                self._ppe_model = YOLO(str(ppe_model_path))
                self._ppe_model_resolved_path = str(ppe_model_path)
                names = getattr(self._ppe_model, "names", None)
                if isinstance(names, dict):
                    self._ppe_names = {int(i): str(n).strip().lower() for i, n in names.items()}
                elif isinstance(names, list):
                    self._ppe_names = {int(i): str(n).strip().lower() for i, n in enumerate(names)}
                logger.info("PPE model ready: %s", self._ppe_model_resolved_path)
            except Exception as exc:
                logger.warning("PPE model not loaded (%s). PPE module disabled until model is available.", exc)
            if PPE_AUX_MODEL_PATH:
                try:
                    aux_p = Path(PPE_AUX_MODEL_PATH)
                    if not aux_p.is_absolute():
                        aux_p = _BACKEND_ROOT / aux_p
                    if not aux_p.exists():
                        raise FileNotFoundError(str(aux_p))
                    self._ppe_aux_model = YOLO(str(aux_p))
                    self._ppe_aux_model_resolved_path = str(aux_p)
                    aux_names = getattr(self._ppe_aux_model, "names", None)
                    if isinstance(aux_names, dict):
                        self._ppe_aux_names = {int(i): str(n).strip().lower() for i, n in aux_names.items()}
                    elif isinstance(aux_names, list):
                        self._ppe_aux_names = {int(i): str(n).strip().lower() for i, n in enumerate(aux_names)}
                    logger.info("PPE aux model ready: %s", self._ppe_aux_model_resolved_path)
                except Exception as exc:
                    logger.warning("PPE aux model not loaded (%s).", exc)

        self._weapon_model = None
        self._weapon_model_resolved_path: Optional[str] = None
        self._weapon_names: dict[int, str] = {}
        self._weapon_class_ids: Optional[set[int]] = None
        self._weapon_use_coco_knife = False
        self._weapon_coco_ids: set[int] = set()
        self._weapon_coco_names: dict[int, str] = {}
        if _YOLO_AVAILABLE:
            try:
                wc_candidates: List[Path] = []
                if WEAPON_MODEL_PATH:
                    wp = Path(WEAPON_MODEL_PATH)
                    wc_candidates.append(wp)
                    if not wp.is_absolute():
                        wc_candidates.append(_BACKEND_ROOT / wp)
                for raw in WEAPON_MODEL_CANDIDATES:
                    cp = Path(raw)
                    wc_candidates.append(cp)
                    if not cp.is_absolute():
                        wc_candidates.append(_BACKEND_ROOT / cp)
                for pat in ("*weapon*.pt", "*gun*.pt", "*knife*.pt"):
                    wc_candidates.extend((_BACKEND_ROOT / "models").glob(pat))
                uniq_w: List[Path] = []
                seen_w: set[str] = set()
                for p in wc_candidates:
                    k = str(p.resolve()) if p.exists() else str(p)
                    if k in seen_w:
                        continue
                    seen_w.add(k)
                    uniq_w.append(p)
                wpath = next((p for p in uniq_w if p.exists()), None)
                if wpath is None:
                    logger.info(
                        "Weapon model not found (optional). Set YOLO_WEAPON_MODEL or add weights under models/."
                    )
                else:
                    self._weapon_model = YOLO(str(wpath))
                    self._weapon_model_resolved_path = str(wpath)
                    wnames = getattr(self._weapon_model, "names", None)
                    if isinstance(wnames, dict):
                        self._weapon_names = {int(i): str(n).strip().lower() for i, n in wnames.items()}
                    elif isinstance(wnames, list):
                        self._weapon_names = {int(i): str(n).strip().lower() for i, n in enumerate(wnames)}
                    wids: set[int] = set()
                    if WEAPON_MATCH_ALL_CLASSES:
                        wids = set(self._weapon_names.keys())
                    else:
                        for wi, nm in self._weapon_names.items():
                            if any(tok in nm for tok in WEAPON_ALLOWED_CLASS_NAMES):
                                wids.add(int(wi))
                    self._weapon_class_ids = wids
                    if not wids and not WEAPON_MATCH_ALL_CLASSES:
                        logger.warning(
                            "Weapon model loaded but no classes match WEAPON_ALLOWED_CLASS_NAMES; "
                            "set WEAPON_MATCH_ALL_CLASSES=true for single-purpose models or adjust env."
                        )
                        self._weapon_class_ids = set()
                    logger.info("Weapon model ready: %s (matched class ids: %s)", wpath, self._weapon_class_ids)
            except Exception as exc:
                logger.warning("Weapon model not loaded (%s).", exc)

        # Person model (footfall + heatmap) — must not crash pipeline if weights missing
        self._person_model = None
        self._person_class_id: Optional[int] = None
        if _YOLO_AVAILABLE:
            try:
                self._person_model = YOLO(PERSON_DETECT_MODEL)
                logger.info("Person model ready: %s (tracker=%s)", PERSON_DETECT_MODEL, self._track_backend)
                self._person_class_id = _yolo_class_id_by_name(self._person_model, "person")
                if self._person_class_id is None:
                    logger.info(
                        "Person model loaded but no class named 'person' was found; fall fallback may be unavailable."
                    )
            except Exception as exc:
                logger.warning(
                    "Person model not loaded (%s). Set PERSON_DETECT_MODEL / FOOTFALL_YOLO_MODEL.",
                    exc,
                )

        if (
            _YOLO_AVAILABLE
            and WEAPON_COCO_KNIFE_FALLBACK
            and self._weapon_model is None
            and self._person_model is not None
        ):
            for raw_name in WEAPON_COCO_FALLBACK_CLASS_NAMES:
                kid = _yolo_class_id_by_name(self._person_model, raw_name)
                if kid is None:
                    logger.debug("Weapon COCO fallback: no class named %r on %s", raw_name, PERSON_DETECT_MODEL)
                    continue
                self._weapon_coco_ids.add(int(kid))
                nm = getattr(self._person_model, "names", None)
                if isinstance(nm, dict):
                    self._weapon_coco_names[int(kid)] = str(nm.get(kid, raw_name)).strip().lower()
                elif isinstance(nm, list) and int(kid) < len(nm):
                    self._weapon_coco_names[int(kid)] = str(nm[int(kid)]).strip().lower()
                else:
                    self._weapon_coco_names[int(kid)] = raw_name
            if self._weapon_coco_ids:
                self._weapon_use_coco_knife = True
                logger.info(
                    "Weapon: no dedicated weights; COCO fallback classes %s via %s (ids=%s). "
                    "COCO has no gun/pistol class—add a trained YOLO_WEAPON_MODEL for firearms. "
                    "Enable 'Weapon' on the camera or you will not get weapon alerts.",
                    list(WEAPON_COCO_FALLBACK_CLASS_NAMES),
                    PERSON_DETECT_MODEL,
                    sorted(self._weapon_coco_ids),
                )

        self._face_app = None
        if FACE_RECOGNITION_ENABLED:
            try:
                from app.face_ort import get_shared_face_app

                self._face_app = get_shared_face_app()
                if self._face_app is not None:
                    eng = getattr(self._face_app, "_aegis_engine", "unknown")
                    logger.info("Face recognition backend ready (%s).", eng)
                else:
                    logger.warning(
                        "FACE_RECOGNITION_ENABLED but face backend failed to init "
                        "(pip install onnxruntime; first run downloads ~100MB face models)."
                    )
            except Exception as exc:
                logger.warning("Face recognition init failed: %s", exc)

        self._pose = None
        self._pose_legacy = None
        self._pose_yolo = None
        self._pose_yolo_resolved_path: Optional[str] = None
        self._pose_backend: Optional[str] = None
        self._pose_joints: Dict[str, int] = dict(_POSE_MP_JOINTS)

        def _init_yolo_pose() -> bool:
            if not _YOLO_AVAILABLE:
                return False
            for load_path in _iter_pose_yolo_load_paths():
                try:
                    self._pose_yolo = YOLO(load_path)
                    self._pose_yolo_resolved_path = load_path
                    self._pose_backend = "yolo_pose"
                    self._pose_joints = dict(_POSE_YOLO_JOINTS)
                    logger.info(
                        "Fall pose backend ready (YOLO pose, Python %s): %s",
                        sys.version.split()[0],
                        load_path,
                    )
                    return True
                except Exception as exc:
                    logger.warning("YOLO pose load failed for %s: %s", load_path, exc)
            return False

        if _USE_YOLO_POSE_FIRST:
            if not _init_yolo_pose():
                logger.warning("YOLO pose unavailable; will try MediaPipe if installed.")
        elif POSE_BACKEND_PREF == "yolo":
            _init_yolo_pose()

        if self._pose_yolo is None and POSE_BACKEND_PREF != "yolo" and _MP_BACKEND == "tasks":
            m_path = _ensure_pose_landmarker_model()
            if m_path:
                try:
                    opts = _PoseLandmarkerOptions(
                        base_options=_BaseOptions(model_asset_path=str(m_path)),
                        running_mode=_VisionTaskRunningMode.VIDEO,
                        min_pose_detection_confidence=POSE_DETECTION_CONF,
                    )
                    self._pose = _PoseLandmarker.create_from_options(opts)
                    self._pose_backend = "mediapipe_tasks"
                    self._pose_joints = dict(_POSE_MP_JOINTS)
                    logger.info("Fall pose backend ready (MediaPipe tasks): %s", m_path)
                except Exception as exc:
                    logger.error("Pose landmarker failed: %s", exc)
        if (
            self._pose_yolo is None
            and self._pose is None
            and POSE_BACKEND_PREF != "yolo"
            and _MP_AVAILABLE
            and _mp_pose is not None
        ):
            try:
                self._pose_legacy = _mp_pose.Pose(
                    static_image_mode=False,
                    model_complexity=0,
                    min_detection_confidence=POSE_DETECTION_CONF,
                )
                self._pose_backend = "mediapipe_legacy"
                self._pose_joints = dict(_POSE_MP_JOINTS)
                logger.info("Fall pose backend ready (MediaPipe legacy solutions.pose)")
            except Exception as exc:
                logger.warning("MediaPipe legacy pose init failed: %s", exc)

        if self._pose_yolo is None and self._pose is None and self._pose_legacy is None:
            if not _init_yolo_pose():
                logger.warning(
                    "Fall detection: no pose backend (install ultralytics; "
                    "POSE_YOLO_MODEL=models/yolo11n-pose.pt). Using person-bbox fallback."
                )

        self._footfall_enabled = True
        self._heatmap_enabled = True
        self._footfall_line_y = 0.5
        self._person_detection_enabled = True
        self._crowd_roi_enabled = False
        self._crowd_limit_enabled = False
        self._crowd_max_people = 10
        self._roi_x1, self._roi_y1, self._roi_x2, self._roi_y2 = 0.22, 0.28, 0.78, 0.72
        self._last_roi_db_ts = 0.0
        self._last_roi_ws_ts = 0.0

        self._footfall_tracker = SimpleCentroidTracker(FOOTFALL_MAX_MATCH_DIST, FOOTFALL_TRACK_MAX_MISSED)
        self._zone_footfall_tracker = ZoneFootfallTracker(FOOTFALL_MAX_MATCH_DIST, FOOTFALL_TRACK_MAX_MISSED)
        self._presence_tracker = PresenceTracker(PRESENCE_TRACK_MAX_DIST, PRESENCE_TRACK_MAX_MISSED)
        self._face_identities: List[dict] = []
        self._face_last_refresh_ts = 0.0
        self._face_seen_cooldown: Dict[str, float] = {}
        self._face_no_identity_log_ts = 0.0
        self._footfall_mode = "line"
        self._heatmap_cells = np.zeros((HEATMAP_GRID_SIZE, HEATMAP_GRID_SIZE), dtype=np.int64)
        self._last_heatmap_flush = time.time()
        self._heatmap_hour_bucket: Optional[datetime] = None

        self._preview_lock = threading.Lock()
        self._preview_jpeg: Optional[bytes] = None
        self._organization_id: Optional[int] = None
        self._reid_track_last_ts: Dict[int, float] = {}

        self._refresh_camera_analytics_settings()

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        try:
            self._flush_heatmap_buffer()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def is_running(self): return bool(self._thread and self._thread.is_alive())

    def get_preview_jpeg(self) -> Optional[bytes]:
        """Latest annotated frame for /cameras/{id}/video (thread-safe)."""
        with self._preview_lock:
            return self._preview_jpeg

    def _publish_preview(self, frame: np.ndarray) -> None:
        """Encode current BGR frame for MJPEG (downscale for bandwidth)."""
        if frame is None or frame.size == 0:
            return
        self._draw_fall_pose_overlay(frame)
        try:
            f = frame
            h, w = f.shape[:2]
            if w > PREVIEW_MAX_WIDTH:
                scale = PREVIEW_MAX_WIDTH / float(w)
                f = cv2.resize(
                    f,
                    (PREVIEW_MAX_WIDTH, max(1, int(h * scale))),
                    interpolation=cv2.INTER_AREA,
                )
            ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG_QUALITY])
            if not ok:
                return
            with self._preview_lock:
                self._preview_jpeg = buf.tobytes()
        except Exception as exc:
            logger.debug("Preview JPEG: %s", exc)

    def _broadcast_ws(self, payload: dict) -> None:
        if self._organization_id is not None:
            payload = {**payload, "organization_id": self._organization_id}
        try:
            self._ws_manager.broadcast_from_thread(payload, self._loop)
        except Exception as exc:
            logger.debug("WS broadcast failed: %s", exc)

    def _draw_heatmap_grid_overlay(self, frame: np.ndarray, h: int, w: int) -> None:
        """Faint alignment grid for heatmap cells (matches HEATMAP_GRID_SIZE)."""
        gs = HEATMAP_GRID_SIZE
        col = (60, 45, 35)
        for i in range(1, gs):
            x = int(i / gs * w)
            cv2.line(frame, (x, 0), (x, h), col, 1, lineType=cv2.LINE_AA)
            y = int(i / gs * h)
            cv2.line(frame, (0, y), (w, y), col, 1, lineType=cv2.LINE_AA)

    def _refresh_camera_analytics_settings(self) -> None:
        from app.models import Camera

        db = self._db_factory()
        try:
            cam = db.query(Camera).filter(Camera.id == self.camera_id).first()
            if cam:
                self._person_detection_enabled = bool(getattr(cam, "person_detection_enabled", True))
                self._crowd_roi_enabled = bool(getattr(cam, "crowd_roi_enabled", False))
                self._crowd_limit_enabled = bool(getattr(cam, "crowd_limit_enabled", False))
                max_people = getattr(cam, "crowd_max_people", 10)
                try:
                    self._crowd_max_people = max(1, int(max_people))
                except Exception:
                    self._crowd_max_people = 10
                if getattr(cam, "crowd_roi_x1", None) is not None:
                    self._roi_x1 = float(max(0.0, min(1.0, float(cam.crowd_roi_x1))))
                if getattr(cam, "crowd_roi_y1", None) is not None:
                    self._roi_y1 = float(max(0.0, min(1.0, float(cam.crowd_roi_y1))))
                if getattr(cam, "crowd_roi_x2", None) is not None:
                    self._roi_x2 = float(max(0.0, min(1.0, float(cam.crowd_roi_x2))))
                if getattr(cam, "crowd_roi_y2", None) is not None:
                    self._roi_y2 = float(max(0.0, min(1.0, float(cam.crowd_roi_y2))))
                self._footfall_enabled = bool(getattr(cam, "footfall_enabled", True))
                self._heatmap_enabled = bool(getattr(cam, "heatmap_enabled", True))
                self._fire_enabled = bool(getattr(cam, "fire_enabled", True))
                self._fall_enabled = bool(getattr(cam, "fall_enabled", True))
                self._face_enabled = bool(getattr(cam, "face_enabled", True))
                self._ppe_enabled = bool(getattr(cam, "ppe_enabled", False))
                fire_min_conf = getattr(cam, "fire_min_confidence", None)
                self._fire_conf_threshold = (
                    float(max(0.0, min(1.0, float(fire_min_conf))))
                    if fire_min_conf is not None
                    else FIRE_CONF_THRESHOLD
                )
                logger.info(
                    "Camera %s fire settings: enabled=%s threshold=%.3f backend=%s path=%s",
                    self.camera_id,
                    self._fire_enabled,
                    self._fire_conf_threshold,
                    self._fire_backend,
                    self._fire_model_resolved_path or "HSV",
                )
                fall_req = getattr(cam, "fall_consecutive_frames", None)
                self._fall_consecutive_required = (
                    max(1, int(fall_req)) if fall_req is not None else FALL_CONSECUTIVE_FRAMES
                )
                face_min_sim = getattr(cam, "face_min_similarity", None)
                self._face_min_similarity_override = (
                    float(max(0.0, min(1.0, float(face_min_sim))))
                    if face_min_sim is not None
                    else FACE_MIN_SIMILARITY
                )
                ppe_conf = getattr(cam, "ppe_confidence", None)
                self._ppe_conf_threshold = (
                    float(max(0.0, min(1.0, float(ppe_conf))))
                    if ppe_conf is not None
                    else PPE_CONF_THRESHOLD
                )
                raw_items = getattr(cam, "ppe_items", None)
                parsed_items: List[object] = []
                if isinstance(raw_items, list):
                    parsed_items = raw_items
                elif isinstance(raw_items, str):
                    # Backward compatibility: some legacy DB rows may hold JSON text.
                    try:
                        val = json.loads(raw_items)
                        if isinstance(val, list):
                            parsed_items = val
                    except Exception:
                        parsed_items = []
                items = {
                    t
                    for t in (_normalize_ppe_item_token(x) for x in parsed_items)
                    if t
                }
                self._ppe_items_required = items or {
                    t for t in (_normalize_ppe_item_token(x) for x in PPE_DEFAULT_ITEMS) if t
                }
                self._weapon_enabled = bool(getattr(cam, "weapon_enabled", False))
                wconf = getattr(cam, "weapon_confidence", None)
                self._weapon_conf_threshold = (
                    float(max(0.0, min(1.0, float(wconf))))
                    if wconf is not None
                    else WEAPON_CONF_THRESHOLD
                )
                if (
                    not self._weapon_enabled
                    and (self._weapon_model is not None or self._weapon_use_coco_knife)
                ):
                    if not self._weapon_disabled_hint_logged:
                        self._weapon_disabled_hint_logged = True
                        logger.warning(
                            "Camera %s (%s): weapon_enabled is false — enable Weapon in camera settings for weapon alerts.",
                            self.camera_id,
                            getattr(cam, "name", "") or "?",
                        )
                ly = getattr(cam, "footfall_line_y", None)
                if ly is not None:
                    self._footfall_line_y = float(max(0.02, min(0.98, float(ly))))
                fm = getattr(cam, "footfall_mode", None) or "line"
                fm = str(fm).strip().lower()
                self._footfall_mode = fm if fm in ("line", "zone") else "line"
                self._organization_id = getattr(cam, "organization_id", None)
        except Exception as exc:
            logger.debug("Footfall settings refresh: %s", exc)
        finally:
            db.close()

    def _run_loop(self):
        self._update_camera_status("active")
        while not self._stop_event.is_set():
            source = self.rtsp_url
            if not source.startswith(("rtsp://", "rtsps://", "http://", "https://")) and os.path.exists(source):
                source = os.path.abspath(source)
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                self._stop_event.wait(STREAM_RECONNECT_DELAY)
                continue
            self._process_stream(cap)
            cap.release()
        self._update_camera_status("inactive")

    def _needs_person_inference(self) -> bool:
        return (
            self._person_detection_enabled
            or self._crowd_roi_enabled
            or self._crowd_limit_enabled
            or self._footfall_enabled
            or self._heatmap_enabled
        )

    def _norm_roi_rect(self) -> Tuple[float, float, float, float]:
        x1, x2 = min(self._roi_x1, self._roi_x2), max(self._roi_x1, self._roi_x2)
        y1, y2 = min(self._roi_y1, self._roi_y2), max(self._roi_y1, self._roi_y2)
        return (x1, x2, y1, y2)

    def _count_in_roi(self, points: List[Tuple[float, float]]) -> int:
        rx1, rx2, ry1, ry2 = self._norm_roi_rect()
        n = 0
        for nx, ny in points:
            if rx1 <= nx <= rx2 and ry1 <= ny <= ry2:
                n += 1
        return n

    def _person_boxes_and_points(
        self, frame
    ) -> Tuple[List[Tuple[float, float, float, float]], List[Tuple[float, float]], List[Optional[int]]]:
        """YOLO person inference: bbox pixels + normalized points (+ optional persistent track ids)."""
        if not self._person_model:
            return [], [], []
        h, w = frame.shape[:2]
        if h <= 0 or w <= 0:
            return [], [], []
        try:
            if self._track_backend == "bytetrack":
                res = self._person_model.track(
                    frame,
                    conf=FOOTFALL_PERSON_CONF,
                    verbose=False,
                    imgsz=FOOTFALL_INFER_IMGSZ,
                    classes=[0],
                    max_det=FOOTFALL_YOLO_MAX_DET,
                    persist=True,
                    tracker="bytetrack.yaml",
                )
            else:
                res = self._person_model.predict(
                    frame,
                    conf=FOOTFALL_PERSON_CONF,
                    verbose=False,
                    imgsz=FOOTFALL_INFER_IMGSZ,
                    classes=[0],
                    max_det=FOOTFALL_YOLO_MAX_DET,
                )
        except Exception as exc:
            logger.debug("Person predict failed: %s", exc)
            return [], [], []
        boxes_px: List[Tuple[float, float, float, float]] = []
        points_norm: List[Tuple[float, float]] = []
        track_ids: List[Optional[int]] = []
        use_foot = FOOTFALL_TRACK_POINT in ("foot", "bottom", "feet")
        raw: List[Tuple[Tuple[float, float, float, float], float, Tuple[float, float]]] = []
        raw_tids: List[Optional[int]] = []
        for r in res:
            if not r.boxes:
                continue
            xy = r.boxes.xyxy.cpu().numpy()
            cf = r.boxes.conf.cpu().numpy() if getattr(r.boxes, "conf", None) is not None else None
            ids = r.boxes.id.cpu().numpy() if getattr(r.boxes, "id", None) is not None else None
            for i, box in enumerate(xy):
                x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
                pconf = float(cf[i]) if cf is not None and i < len(cf) else 1.0
                if pconf < PERSON_MIN_PER_BOX_CONF:
                    continue
                bw = max(0.0, x2 - x1)
                bh = max(0.0, y2 - y1)
                if bw <= 0 or bh <= 0:
                    continue
                area_norm = (bw * bh) / float(max(1.0, w * h))
                h_norm = bh / float(max(1.0, h))
                aspect = bw / float(max(1e-6, bh))
                if area_norm < PERSON_MIN_BOX_AREA_NORM:
                    continue
                if h_norm < PERSON_MIN_BOX_HEIGHT_NORM:
                    continue
                if PERSON_MIN_W_OVER_H > 0 and aspect < PERSON_MIN_W_OVER_H:
                    continue
                if aspect > PERSON_MAX_BOX_ASPECT:
                    continue
                if pconf < PERSON_COUNT_CONF_MIN:
                    continue
                cx = ((x1 + x2) / 2.0) / w
                if use_foot:
                    cy = y2 / h
                else:
                    cy = ((y1 + y2) / 2.0) / h
                raw.append(((x1, y1, x2, y2), pconf, (float(cx), float(cy))))
                tid: Optional[int] = None
                if ids is not None and i < len(ids):
                    try:
                        tid = int(ids[i])
                    except Exception:
                        tid = None
                raw_tids.append(tid)

        if self._track_backend == "bytetrack":
            for i, ((x1, y1, x2, y2), _pconf, (cx, cy)) in enumerate(raw):
                boxes_px.append((x1, y1, x2, y2))
                points_norm.append((cx, cy))
                track_ids.append(raw_tids[i] if i < len(raw_tids) else None)
            return boxes_px, points_norm, track_ids

        merged = _dedupe_person_detections(raw, PERSON_DEDUPE_IOU) if raw else []
        for (x1, y1, x2, y2), _pconf, (cx, cy) in merged:
            boxes_px.append((x1, y1, x2, y2))
            points_norm.append((cx, cy))
            track_ids.append(None)
        return boxes_px, points_norm, track_ids

    def _draw_roi_overlay(
        self,
        frame,
        h: int,
        w: int,
        count: int,
        subtitle: Optional[str] = None,
    ) -> None:
        rx1, rx2, ry1, ry2 = self._norm_roi_rect()
        x1, y1 = int(rx1 * w), int(ry1 * h)
        x2, y2 = int(rx2 * w), int(ry2 * h)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 200, 100), 2)
        if subtitle:
            cv2.putText(
                frame,
                subtitle,
                (x1, max(18, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 220, 140),
                1,
                lineType=cv2.LINE_AA,
            )
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.putText(
            frame,
            str(count),
            (cx - 6, cy + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 220, 120),
            2,
        )

    def _persist_roi_count(self, count: int) -> None:
        from app.models import Camera

        db = self._db_factory()
        try:
            cam = db.query(Camera).filter(Camera.id == self.camera_id).first()
            if cam:
                cam.last_crowd_roi_count = int(count)
                db.commit()
        except Exception as exc:
            logger.debug("ROI count persist: %s", exc)
            db.rollback()
        finally:
            db.close()

    def _emit_crowd_roi_ws(self, count: int) -> None:
        payload = {
            "event": "crowd_roi",
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "count_in_roi": int(count),
        }
        try:
            self._broadcast_ws(payload)
        except Exception as exc:
            logger.debug("Crowd ROI WS broadcast failed: %s", exc)

    def _recent_overcrowd_alert_in_db(self) -> bool:
        """Avoid duplicate Overcrowd rows shortly apart (e.g. worker restart mid-incident)."""
        from app.models import Alert, AlertTypeEnum

        db = self._db_factory()
        try:
            since = datetime.utcnow() - timedelta(seconds=CROWD_OVERCROWD_ALERT_MIN_INTERVAL_SECONDS)
            row = (
                db.query(Alert.id)
                .filter(
                    Alert.camera_id == self.camera_id,
                    Alert.type == AlertTypeEnum.crowd,
                    Alert.timestamp >= since,
                    Alert.notes.isnot(None),
                )
                .filter(Alert.notes.contains("Overcrowd"))
                .first()
            )
            return row is not None
        except Exception:
            return False
        finally:
            db.close()

    def _emit_crowd_limit_alert(self, frame: np.ndarray, people_count: int, max_people: int) -> None:
        now = time.time()
        if now - self._last_crowd_limit_alert_ts < CROWD_LIMIT_ALERT_COOLDOWN_SECONDS:
            return
        if self._recent_overcrowd_alert_in_db():
            return
        self._last_crowd_limit_alert_ts = now
        snapshot = self._save_snapshot(frame, "CrowdLimit")
        confidence = min(0.99, max(0.50, people_count / float(max(max_people, 1))))
        aid = self._save_alert_to_db(
            "Crowd",
            confidence,
            snapshot,
            notes=f"Overcrowd: {int(people_count)}/{int(max_people)}",
        )
        payload = {
            "event": "alert",
            "alert_id": int(aid or now * 1000),
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "type": "Crowd",
            "subtype": "Overcrowd",
            "confidence": f"{confidence:.2f}",
            "timestamp": _utc_now_iso(),
            "snapshot_path": snapshot,
            "people_count": int(people_count),
            "max_people": int(max_people),
        }
        try:
            self._broadcast_ws(payload)
        except Exception as exc:
            logger.debug("Crowd limit WS broadcast failed: %s", exc)

    def _emit_crowd_event(self, frame: np.ndarray, subtype: str, confidence: float, extras: Dict[str, object]) -> None:
        now = time.time()
        last = self._crowd_event_last_ts.get(subtype, 0.0)
        if now - last < CROWD_EVENT_COOLDOWN_SECONDS:
            return
        self._crowd_event_last_ts[subtype] = now
        snapshot = self._save_snapshot(frame, f"Crowd{subtype}")
        notes = f"{subtype}: " + ", ".join(f"{k}={v}" for k, v in (extras or {}).items())
        aid = self._save_alert_to_db("Crowd", confidence, snapshot, notes=notes[:2000])
        payload = {
            "event": "alert",
            "alert_id": int(aid or now * 1000),
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "type": "Crowd",
            "subtype": subtype,
            "confidence": f"{max(0.1, min(0.99, confidence)):.2f}",
            "timestamp": _utc_now_iso(),
            "snapshot_path": snapshot,
        }
        payload.update(extras or {})
        try:
            self._broadcast_ws(payload)
        except Exception as exc:
            logger.debug("Crowd %s WS broadcast failed: %s", subtype, exc)

    def _flow_window_counts(self) -> Tuple[int, int]:
        now = time.time()
        cutoff = now - max(1, FLOW_WINDOW_SECONDS)
        while self._flow_recent and self._flow_recent[0][0] < cutoff:
            self._flow_recent.popleft()
        entry_60 = sum(1 for _ts, d in self._flow_recent if d == "entry")
        exit_60 = sum(1 for _ts, d in self._flow_recent if d == "exit")
        return int(entry_60), int(exit_60)

    def _resolve_crowd_limit_count(
        self, people_count: int, roi_count: int, show_roi: bool
    ) -> Tuple[int, str]:
        """
        Count used for overcrowd alerts (must match on-screen text). limit_basis:
        'none' — limit disabled; 'frame' — full frame; 'zone' — ROI rectangle only.
        """
        if not self._crowd_limit_enabled:
            return people_count, "none"
        mode = CROWD_LIMIT_COUNT_MODE
        if mode == "roi":
            return roi_count, "zone"
        if mode == "global":
            return people_count, "frame"
        if show_roi:
            return roi_count, "zone"
        return people_count, "frame"

    def _emit_crowd_metric_ws(
        self,
        people_count: int,
        roi_count: int,
        limit_count: int,
        limit_basis: str,
        roi_active: bool,
    ) -> None:
        now = time.time()
        if now - self._last_crowd_metric_ws_ts < CROWD_METRIC_EMIT_SECONDS:
            return
        self._last_crowd_metric_ws_ts = now
        entry_60, exit_60 = self._flow_window_counts()
        cf = bool(
            min(entry_60, exit_60) >= COUNTERFLOW_MIN_EVENTS_60S
            and (max(entry_60, exit_60) / float(max(1, min(entry_60, exit_60)))) <= COUNTERFLOW_MAX_DIR_RATIO
        )
        payload = {
            "event": "crowd_metric",
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "timestamp": _utc_now_iso(),
            "people_count": int(people_count),
            "roi_count": int(roi_count),
            "limit_count": int(limit_count),
            "limit_basis": str(limit_basis),
            "roi_active": bool(roi_active),
            "crowd_roi_enabled": bool(self._crowd_roi_enabled),
            "crowd_limit_enabled": bool(self._crowd_limit_enabled),
            "max_people": int(self._crowd_max_people),
            "overcrowded": bool(
                self._crowd_limit_enabled and limit_count > self._crowd_max_people
            ),
            "entry_60s": int(entry_60),
            "exit_60s": int(exit_60),
            "net_60s": int(entry_60 - exit_60),
            "counterflow": cf,
        }
        try:
            self._broadcast_ws(payload)
        except Exception as exc:
            logger.debug("Crowd metric WS broadcast failed: %s", exc)

    def _evaluate_crowd_events(
        self,
        frame: np.ndarray,
        crowd_count_for_limit: int,
        roi_count: int,
        show_roi: bool,
    ) -> None:
        entry_60, exit_60 = self._flow_window_counts()
        min_dir = min(entry_60, exit_60)
        max_dir = max(entry_60, exit_60)
        dir_ratio = max_dir / float(max(1, min_dir))
        if min_dir >= COUNTERFLOW_MIN_EVENTS_60S and dir_ratio <= COUNTERFLOW_MAX_DIR_RATIO:
            conf = min(0.95, 0.55 + 0.03 * min_dir)
            self._emit_crowd_event(
                frame,
                "CounterFlow",
                conf,
                {
                    "entry_60s": int(entry_60),
                    "exit_60s": int(exit_60),
                    "net_60s": int(entry_60 - exit_60),
                    "people_count": int(crowd_count_for_limit),
                    "max_people": int(self._crowd_max_people),
                },
            )

        queue_count = roi_count if show_roi else crowd_count_for_limit
        if queue_count >= QUEUE_HIGH_ROI_THRESHOLD:
            self._queue_high_consecutive += 1
        else:
            self._queue_high_consecutive = 0
        if self._queue_high_consecutive >= QUEUE_HIGH_CONSEC_FRAMES:
            conf = min(0.96, 0.50 + 0.025 * queue_count)
            self._emit_crowd_event(
                frame,
                "QueueHigh",
                conf,
                {
                    "roi_count": int(roi_count),
                    "people_count": int(crowd_count_for_limit),
                    "queue_threshold": int(QUEUE_HIGH_ROI_THRESHOLD),
                    "max_people": int(self._crowd_max_people),
                },
            )
            self._queue_high_consecutive = 0

    def _process_stream(self, cap: cv2.VideoCapture) -> None:
        logger.info(
            "StreamProcessor._process_stream START: cam=%s url=%s fire_enabled=%s consecutive_req=%s",
            self.camera_id,
            self.rtsp_url[:50] if self.rtsp_url else None,
            self._fire_enabled,
            FIRE_CONSECUTIVE_FRAMES,
        )
        self._refresh_camera_analytics_settings()
        frame_idx = 0
        settings_counter = 0
        is_file = not self.rtsp_url.startswith(("rtsp://", "rtmp://", "http://", "https://"))
        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break

            frame_idx += 1
            settings_counter += 1
            if settings_counter >= SETTINGS_REFRESH_INFER_FRAMES:
                settings_counter = 0
                self._refresh_camera_analytics_settings()

            # Keep pose landmarks fresh for fall overlay + detection when fall module is on
            if self._fall_enabled:
                self._update_pose_landmarks(frame)

            # Publish preview immediately for smooth MJPEG stream
            # (heavy modules except fire run on every Nth frame)
            self._publish_preview(frame)

            # Fire detection runs on EVERY frame for immediate response
            fire_conf = self._detect_fire(frame) if self._fire_enabled else None
            if self._fire_enabled:
                if fire_conf:
                    self._fire_consecutive += 1
                else:
                    self._fire_consecutive = 0
                logger.debug(
                    "Fire eval: conf=%s consecutive=%s threshold=%s",
                    fire_conf,
                    self._fire_consecutive,
                    FIRE_CONSECUTIVE_FRAMES,
                )
                if fire_conf and self._fire_consecutive >= FIRE_CONSECUTIVE_FRAMES:
                    logger.warning(
                        "FIRE_ALERT_TRIGGERED cam=%s conf=%.2f consecutive=%d",
                        self.camera_id,
                        fire_conf,
                        self._fire_consecutive,
                    )
                    self._trigger_alert(frame, "Fire", fire_conf)
                    self._fire_consecutive = 0
                if fire_conf:
                    if self._fire_overlay_boxes:
                        for (x1, y1, x2, y2), fconf in self._fire_overlay_boxes:
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                            cv2.putText(
                                frame,
                                f"FIRE {fconf:.2f}",
                                (x1, max(16, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.55,
                                (0, 0, 255),
                                2,
                                lineType=cv2.LINE_AA,
                            )
                    else:
                        cv2.putText(
                            frame,
                            f"FIRE {fire_conf:.2f}",
                            (10, 48),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.65,
                            (0, 0, 255),
                            2,
                            lineType=cv2.LINE_AA,
                        )
            else:
                self._fire_consecutive = 0

            # Skip other detections on every Nth frame (to balance performance)
            if frame_idx % INFER_EVERY_N_FRAMES != 0:
                continue

            fall_conf = self._detect_fall(frame) if self._fall_enabled else None
            if self._fall_enabled and fall_conf:
                self._trigger_alert(frame, "Fall", fall_conf)
                cv2.putText(
                    frame,
                    f"FALL RISK {fall_conf:.2f}",
                    (10, 72),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.62,
                    (0, 120, 255),
                    2,
                    lineType=cv2.LINE_AA,
                )
            if not self._fall_enabled:
                self._fall_consecutive = 0

            if self._ppe_enabled:
                ppe = self._detect_ppe_violation(frame)
                if ppe:
                    conf, notes = ppe
                    self._trigger_alert(frame, "PPE", conf, notes=notes)
                if self._ppe_overlay_boxes:
                    for (x1, y1, x2, y2), col, tag in self._ppe_overlay_boxes:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                        cv2.putText(
                            frame,
                            tag[:48],
                            (x1, max(14, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.48,
                            col,
                            1,
                            lineType=cv2.LINE_AA,
                        )

            if self._weapon_enabled:
                wdet = self._detect_weapon(frame)
                if wdet:
                    wconf, wnotes = wdet
                    # Persist annotated snapshot (red boxes) — not the raw frame (was missing highlights).
                    self._trigger_alert(
                        self._weapon_alert_snapshot_bgr(frame),
                        "Weapon",
                        wconf,
                        notes=wnotes,
                    )
                if self._weapon_overlay_boxes:
                    wcol = (0, 0, 255)  # BGR red — match saved alert snapshot
                    for (x1, y1, x2, y2), wlbl, wc in self._weapon_overlay_boxes:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), wcol, 3, lineType=cv2.LINE_AA)
                        cv2.putText(
                            frame,
                            f"{wlbl[:32]} {wc:.2f}",
                            (x1, max(16, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.52,
                            wcol,
                            2,
                            lineType=cv2.LINE_AA,
                        )

            if self._face_app and self._face_enabled:
                self._process_faces(frame, frame_idx)

            if not self._person_model or not self._needs_person_inference():
                # Person inference disabled; continue with next frame
                continue

            boxes_px, points_norm, track_ids = self._person_boxes_and_points(frame)
            self._maybe_record_person_reid_samples(frame, boxes_px, track_ids, frame_idx)
            tracked_points: List[Tuple[int, float, float]] = []
            if self._track_backend == "bytetrack":
                for i, (nx, ny) in enumerate(points_norm):
                    tid = track_ids[i] if i < len(track_ids) else None
                    if tid is not None:
                        tracked_points.append((tid, nx, ny))
            stable_points = points_norm if self._track_backend == "bytetrack" else self._presence_tracker.update(points_norm)
            h, w = frame.shape[:2]
            people_count = len(stable_points)

            show_roi = self._crowd_roi_enabled or (
                self._footfall_enabled and self._footfall_mode == "zone"
            )
            roi_count = 0
            if show_roi:
                roi_count = self._count_in_roi(stable_points)
                sub = "FOOTFALL ZONE" if (self._footfall_mode == "zone" and self._footfall_enabled) else None
                self._draw_roi_overlay(frame, h, w, roi_count, subtitle=sub)
                now = time.time()
                if now - self._last_roi_db_ts >= 2.0:
                    self._last_roi_db_ts = now
                    self._persist_roi_count(roi_count)
                if now - self._last_roi_ws_ts >= 1.0:
                    self._last_roi_ws_ts = now
                    self._emit_crowd_roi_ws(roi_count)

            limit_count, _limit_basis = self._resolve_crowd_limit_count(
                people_count, roi_count, show_roi
            )

            if self._crowd_limit_enabled:
                limit_col = (0, 180, 255) if limit_count <= self._crowd_max_people else (0, 80, 255)
                cv2.putText(
                    frame,
                    f"People: {limit_count}/{self._crowd_max_people}",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    limit_col,
                    2,
                    lineType=cv2.LINE_AA,
                )
                if limit_count > self._crowd_max_people:
                    self._crowd_over_limit_consecutive += 1
                else:
                    self._crowd_over_limit_consecutive = 0
                    self._overcrowd_incident_active = False
                if (
                    limit_count > self._crowd_max_people
                    and self._crowd_over_limit_consecutive >= CROWD_OVER_LIMIT_CONSEC_FRAMES
                    and not self._overcrowd_incident_active
                ):
                    self._emit_crowd_limit_alert(frame, limit_count, self._crowd_max_people)
                    self._overcrowd_incident_active = True
            else:
                cv2.putText(
                    frame,
                    f"People: {people_count}",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 220, 120),
                    2,
                    lineType=cv2.LINE_AA,
                )

            self._evaluate_crowd_events(frame, limit_count, roi_count, show_roi)
            self._emit_crowd_metric_ws(
                people_count, roi_count, limit_count, _limit_basis, show_roi
            )

            if self._person_detection_enabled:
                for (x1, y1, x2, y2) in boxes_px:
                    i1, i2, i3, i4 = int(x1), int(y1), int(x2), int(y2)
                    cv2.rectangle(frame, (i1, i2), (i3, i4), (255, 180, 0), 2)
                    cv2.putText(
                        frame,
                        "person",
                        (i1, max(12, i2 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 220, 120),
                        1,
                    )

            if self._footfall_enabled and self._footfall_mode == "line":
                line_y_abs = int(self._footfall_line_y * h)
                cv2.line(frame, (0, line_y_abs), (w, line_y_abs), (255, 255, 255), 2)
                cv2.putText(
                    frame,
                    "Footfall line",
                    (10, max(10, line_y_abs - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 255, 255),
                    1,
                )

            if self._heatmap_enabled:
                self._draw_heatmap_grid_overlay(frame, h, w)

            if tracked_points:
                self._process_crowd_analytics_tracked(tracked_points, stable_points)
            else:
                self._process_crowd_analytics_points(stable_points)

    def _process_crowd_analytics_points(self, centroids: List[Tuple[float, float]]) -> None:
        if not self._person_model:
            return
        if not self._footfall_enabled and not self._heatmap_enabled:
            return

        if self._heatmap_enabled:
            now_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
            if self._heatmap_hour_bucket is None:
                self._heatmap_hour_bucket = now_hour
            elif now_hour > self._heatmap_hour_bucket:
                self._flush_heatmap_buffer()
                self._heatmap_hour_bucket = now_hour
            for nx, ny in centroids:
                ix = int(min(HEATMAP_GRID_SIZE - 1, max(0, nx * HEATMAP_GRID_SIZE)))
                iy = int(min(HEATMAP_GRID_SIZE - 1, max(0, ny * HEATMAP_GRID_SIZE)))
                self._heatmap_cells[iy, ix] += 1
            if time.time() - self._last_heatmap_flush > HEATMAP_FLUSH_SECONDS:
                self._flush_heatmap_buffer()
                self._last_heatmap_flush = time.time()

        if self._footfall_enabled:
            if self._footfall_mode == "zone":
                bounds = self._norm_roi_rect()
                events = self._zone_footfall_tracker.update(centroids, bounds)
            else:
                events = self._footfall_tracker.update(centroids, self._footfall_line_y)
            now = time.time()
            for tid, direc in events:
                last = self._last_footfall_cross_ts.get(tid, 0.0)
                if now - last < FOOTFALL_PER_TRACK_COOLDOWN:
                    continue
                self._last_footfall_cross_ts[tid] = now
                self._flow_recent.append((now, direc))
                self._save_footfall(direc, tid)

    def _process_crowd_analytics_tracked(
        self, tracks: List[Tuple[int, float, float]], centroids: List[Tuple[float, float]]
    ) -> None:
        """
        ByteTrack path: use persistent track IDs for entry/exit events.
        Falls back to heatmap accumulation from centroids.
        """
        if not self._person_model:
            return
        if not self._footfall_enabled and not self._heatmap_enabled:
            return
        if self._heatmap_enabled:
            now_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
            if self._heatmap_hour_bucket is None:
                self._heatmap_hour_bucket = now_hour
            elif now_hour > self._heatmap_hour_bucket:
                self._flush_heatmap_buffer()
                self._heatmap_hour_bucket = now_hour
            for nx, ny in centroids:
                ix = int(min(HEATMAP_GRID_SIZE - 1, max(0, nx * HEATMAP_GRID_SIZE)))
                iy = int(min(HEATMAP_GRID_SIZE - 1, max(0, ny * HEATMAP_GRID_SIZE)))
                self._heatmap_cells[iy, ix] += 1
            if time.time() - self._last_heatmap_flush > HEATMAP_FLUSH_SECONDS:
                self._flush_heatmap_buffer()
                self._last_heatmap_flush = time.time()
        now = time.time()
        if self._footfall_enabled:
            events: List[Tuple[int, str]] = []
            if self._footfall_mode == "zone":
                rx1, rx2, ry1, ry2 = self._norm_roi_rect()
                for tid, nx, ny in tracks:
                    prev = self._bt_prev_points.get(tid)
                    self._bt_prev_points[tid] = (nx, ny)
                    self._bt_last_seen[tid] = now
                    if prev is None:
                        continue
                    p_in = rx1 <= prev[0] <= rx2 and ry1 <= prev[1] <= ry2
                    n_in = rx1 <= nx <= rx2 and ry1 <= ny <= ry2
                    if (not p_in) and n_in:
                        events.append((tid, "entry"))
                    elif p_in and (not n_in):
                        events.append((tid, "exit"))
            else:
                for tid, nx, ny in tracks:
                    prev = self._bt_prev_points.get(tid)
                    self._bt_prev_points[tid] = (nx, ny)
                    self._bt_last_seen[tid] = now
                    if prev is None:
                        continue
                    if _crosses_horizontal_line(prev[1], ny, self._footfall_line_y):
                        events.append((tid, "entry" if ny > prev[1] else "exit"))

            for tid, direc in events:
                last = self._last_footfall_cross_ts.get(tid, 0.0)
                if now - last < FOOTFALL_PER_TRACK_COOLDOWN:
                    continue
                self._last_footfall_cross_ts[tid] = now
                self._flow_recent.append((now, direc))
                self._save_footfall(direc, tid)

        # Drop stale tracks so memory does not grow forever.
        cutoff = now - 3.0
        for tid in list(self._bt_last_seen.keys()):
            if self._bt_last_seen[tid] < cutoff:
                self._bt_last_seen.pop(tid, None)
                self._bt_prev_points.pop(tid, None)

    def _flush_heatmap_buffer(self):
        if self._heatmap_hour_bucket is None or self._heatmap_cells.sum() == 0:
            return
        from app.models import CrowdHeatmapHourly

        db = self._db_factory()
        try:
            flat = self._heatmap_cells.flatten().astype(int).tolist()
            row = (
                db.query(CrowdHeatmapHourly)
                .filter_by(camera_id=self.camera_id, hour_bucket=self._heatmap_hour_bucket)
                .first()
            )
            if row:
                old = row.cells or [0] * len(flat)
                if len(old) != len(flat):
                    old = [0] * len(flat)
                row.cells = [a + b for a, b in zip(old, flat)]
            else:
                db.add(
                    CrowdHeatmapHourly(
                        camera_id=self.camera_id,
                        hour_bucket=self._heatmap_hour_bucket,
                        grid_size=HEATMAP_GRID_SIZE,
                        cells=flat,
                    )
                )
            db.commit()
            self._heatmap_cells.fill(0)
            self._emit_heatmap_flush_ws()
        except Exception as exc:
            logger.error("Heatmap flush: %s", exc)
            db.rollback()
        finally:
            db.close()

    def _emit_footfall_ws(self, direction: str, track_id: int, crossed_at: datetime) -> None:
        """Push footfall crossing to dashboards over the shared WebSocket."""
        payload = {
            "event": "footfall",
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "direction": direction,
            "track_id": track_id,
            "crossed_at": _iso_utc(crossed_at),
        }
        try:
            self._broadcast_ws(payload)
        except Exception as exc:
            logger.debug("Footfall WS broadcast failed: %s", exc)

    def _emit_heatmap_flush_ws(self) -> None:
        payload = {
            "event": "heatmap_flush",
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
        }
        if self._heatmap_hour_bucket is not None:
            payload["hour_bucket"] = _iso_utc(self._heatmap_hour_bucket)
        try:
            self._broadcast_ws(payload)
        except Exception as exc:
            logger.debug("Heatmap WS broadcast failed: %s", exc)

    def _save_footfall(self, direction, track_id):
        from app.models import FootfallCrossing, FootfallDirectionEnum
        db = self._db_factory()
        crossed_at = datetime.utcnow()
        try:
            db.add(
                FootfallCrossing(
                    camera_id=self.camera_id,
                    direction=FootfallDirectionEnum(direction),
                    crossed_at=crossed_at,
                    track_id=track_id,
                )
            )
            db.commit()
        finally:
            db.close()
        self._emit_footfall_ws(direction, track_id, crossed_at)

    def _refresh_face_identities(self) -> None:
        if not self._face_app:
            return
        now = time.time()
        if now - self._face_last_refresh_ts < FACE_IDENTITY_REFRESH_SECONDS:
            return
        self._face_last_refresh_ts = now
        from app.models import FaceIdentity

        db = self._db_factory()
        try:
            q = db.query(FaceIdentity).filter(FaceIdentity.is_active == True)  # noqa: E712
            if self._organization_id is not None:
                from sqlalchemy import or_

                q = q.filter(
                    or_(
                        FaceIdentity.organization_id == self._organization_id,
                        FaceIdentity.organization_id.is_(None),
                    )
                )
            rows = q.all()
            data: List[dict] = []
            for r in rows:
                emb_list = r.embeddings or []
                for e in emb_list:
                    try:
                        v = np.asarray(e, dtype=np.float32).reshape(-1)
                        n = float(np.linalg.norm(v))
                        if n <= 1e-9:
                            continue
                        data.append(
                            {
                                "identity_id": int(r.id),
                                "name": str(r.name),
                                "category": str(r.category.value if hasattr(r.category, "value") else r.category),
                                "emb": v / n,
                            }
                        )
                    except Exception:
                        continue
            self._face_identities = data
            if FACE_RECOGNITION_ENABLED and data:
                logger.debug("Face registry: loaded %d embedding vectors for matching.", len(data))
        except Exception as exc:
            logger.debug("Face identity refresh failed: %s", exc)
        finally:
            db.close()

    def _match_face_embedding(self, embedding: np.ndarray) -> Optional[dict]:
        if not self._face_identities:
            return None
        v = np.asarray(embedding, dtype=np.float32).reshape(-1)
        n = float(np.linalg.norm(v))
        if n <= 1e-9:
            return None
        v = v / n
        best = None
        best_sim = -1.0
        for item in self._face_identities:
            sim = float(np.dot(v, item["emb"]))
            if sim > best_sim:
                best_sim = sim
                best = item
        min_sim = (
            self._face_min_similarity_override
            if self._face_min_similarity_override is not None
            else (1.0 - FACE_MATCH_THRESHOLD)
        )
        if best is None or best_sim < min_sim:
            return None
        out = dict(best)
        out["similarity"] = best_sim
        return out

    def _record_face_sighting(
        self,
        identity_id: Optional[int],
        category: str,
        confidence: float,
        event_type: str,
        snapshot_path: Optional[str],
        notes: Optional[str] = None,
    ) -> None:
        from app.models import FaceCategoryEnum, FaceSighting

        db = self._db_factory()
        try:
            cat = FaceCategoryEnum(category)
            row = FaceSighting(
                camera_id=self.camera_id,
                identity_id=identity_id,
                category=cat,
                confidence=float(confidence),
                event_type=str(event_type),
                timestamp=datetime.utcnow(),
                snapshot_path=snapshot_path,
                notes=notes,
            )
            db.add(row)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.debug("Face sighting save failed: %s", exc)
        finally:
            db.close()

    def _emit_face_blacklist_alert(
        self, frame: np.ndarray, identity_id: int, identity_name: str, confidence: float
    ) -> None:
        now = time.time()
        key = f"blacklist:{identity_name.lower()}"
        if now - self._face_seen_cooldown.get(key, 0.0) < FACE_COOLDOWN_SECONDS:
            return
        self._face_seen_cooldown[key] = now
        snapshot = self._save_snapshot(frame, "FaceBlacklist")
        notes = f"Blacklist match: {identity_name}"
        aid = self._save_alert_to_db("Face", confidence, snapshot, notes=notes)
        payload = {
            "event": "alert",
            "alert_id": int(aid or now * 1000),
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "type": "Face",
            "subtype": "BlacklistMatch",
            "identity": identity_name,
            "confidence": self._format_confidence(confidence),
            "timestamp": _utc_now_iso(),
            "snapshot_path": snapshot,
        }
        try:
            self._broadcast_ws(payload)
        except Exception as exc:
            logger.debug("Face blacklist WS broadcast failed: %s", exc)
        self._record_face_sighting(
            identity_id=identity_id,
            category="blacklist",
            confidence=confidence,
            event_type="blacklist_alert",
            snapshot_path=snapshot,
            notes=notes,
        )

    def _process_faces(self, frame: np.ndarray, frame_idx: int) -> None:
        if not self._face_app or (frame_idx % FACE_INFER_EVERY_N_FRAMES != 0):
            return
        self._refresh_face_identities()
        if not self._face_identities:
            now_t = time.time()
            if now_t - self._face_no_identity_log_ts >= 60.0:
                self._face_no_identity_log_ts = now_t
                logger.warning(
                    "Face recognition: no embedding vectors in DB for active identities. "
                    "Blacklist alerts need enroll-image with InsightFace working, or JSON embeddings."
                )
            return
        try:
            faces = self._face_app.get(frame)
        except Exception as exc:
            logger.debug("InsightFace inference failed: %s", exc)
            return
        now = time.time()
        for f in faces:
            emb = getattr(f, "normed_embedding", None)
            if emb is None:
                emb = getattr(f, "embedding", None)
            if emb is None:
                continue
            match = self._match_face_embedding(np.asarray(emb, dtype=np.float32))
            if not match:
                continue
            name = str(match.get("name", "unknown"))
            category = _norm_face_category(match.get("category", "neutral"))
            confidence = float(match.get("similarity", 0.0))
            identity_id = int(match.get("identity_id"))
            bbox = getattr(f, "bbox", None)
            if bbox is not None and len(bbox) >= 4:
                x1, y1, x2, y2 = [int(float(v)) for v in bbox[:4]]
                if category == "blacklist":
                    col = (0, 0, 255)
                    tag = f"BLACKLIST: {name} {confidence:.2f}"
                elif category == "whitelist":
                    col = (0, 220, 0)
                    tag = f"WHITELIST: {name} {confidence:.2f}"
                else:
                    col = (0, 220, 220)
                    tag = f"FACE: {name} {confidence:.2f}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                cv2.putText(
                    frame,
                    tag[:48],
                    (x1, max(16, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    col,
                    2 if category == "blacklist" else 1,
                    lineType=cv2.LINE_AA,
                )

            if category == "blacklist":
                self._emit_face_blacklist_alert(frame, identity_id, name, confidence)
                continue

            if category == "whitelist":
                key = f"attendance:{identity_id}"
                if now - self._face_seen_cooldown.get(key, 0.0) >= FACE_ATTENDANCE_COOLDOWN_SECONDS:
                    self._face_seen_cooldown[key] = now
                    self._record_face_sighting(
                        identity_id=identity_id,
                        category="whitelist",
                        confidence=confidence,
                        event_type="attendance",
                        snapshot_path=None,
                        notes=f"Attendance: {name}",
                    )
            else:
                key = f"neutral:{identity_id}"
                if now - self._face_seen_cooldown.get(key, 0.0) >= FACE_ATTENDANCE_COOLDOWN_SECONDS:
                    self._face_seen_cooldown[key] = now
                    self._record_face_sighting(
                        identity_id=identity_id,
                        category="neutral",
                        confidence=confidence,
                        event_type="recognition",
                        snapshot_path=None,
                        notes=f"Recognized neutral identity: {name}",
                    )

    def _detect_ppe_violation(self, frame: np.ndarray) -> Optional[Tuple[float, str]]:
        """
        PPE violation detector that supports two common model styles:
          1) Explicit missing labels: no_helmet / no_vest / ...
          2) Person + equipment labels: person + helmet/vest/... (per-person association)
        """
        self._ppe_overlay_boxes = []
        if not self._ppe_model:
            return None
        dets: List[Tuple[str, float, Optional[Tuple[float, float, float, float]]]] = []
        def collect_from(model, name_map):
            try:
                res = model.predict(frame, conf=self._ppe_conf_threshold, verbose=False, imgsz=640)
            except Exception as exc:
                logger.debug("PPE model inference failed: %s", exc)
                return
            if not res or not res[0].boxes or len(res[0].boxes) == 0:
                return
            boxes = res[0].boxes
            confs = boxes.conf.cpu().numpy() if getattr(boxes, "conf", None) is not None else None
            cls = boxes.cls.cpu().numpy() if getattr(boxes, "cls", None) is not None else None
            xy = boxes.xyxy.cpu().numpy() if getattr(boxes, "xyxy", None) is not None else None
            if cls is None or confs is None:
                return
            for i in range(len(cls)):
                lbl = str(name_map.get(int(cls[i]), "")).strip().lower()
                if not lbl:
                    continue
                box = tuple(map(float, xy[i])) if xy is not None and i < len(xy) else None
                dets.append((lbl, float(confs[i]), box))

        collect_from(self._ppe_model, self._ppe_names)
        if self._ppe_aux_model is not None:
            collect_from(self._ppe_aux_model, self._ppe_aux_names)
        if not dets:
            return None

        req = set(self._ppe_items_required)
        if "kit" in req:
            req.update({"helmet", "vest", "gloves", "boots", "goggles", "mask"})

        def norm_token(s: str) -> str:
            return "".join(ch for ch in str(s).strip().lower() if ch.isalnum())

        missing_label_map = {
            "helmet": {"nohelmet", "nohardhat", "withouthelmet", "helmetmissing"},
            "vest": {"novest", "nosafetyvest", "withoutvest", "vestmissing"},
            "gloves": {"nogloves", "noglove", "withoutgloves", "withoutglove", "glovesmissing", "glovemissing"},
            "boots": {"noboots", "noshoes", "nosafetyshoes", "withoutboots", "bootsmissing"},
            "goggles": {"nogoggles", "noglasses", "withoutgoggles", "gogglesmissing"},
            "mask": {"nomask", "norespirator", "withoutmask", "maskmissing"},
        }
        present_label_map = {
            "helmet": {"helmet", "hardhat", "safetyhelmet"},
            "vest": {"vest", "safetyvest", "reflectivevest"},
            "gloves": {"gloves", "glove", "handgloves"},
            "boots": {"boots", "boot", "safetyshoes", "safetyshoe", "shoes", "shoe"},
            "goggles": {"goggles", "safetyglasses", "glasses"},
            "mask": {"mask", "respirator"},
        }
        person_labels = {"person", "worker", "human", "labour"}

        def center_in(a: Tuple[float, float], b: Tuple[float, float, float, float]) -> bool:
            x, y = a
            x1, y1, x2, y2 = b
            return x1 <= x <= x2 and y1 <= y <= y2

        violations: List[Tuple[str, float]] = []
        person_boxes: List[Tuple[Tuple[float, float, float, float], float]] = []
        equip_boxes: Dict[str, List[Tuple[Tuple[float, float, float, float], float]]] = {k: [] for k in present_label_map}
        explicit_missing: set[str] = set()
        has_any_missing_labels = False
        has_person_label = False
        has_any_present_labels = False
        for lbl_raw, c, box in dets:
            lbl = lbl_raw.lower()
            norm_lbl = norm_token(lbl)
            if norm_lbl in person_labels:
                has_person_label = True
                if box is not None:
                    person_boxes.append((box, c))
                continue
            for equip in req:
                if equip in missing_label_map and norm_lbl in missing_label_map[equip]:
                    has_any_missing_labels = True
                    explicit_missing.add(equip)
                    violations.append((equip, c))
                    if box is not None:
                        x1, y1, x2, y2 = [int(v) for v in box]
                        self._ppe_overlay_boxes.append(((x1, y1, x2, y2), (0, 0, 255), f"MISSING {equip.upper()}"))
                    break
            for equip in req:
                if equip in present_label_map and norm_lbl in present_label_map[equip]:
                    has_any_present_labels = True
                    if box is not None:
                        equip_boxes[equip].append((box, c))
                    break
        # Inference path: infer missing selected PPE from person+equipment overlap.
        # This runs even when explicit missing labels exist, so selected items like gloves
        # can still be marked missing if model doesn't output dedicated no_* class.
        if has_person_label and person_boxes:
            for pbox, _pc in person_boxes:
                person_missing: List[str] = []
                person_present: List[str] = []
                for equip in req:
                    if equip in explicit_missing:
                        person_missing.append(equip)
                        continue
                    candidates = equip_boxes.get(equip, [])
                    found = any(
                        _iou_xyxy(pbox, ebox) >= 0.01
                        or center_in(((ebox[0] + ebox[2]) * 0.5, (ebox[1] + ebox[3]) * 0.5), pbox)
                        for ebox, _ec in candidates
                    )
                    if not found:
                        person_missing.append(equip)
                        violations.append((equip, max(0.55, self._ppe_conf_threshold)))
                    else:
                        person_present.append(equip)
                px1, py1, px2, py2 = [int(v) for v in pbox]
                if person_missing:
                    lbl = "PPE MISSING: " + ",".join(sorted(set(person_missing)))
                    self._ppe_overlay_boxes.append(((px1, py1, px2, py2), (0, 0, 255), lbl))
                elif person_present:
                    lbl = "PPE OK: " + ",".join(sorted(set(person_present)))
                    self._ppe_overlay_boxes.append(((px1, py1, px2, py2), (0, 200, 0), lbl))

        if not violations:
            # Model labels do not support missing-PPE inference.
            if self._ppe_enabled:
                now_t = time.time()
                if now_t - self._ppe_label_warn_ts >= 60.0:
                    self._ppe_label_warn_ts = now_t
                    logger.warning(
                        "PPE model labels are not compatible for violation detection on camera %s. "
                        "Need either explicit missing labels (no_helmet/no_vest/...) or person+equipment labels.",
                        self.camera_id,
                    )
            return None
        best_conf = max(v[1] for v in violations)
        uniq = sorted({v[0] for v in violations})
        required = sorted(x for x in req if x != "kit")
        notes = f"PPE missing: {', '.join(uniq)} | required: {', '.join(required)}"
        return best_conf, notes

    def _weapon_alert_snapshot_bgr(self, frame: np.ndarray) -> np.ndarray:
        """
        Image saved for weapon alerts: red bounding boxes + label/confidence.
        Optionally crops to the union of detections (when the weapon is small in the frame).
        """
        boxes = self._weapon_overlay_boxes
        red = (0, 0, 255)
        if not boxes:
            return frame.copy()

        def _annotate(
            img: np.ndarray,
            items: List[Tuple[Tuple[int, int, int, int], str, float]],
        ) -> None:
            for (x1, y1, x2, y2), wlbl, wc in items:
                cv2.rectangle(img, (x1, y1), (x2, y2), red, 3, lineType=cv2.LINE_AA)
                tag = f"{wlbl} {wc * 100:.0f}%"
                cv2.putText(
                    img,
                    tag[:56],
                    (x1, max(22, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    red,
                    2,
                    lineType=cv2.LINE_AA,
                )

        H, W = frame.shape[:2]
        x1m = min(b[0][0] for b in boxes)
        y1m = min(b[0][1] for b in boxes)
        x2m = max(b[0][2] for b in boxes)
        y2m = max(b[0][3] for b in boxes)
        union_area = max(1, x2m - x1m) * max(1, y2m - y1m)
        frame_area = max(1, W * H)
        use_crop = WEAPON_SNAPSHOT_CROP and (union_area / frame_area) < 0.72
        if not use_crop:
            out = frame.copy()
            _annotate(out, boxes)
            return out
        bw = max(1, x2m - x1m)
        bh = max(1, y2m - y1m)
        pad = int(max(40, 0.26 * max(bw, bh)))
        x1 = max(0, x1m - pad)
        y1 = max(0, y1m - pad)
        x2 = min(W, x2m + pad)
        y2 = min(H, y2m + pad)
        crop = frame[y1:y2, x1:x2].copy()
        shifted: List[Tuple[Tuple[int, int, int, int], str, float]] = []
        for (bx1, by1, bx2, by2), wlbl, wc in boxes:
            shifted.append(((bx1 - x1, by1 - y1, bx2 - x1, by2 - y1), wlbl, wc))
        _annotate(crop, shifted)
        return crop

    def _detect_weapon(self, frame: np.ndarray) -> Optional[Tuple[float, str]]:
        self._weapon_overlay_boxes = []
        use_coco_fb = (
            self._weapon_use_coco_knife
            and self._person_model is not None
            and bool(self._weapon_coco_ids)
        )
        model = self._weapon_model
        class_ids = self._weapon_class_ids
        names_map = self._weapon_names
        if use_coco_fb and model is None:
            model = self._person_model
            class_ids = set(self._weapon_coco_ids)
            names_map = dict(self._weapon_coco_names)
        if not model or not class_ids:
            return None
        try:
            pred_kw = dict(conf=self._weapon_conf_threshold, verbose=False, imgsz=640)
            if use_coco_fb and self._weapon_coco_ids:
                pred_kw["classes"] = sorted(int(x) for x in self._weapon_coco_ids)
            res = model.predict(frame, **pred_kw)
        except Exception as exc:
            logger.debug("Weapon model inference failed: %s", exc)
            return None
        if not res or not res[0].boxes or len(res[0].boxes) == 0:
            return None
        boxes = res[0].boxes
        confs = boxes.conf.cpu().numpy() if getattr(boxes, "conf", None) is not None else None
        cls_arr = boxes.cls.cpu().numpy() if getattr(boxes, "cls", None) is not None else None
        xy = boxes.xyxy.cpu().numpy() if getattr(boxes, "xyxy", None) is not None else None
        best_conf = 0.0
        best_lbl = "weapon"
        for i in range(len(boxes)):
            if cls_arr is not None:
                try:
                    ci = int(cls_arr[i])
                except Exception:
                    continue
                if ci not in class_ids:
                    continue
            else:
                ci = -1
            cconf = float(confs[i]) if confs is not None and i < len(confs) else 0.0
            lbl = names_map.get(ci, "weapon") if ci >= 0 else "weapon"
            if xy is not None and i < len(xy):
                x1, y1, x2, y2 = map(int, xy[i])
                lbl = _refine_weapon_display_label(lbl, x1, y1, x2, y2)
                self._weapon_overlay_boxes.append(((x1, y1, x2, y2), lbl, cconf))
            if cconf > best_conf:
                best_conf = cconf
                best_lbl = lbl
        if best_conf < self._weapon_conf_threshold:
            return None
        return best_conf, f"Detected: {best_lbl} (conf {best_conf:.2f})"

    def get_ppe_status(self) -> dict:
        labels = [self._ppe_names[k] for k in sorted(self._ppe_names.keys())] if self._ppe_names else []
        return {
            "running": bool(self.is_running),
            "ppe_enabled": bool(self._ppe_enabled),
            "model_loaded": bool(self._ppe_model is not None),
            "model_path": self._ppe_model_resolved_path or PPE_MODEL_PATH,
            "aux_model_loaded": bool(self._ppe_aux_model is not None),
            "aux_model_path": self._ppe_aux_model_resolved_path or PPE_AUX_MODEL_PATH,
            "required_items": sorted(self._ppe_items_required),
            "confidence_threshold": float(self._ppe_conf_threshold),
            "model_classes": labels + ([self._ppe_aux_names[k] for k in sorted(self._ppe_aux_names.keys())] if self._ppe_aux_names else []),
        }

    def get_weapon_status(self) -> dict:
        labels = [self._weapon_names[k] for k in sorted(self._weapon_names.keys())] if self._weapon_names else []
        if self._weapon_use_coco_knife:
            labels = [f"{self._weapon_coco_names.get(k, k)} (COCO fallback)" for k in sorted(self._weapon_coco_names.keys())]
        filt = "all" if WEAPON_MATCH_ALL_CLASSES else list(WEAPON_ALLOWED_CLASS_NAMES)
        path_disp = self._weapon_model_resolved_path or WEAPON_MODEL_PATH or "(not configured)"
        if self._weapon_use_coco_knife:
            path_disp = f"COCO knife fallback ({PERSON_DETECT_MODEL})"
        return {
            "running": bool(self.is_running),
            "weapon_enabled": bool(self._weapon_enabled),
            "model_loaded": bool(self._weapon_model is not None or self._weapon_use_coco_knife),
            "model_path": path_disp,
            "confidence_threshold": float(self._weapon_conf_threshold),
            "model_classes": labels,
            "class_filter": filt,
        }

    def get_fire_status(self) -> dict:
        names = []
        if self._fire_model is not None:
            raw = getattr(self._fire_model, "names", None)
            if isinstance(raw, dict):
                names = [str(raw[k]) for k in sorted(raw.keys(), key=lambda x: int(x))]
            elif isinstance(raw, list):
                names = [str(n) for n in raw]
        return {
            "running": bool(self.is_running),
            "fire_enabled": bool(self._fire_enabled),
            "backend": self._fire_backend,
            "model_loaded": bool(self._fire_model is not None),
            "model_path": self._fire_model_resolved_path or YOLO_MODEL_PATH,
            "confidence_threshold": float(self._fire_conf_threshold),
            "consecutive_frames_required": int(FIRE_CONSECUTIVE_FRAMES),
            "allowed_class_names": list(FIRE_ALLOWED_CLASS_NAMES),
            "matched_class_ids": sorted(self._fire_class_ids) if self._fire_class_ids else [],
            "model_classes": names,
            "hsv_fallback": self._fire_model is None,
            "yolo_predict_conf": float(min(self._fire_conf_threshold, FIRE_YOLO_PREDICT_CONF)),
            "hsv_with_yolo": bool(FIRE_USE_HSV_WITH_YOLO),
        }

    def get_fall_status(self) -> dict:
        pose_path = str(POSE_LANDMARKER_MODEL_PATH.resolve())
        pose_file = POSE_LANDMARKER_MODEL_PATH.is_file()
        yolo_pose_path = self._pose_yolo_resolved_path or POSE_YOLO_MODEL
        return {
            "running": bool(self.is_running),
            "fall_enabled": bool(self._fall_enabled),
            "pose_backend": self._pose_backend or "person_bbox_only",
            "pose_loaded": bool(
                self._pose is not None
                or self._pose_legacy is not None
                or self._pose_yolo is not None
            ),
            "pose_model_path": yolo_pose_path if self._pose_yolo else pose_path,
            "pose_model_on_disk": bool(self._pose_yolo) or pose_file,
            "yolo_pose_model": yolo_pose_path,
            "person_model_loaded": bool(self._person_model is not None),
            "person_model_path": PERSON_DETECT_MODEL,
            "consecutive_frames_required": int(self._fall_consecutive_required),
            "infer_every_n_frames": int(INFER_EVERY_N_FRAMES),
            "mediapipe_available": bool(_MP_AVAILABLE),
            "python_version": sys.version.split()[0],
            "pose_backend_preference": POSE_BACKEND_PREF,
        }

    def _detect_fire_yolo(self, frame: np.ndarray) -> Optional[float]:
        if not self._fire_model:
            return None
        predict_conf = min(self._fire_conf_threshold, FIRE_YOLO_PREDICT_CONF)
        res = self._fire_model.predict(
            frame,
            conf=predict_conf,
            verbose=False,
            imgsz=FIRE_YOLO_IMGSZ,
        )
        if not res or not res[0].boxes or len(res[0].boxes) == 0:
            return None
        boxes = res[0].boxes
        confs = boxes.conf.cpu().numpy() if getattr(boxes, "conf", None) is not None else None
        cls = boxes.cls.cpu().numpy() if getattr(boxes, "cls", None) is not None else None
        xy = boxes.xyxy.cpu().numpy() if getattr(boxes, "xyxy", None) is not None else None
        h, w = frame.shape[:2]
        best = 0.0
        for i in range(len(boxes)):
            if cls is not None and self._fire_class_ids:
                try:
                    c = int(cls[i])
                except Exception:
                    continue
                if c not in self._fire_class_ids:
                    continue
            cconf = float(confs[i]) if confs is not None and i < len(confs) else 0.0
            if xy is not None and i < len(xy):
                x1, y1, x2, y2 = map(float, xy[i])
                area_norm = max(0.0, (x2 - x1) * (y2 - y1)) / float(max(1.0, w * h))
                if area_norm < FIRE_MIN_AREA_NORM:
                    continue
                self._fire_overlay_boxes.append(((int(x1), int(y1), int(x2), int(y2)), cconf))
            if cconf > best:
                best = cconf
        if best >= self._fire_conf_threshold:
            return best
        return None

    def _detect_fire(self, frame):
        self._fire_overlay_boxes = []
        yolo_conf = self._detect_fire_yolo(frame) if self._fire_model else None
        if yolo_conf is not None:
            return yolo_conf
        if self._fire_model is not None and not FIRE_USE_HSV_WITH_YOLO:
            return None
        hsv_conf = self._detect_fire_hsv(frame)
        if hsv_conf is not None and hsv_conf >= self._fire_conf_threshold:
            logger.debug(
                "Fire HSV-only: conf=%.3f threshold=%.3f overlays=%d",
                hsv_conf,
                self._fire_conf_threshold,
                len(self._fire_overlay_boxes),
            )
            return hsv_conf
        return None

    def _detect_fire_hsv(self, frame: np.ndarray) -> Optional[float]:
        """
        Lightweight fallback when fire model is unavailable.
        Detects sustained bright orange/red regions and returns pseudo-confidence.
        """
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            # Fire is usually bright and saturated. Include yellow/orange flames as well as red tones.
            # Orange/red flames (saturated fire)
            lower1 = np.array([0, 100, 120], dtype=np.uint8)
            upper1 = np.array([40, 255, 255], dtype=np.uint8)
            lower2 = np.array([165, 100, 120], dtype=np.uint8)
            upper2 = np.array([180, 255, 255], dtype=np.uint8)
            mask_warm = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
            warm_pixels = int(np.count_nonzero(mask_warm))
            if warm_pixels < 80:
                return None

            # Broadcast / UI blues (e.g. station logos) — not fire.
            blue_mask = cv2.inRange(hsv, np.array([90, 70, 50]), np.array([135, 255, 255]))
            blue_frac = float(np.count_nonzero(blue_mask)) / float(mask_warm.size + 1e-9)
            if blue_frac > FIRE_HSV_MAX_BLUE_FRAC:
                return None

            # Flame cores can be bright/low-S, but only count them when tied to warm regions.
            lower_bright = np.array([5, 0, 210], dtype=np.uint8)
            upper_bright = np.array([40, 85, 255], dtype=np.uint8)
            mask_bright = cv2.inRange(hsv, lower_bright, upper_bright)
            kernel = np.ones((3, 3), np.uint8)
            mask_warm_d = cv2.dilate(mask_warm, kernel, iterations=2)
            mask_bright_near_warm = mask_bright & mask_warm_d
            mask = mask_warm | mask_bright_near_warm

            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
            mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel, iterations=1)

            total_mask = int(np.count_nonzero(mask))
            if total_mask < 80:
                return None
            warm_frac = warm_pixels / float(total_mask + 1e-9)
            if warm_frac < FIRE_HSV_MIN_WARM_FRAC:
                return None

            area_ratio = float(total_mask) / float(mask.size + 1e-9)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None
            max_area = max((cv2.contourArea(c) for c in contours), default=0.0)
            frame_area = float(frame.shape[0] * frame.shape[1] + 1e-9)
            max_blob_ratio = max_area / frame_area
            if area_ratio < 0.004 or max_blob_ratio < 0.0012:
                return None
            values = hsv[:, :, 2][mask > 0]
            if values.size == 0:
                return None
            average_value = float(np.mean(values))
            if average_value < 155:
                return None
            raw_conf = 0.35 + max_blob_ratio * 10.0 + warm_frac * 0.25 + (average_value - 160) / 200.0
            conf = round(float(min(FIRE_HSV_MAX_CONF, raw_conf)), 2)
            largest = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest)
            self._fire_overlay_boxes = [((x, y, x + w, y + h), conf)]
            logger.debug(
                "Fire HSV: conf=%s warm_frac=%.3f blue_frac=%.3f area_ratio=%.4f",
                conf,
                warm_frac,
                blue_frac,
                area_ratio,
            )
            return conf
        except Exception as exc:
            logger.debug("Fire HSV detection failed: %s", exc)
            return None

    def _draw_fall_pose_overlay(self, frame: np.ndarray) -> None:
        """Draw shoulder–hip torso line so fall monitoring is visible on the preview (not a configurable ROI)."""
        if not FALL_DRAW_POSE_OVERLAY:
            return
        lm = self._last_pose_landmarks
        if not lm:
            return
        try:
            n = len(lm)
        except TypeError:
            return
        h, w = frame.shape[:2]
        j = self._pose_joints

        def vis_pt(key: str):
            i = j.get(key, -1)
            if i < 0 or i >= n:
                return None
            p = lm[i]
            v = getattr(p, "visibility", 0.0)
            if v < 0.5:
                return None
            return int(p.x * w), int(p.y * h)

        l_sh, r_sh = vis_pt("l_sh"), vis_pt("r_sh")
        l_hp, r_hp = vis_pt("l_hp"), vis_pt("r_hp")
        pts = [p for p in (l_sh, r_sh, l_hp, r_hp) if p is not None]
        if len(pts) < 2:
            return
        if l_sh and r_sh:
            cv2.line(frame, l_sh, r_sh, (0, 220, 255), 2, lineType=cv2.LINE_AA)
        if l_hp and r_hp:
            cv2.line(frame, l_hp, r_hp, (0, 200, 255), 2, lineType=cv2.LINE_AA)
        if l_sh and r_sh and l_hp and r_hp:
            sm = ((l_sh[0] + r_sh[0]) // 2, (l_sh[1] + r_sh[1]) // 2)
            hm = ((l_hp[0] + r_hp[0]) // 2, (l_hp[1] + r_hp[1]) // 2)
            cv2.line(frame, sm, hm, (0, 255, 200), 3, lineType=cv2.LINE_AA)
        cv2.putText(
            frame,
            "Fall: torso (pose)",
            (10, max(24, h - 16)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (220, 230, 240),
            1,
            lineType=cv2.LINE_AA,
        )

    def _update_pose_landmarks_yolo(self, frame: np.ndarray) -> None:
        if self._pose_yolo is None:
            return
        try:
            res = self._pose_yolo.predict(
                frame,
                conf=POSE_YOLO_CONF,
                verbose=False,
                imgsz=POSE_YOLO_IMGSZ,
            )
            if not res or res[0].keypoints is None:
                self._last_pose_landmarks = None
                return
            kobj = res[0].keypoints
            if kobj.xy is None or len(kobj.xy) == 0:
                self._last_pose_landmarks = None
                return
            h, w = frame.shape[:2]
            xy = kobj.xy.cpu().numpy()
            xyn = kobj.xyn.cpu().numpy() if getattr(kobj, "xyn", None) is not None else None
            kconf = kobj.conf.cpu().numpy() if getattr(kobj, "conf", None) is not None else None
            best_i = 0
            best_score = -1.0
            for i in range(len(xy)):
                score = float(np.mean(kconf[i])) if kconf is not None and i < len(kconf) else 1.0
                if score > best_score:
                    best_score = score
                    best_i = i
            landmarks: List[_NormLandmark] = []
            if xyn is not None and best_i < len(xyn):
                for j in range(len(xyn[best_i])):
                    x, y = float(xyn[best_i][j][0]), float(xyn[best_i][j][1])
                    vis = float(kconf[best_i][j]) if kconf is not None else 1.0
                    landmarks.append(_NormLandmark(x, y, vis))
            else:
                row = xy[best_i]
                for j in range(len(row)):
                    px, py = float(row[j][0]), float(row[j][1])
                    landmarks.append(_NormLandmark(px / max(1.0, w), py / max(1.0, h), 1.0))
            self._last_pose_landmarks = landmarks if landmarks else None
        except Exception as exc:
            logger.debug("YOLO pose update failed: %s", exc)
            self._last_pose_landmarks = None

    def _update_pose_landmarks(self, frame: np.ndarray) -> None:
        """Run pose estimation and cache landmarks for overlay + fall logic."""
        if self._pose_yolo is not None:
            self._update_pose_landmarks_yolo(frame)
            return
        if self._pose is not None and _Image is not None and _ImageFormat is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = _Image(_ImageFormat.SRGB, rgb)
                self._pose_ts_ms += 33
                res = self._pose.detect_for_video(mp_image, self._pose_ts_ms)
                if res.pose_landmarks:
                    self._last_pose_landmarks = res.pose_landmarks[0]
                    return
            except Exception as exc:
                logger.debug("Pose tasks update failed: %s", exc)
        if self._pose_legacy is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = self._pose_legacy.process(rgb)
                if res.pose_landmarks:
                    self._last_pose_landmarks = res.pose_landmarks.landmark
                    return
            except Exception as exc:
                logger.debug("Pose legacy update failed: %s", exc)
        self._last_pose_landmarks = None

    def _detect_fall(self, frame):
        if self._last_pose_landmarks is None:
            self._update_pose_landmarks(frame)
        lm = self._last_pose_landmarks
        if lm is None:
            return self._detect_fall_by_person_box(frame)
        h, w = frame.shape[:2]

        try:
            n = len(lm)
        except TypeError:
            self._fall_consecutive = 0
            return None

        j = self._pose_joints

        def vis_lm(key: str):
            i = j.get(key, -1)
            if i < 0 or i >= n:
                return None
            p = lm[i]
            if getattr(p, "visibility", 0.0) < 0.5:
                return None
            return p

        l_sh, r_sh = vis_lm("l_sh"), vis_lm("r_sh")
        l_hp, r_hp = vis_lm("l_hp"), vis_lm("r_hp")
        nose = vis_lm("nose")
        if not (l_sh and r_sh and l_hp and r_hp):
            self._fall_consecutive = 0
            return None

        sx = (l_sh.x + r_sh.x) * 0.5
        sy = (l_sh.y + r_sh.y) * 0.5
        hx = (l_hp.x + r_hp.x) * 0.5
        hy = (l_hp.y + r_hp.y) * 0.5
        dy = hy - sy
        dx = hx - sx
        norm = math.sqrt(dx * dx + dy * dy) + 1e-9
        verticality = abs(dy) / norm

        # Clear upright / seated: hips below shoulders with a vertical torso in image space.
        if dy >= FALL_MIN_SHOULDER_HIP_DY_NORM and verticality >= FALL_MIN_UPRIGHT_VERTICALITY:
            self._fall_consecutive = 0
            return None

        # Overhead / shallow angle: torso is short in y — if head is still above hips, treat as not fallen.
        if abs(dy) < FALL_AMBIGUOUS_DY_NORM and nose is not None and nose.y < hy - 0.015:
            self._fall_consecutive = 0
            return None

        xs = [l.x * w for l in lm if getattr(l, "visibility", 0) > 0.5]
        ys = [l.y * h for l in lm if getattr(l, "visibility", 0) > 0.5]
        if len(xs) < 5:
            self._fall_consecutive = 0
            return None
        y_span = max(ys) - min(ys)
        x_span = max(xs) - min(xs)
        if y_span <= 1e-6:
            self._fall_consecutive = 0
            return None
        aspect = x_span / y_span

        # Width-heavy bbox alone matched seated workers; require a non-upright torso and high aspect.
        if aspect <= FALL_RATIO_THRESHOLD or verticality >= (FALL_MIN_UPRIGHT_VERTICALITY + 0.12):
            self._fall_consecutive = 0
            return None

        self._fall_consecutive += 1
        if self._fall_consecutive < self._fall_consecutive_required:
            return None

        self._fall_consecutive = 0
        conf = min(0.92, 0.52 + 0.12 * min(aspect, 3.0))
        return round(conf, 2)

    def _detect_fall_by_person_box(self, frame):
        if self._person_model is None or self._person_class_id is None:
            self._fall_consecutive = 0
            return None
        try:
            res = self._person_model.predict(
                frame,
                conf=PERSON_COUNT_CONF_MIN,
                verbose=False,
                imgsz=FOOTFALL_INFER_IMGSZ,
            )
            if not res or not res[0].boxes or len(res[0].boxes) == 0:
                self._fall_consecutive = 0
                return None
            boxes = res[0].boxes
            cls = boxes.cls.cpu().numpy() if getattr(boxes, "cls", None) is not None else None
            xy = boxes.xyxy.cpu().numpy() if getattr(boxes, "xyxy", None) is not None else None
            h, w = frame.shape[:2]
            best_ratio = 0.0
            best_area = 0.0
            for i in range(len(boxes)):
                if cls is not None:
                    try:
                        c = int(cls[i])
                    except Exception:
                        continue
                    if c != self._person_class_id:
                        continue
                if xy is None or i >= len(xy):
                    continue
                x1, y1, x2, y2 = map(float, xy[i])
                width = x2 - x1
                height = y2 - y1
                if height <= 0 or width <= 0:
                    continue
                area_norm = (width * height) / float(max(1.0, w * h))
                if area_norm < 0.012:
                    continue
                ratio = width / height
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_area = area_norm
            if best_ratio <= FALL_RATIO_THRESHOLD:
                self._fall_consecutive = 0
                return None
            self._fall_consecutive += 1
            if self._fall_consecutive < self._fall_consecutive_required:
                return None
            self._fall_consecutive = 0
            conf = min(0.85, 0.45 + 0.10 * min(best_ratio, 4.0))
            return round(conf, 2)
        except Exception as exc:
            logger.debug("Person-box fall fallback failed: %s", exc)
            self._fall_consecutive = 0
            return None

    def _maybe_record_person_reid_samples(
        self,
        frame: np.ndarray,
        boxes_px: List[Tuple[float, float, float, float]],
        track_ids: List[Optional[int]],
        frame_idx: int,
    ) -> None:
        if self._organization_id is None or not boxes_px:
            return
        if frame_idx % PERSON_REID_SAMPLE_EVERY_FRAMES != 0:
            return
        from app.models import PersonSighting
        from app.person_embedding import embedding_from_bgr_crop

        now = time.time()
        h, w = frame.shape[:2]
        db = self._db_factory()
        try:
            for i, box in enumerate(boxes_px):
                tid = track_ids[i] if i < len(track_ids) else None
                if tid is None:
                    continue
                if now - self._reid_track_last_ts.get(int(tid), 0.0) < PERSON_REID_TRACK_COOLDOWN:
                    continue
                x1, y1, x2, y2 = box
                i1 = max(0, min(w - 1, int(x1)))
                j1 = max(0, min(h - 1, int(y1)))
                i2 = max(0, min(w, int(x2)))
                j2 = max(0, min(h, int(y2)))
                if i2 <= i1 + 4 or j2 <= j1 + 4:
                    continue
                crop = frame[j1:j2, i1:i2]
                emb, dom = embedding_from_bgr_crop(crop)
                if not emb:
                    continue
                rel = f"reid/cam{self.camera_id}_t{int(tid)}_{datetime.utcnow().strftime('%H%M%S')}.jpg"
                out_path = SNAPSHOT_DIR / rel
                out_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    cv2.imwrite(str(out_path), crop)
                except Exception:
                    rel = None
                row = PersonSighting(
                    organization_id=self._organization_id,
                    camera_id=self.camera_id,
                    local_track_id=int(tid),
                    snapshot_path=str(rel) if rel else None,
                    embedding=emb,
                    dominant_hue=dom,
                )
                db.add(row)
                db.commit()
                self._reid_track_last_ts[int(tid)] = now
        except Exception as exc:
            logger.debug("Person Re-ID sample failed: %s", exc)
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def _alert_cooldown_key(alert_type: object) -> str:
        if hasattr(alert_type, "value"):
            return str(alert_type.value).lower()
        return str(alert_type).lower()

    def _recent_fire_alert_in_db(self) -> bool:
        """Skip duplicate fire rows for the same camera within FIRE_ALERT_MIN_INTERVAL_SECONDS."""
        from app.models import Alert, AlertTypeEnum

        db = self._db_factory()
        try:
            since = datetime.utcnow() - timedelta(seconds=FIRE_ALERT_MIN_INTERVAL_SECONDS)
            row = (
                db.query(Alert.id)
                .filter(
                    Alert.camera_id == self.camera_id,
                    Alert.type == AlertTypeEnum.fire,
                    Alert.timestamp >= since,
                )
                .first()
            )
            return row is not None
        except Exception:
            return False
        finally:
            db.close()

    def _recent_weapon_alert_in_db(self) -> bool:
        from app.models import Alert, AlertTypeEnum

        db = self._db_factory()
        try:
            since = datetime.utcnow() - timedelta(seconds=WEAPON_ALERT_MIN_INTERVAL_SECONDS)
            row = (
                db.query(Alert.id)
                .filter(
                    Alert.camera_id == self.camera_id,
                    Alert.type == AlertTypeEnum.weapon,
                    Alert.timestamp >= since,
                )
                .first()
            )
            return row is not None
        except Exception:
            return False
        finally:
            db.close()

    def _trigger_alert(self, frame, alert_type, confidence, notes: Optional[str] = None):
        now = time.time()
        key = self._alert_cooldown_key(alert_type)
        cooldown = ALERT_COOLDOWN_SECONDS
        if key == "fire":
            cooldown = FIRE_ALERT_MIN_INTERVAL_SECONDS
            if self._recent_fire_alert_in_db():
                logger.debug("Fire alert suppressed: duplicate detected within %s seconds", cooldown)
                return
        if key == "weapon":
            cooldown = WEAPON_ALERT_MIN_INTERVAL_SECONDS
            if self._recent_weapon_alert_in_db():
                logger.debug("Weapon alert suppressed: duplicate detected within %s seconds", cooldown)
                return
        if now - self._last_alert.get(key, 0) < cooldown:
            logger.debug(
                "Alert %s suppressed by cooldown: %s remaining",
                key,
                cooldown - (now - self._last_alert.get(key, 0)),
            )
            return
        self._last_alert[key] = now
        path = self._save_snapshot(frame, alert_type)
        aid = self._save_alert_to_db(alert_type, confidence, path, notes=notes)
        conf_txt = self._format_confidence(confidence)
        if aid:
            payload = {
                "event": "alert",
                "alert_id": aid,
                "camera_id": self.camera_id,
                "camera_name": self.camera_name,
                "type": alert_type,
                "confidence": conf_txt,
                "timestamp": _utc_now_iso(),
                "snapshot_path": path,
                "notes": notes,
            }
            self._broadcast_ws(payload)

    def _save_snapshot(self, frame, alert_type):
        path = SNAPSHOT_DIR / f"cam{self.camera_id}_{alert_type}_{datetime.utcnow().strftime('%H%M%S')}.jpg"
        cv2.imwrite(str(path), frame); return str(path)

    @staticmethod
    def _format_confidence(confidence: object) -> str:
        """
        Persist confidence in a compact deterministic format compatible with DB
        column VARCHAR(10), e.g. '0.5205' or '1'.
        """
        try:
            v = float(confidence)
        except Exception:
            return str(confidence)[:10]
        txt = f"{v:.4f}".rstrip("0").rstrip(".")
        return txt[:10]

    def _save_alert_to_db(self, alert_type, confidence, snapshot_path, notes: Optional[str] = None):
        from app.models import Alert, AlertTypeEnum

        db = self._db_factory()
        aid: Optional[int] = None
        ts: Optional[datetime] = None
        type_str: str = (
            alert_type.value if hasattr(alert_type, "value") else str(alert_type)
        )
        try:
            alert = Alert(
                camera_id=self.camera_id,
                type=AlertTypeEnum(alert_type) if isinstance(alert_type, str) else alert_type,
                confidence=self._format_confidence(confidence),
                snapshot_path=snapshot_path,
                timestamp=datetime.utcnow(),
                notes=notes,
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            aid = alert.id
            ts = alert.timestamp
            try:
                from app.vlm_service import verify_alert_async

                verify_alert_async(aid, type_str, snapshot_path)
            except Exception:
                pass
        except Exception as exc:
            logger.error("Alert DB save failed (%s): %s", alert_type, exc)
            db.rollback()
        finally:
            db.close()

        if aid and ts:
            try:
                from app.notification_dispatch import schedule_alert_notifications

                schedule_alert_notifications(
                    alert_id=aid,
                    camera_id=self.camera_id,
                    camera_name=self.camera_name,
                    alert_type=type_str,
                    confidence=self._format_confidence(confidence),
                    snapshot_path=snapshot_path,
                    notes=notes,
                    timestamp_utc=ts,
                )
            except Exception as exc:
                logger.debug("Alert notification schedule failed: %s", exc)

        return aid

    def _update_camera_status(self, status):
        from app.models import Camera, CameraStatusEnum

        db = self._db_factory()
        try:
            cam = db.query(Camera).filter(Camera.id == self.camera_id).first()
            if cam:
                cam.status = CameraStatusEnum(status) if isinstance(status, str) else status
                db.commit()
        except Exception as exc:
            logger.error("Camera status update: %s", exc)
            db.rollback()
        finally:
            db.close()

class ProcessorRegistry:
    def __init__(self):
        self._processors: Dict[int, VideoProcessor] = {}
        self._lock = threading.Lock()

    def start(self, camera_id, rtsp_url, camera_name, db_factory, ws_manager, loop):
        with self._lock:
            if camera_id in self._processors and self._processors[camera_id].is_running: return False
            proc = VideoProcessor(camera_id, rtsp_url, camera_name, db_factory, ws_manager, loop)
            proc.start()
            self._processors[camera_id] = proc
            return True

    def stop(self, camera_id):
        with self._lock:
            proc = self._processors.pop(camera_id, None)
            if proc: proc.stop(); return True
        return False

    def is_running(self, camera_id):
        with self._lock:
            p = self._processors.get(camera_id)
            return bool(p and p.is_running)

    def stop_all(self):
        with self._lock:
            for p in self._processors.values():
                p.stop()
            self._processors.clear()

    def running_ids(self) -> List[int]:
        """Camera IDs whose VideoProcessor thread is still alive."""
        with self._lock:
            return [cid for cid, p in self._processors.items() if p.is_running]

    def get_preview_jpeg(self, camera_id: int) -> Optional[bytes]:
        """Latest MJPEG frame from inference (overlays included)."""
        with self._lock:
            proc = self._processors.get(camera_id)
        if not proc or not proc.is_running:
            return None
        return proc.get_preview_jpeg()

    def get_ppe_status(self, camera_id: int) -> Optional[dict]:
        with self._lock:
            proc = self._processors.get(camera_id)
        if not proc:
            return None
        return proc.get_ppe_status()

    def get_weapon_status(self, camera_id: int) -> Optional[dict]:
        with self._lock:
            proc = self._processors.get(camera_id)
        if not proc:
            return None
        return proc.get_weapon_status()

    def get_fire_status(self, camera_id: int) -> Optional[dict]:
        with self._lock:
            proc = self._processors.get(camera_id)
        if not proc:
            return None
        return proc.get_fire_status()

    def get_fall_status(self, camera_id: int) -> Optional[dict]:
        with self._lock:
            proc = self._processors.get(camera_id)
        if not proc:
            return None
        return proc.get_fall_status()

    def refresh_settings(self, camera_id: int) -> bool:
        with self._lock:
            proc = self._processors.get(camera_id)
        if not proc or not proc.is_running:
            return False
        try:
            proc._refresh_camera_analytics_settings()  # intentional internal call for live config updates
            return True
        except Exception:
            return False

registry = ProcessorRegistry()