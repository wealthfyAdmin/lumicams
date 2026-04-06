import base64
import logging
import os
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_bearer_or_query, require_admin
from app.database import SessionLocal, get_db
from app.inference import registry
from app.models import Camera, CameraStatusEnum, Organization, User
from app.schema import CameraCreate, CameraOut, CameraUpdate, ProcessorStatusOut
from app.tenancy import camera_accessible, cameras_query_for_user, is_super_admin
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["Cameras"])

# Tiny valid JPEG (1×1 px) if OpenCV text rendering fails
_FALLBACK_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDABALDA4MChAODQ4SERATGCgaGBYWGDEjJR0oOjM9PDkzODdASFxOQERXRTc4UG1RV19iZ2hnPk1xeXBkeFxlZ2P/2wBDAQICAgQDAwUFBQUFBQYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBv/EABkAAAMBAQEAAAAAAAAAAAAAAAACAAMEBf/EAB4QAAEEAgMBAAAAAAAAAAAAAAIAAwEEBQYSISET/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwDcA//Z"
)


def _paused_placeholder_jpeg() -> bytes:
    """Single JPEG frame shown in MJPEG when inference is stopped (avoids 409 + broken <img>)."""
    try:
        import cv2
        import numpy as np

        h, w = 360, 640
        img = np.full((h, w, 3), (32, 28, 20), dtype=np.uint8)
        cv2.putText(
            img,
            "PROCESSOR PAUSED",
            (140, h // 2 - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (120, 200, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            img,
            "Start camera to view live AI overlay",
            (48, h // 2 + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (140, 160, 190),
            1,
            cv2.LINE_AA,
        )
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        if ok:
            return buf.tobytes()
    except Exception as exc:
        logger.debug("Paused placeholder (full frame) failed: %s", exc)
    try:
        import cv2
        import numpy as np

        img = np.zeros((64, 64, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if buf is not None:
            return buf.tobytes()
    except Exception as exc:
        logger.debug("Paused placeholder (tiny) failed: %s", exc)
    return _FALLBACK_JPEG


def _get_camera_or_404(camera_id: int, db: Session, user: User) -> Camera:
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam or not camera_accessible(user, cam):
        raise HTTPException(status_code=404, detail="Camera not found.")
    return cam

# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("/", response_model=CameraOut, status_code=201)
def create_camera(
    payload: CameraCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Register a new camera. Requires Admin role."""
    if is_super_admin(current_user):
        oid = payload.organization_id
        if oid is None:
            raise HTTPException(
                status_code=422,
                detail="organization_id is required when creating a camera as platform admin.",
            )
        org = db.query(Organization).filter(Organization.id == oid).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")
    else:
        oid = current_user.organization_id
        if oid is None:
            raise HTTPException(status_code=400, detail="Your account is not linked to an organization.")
    cam = Camera(
        name=payload.name,
        rtsp_url=payload.rtsp_url,
        location=payload.location,
        user_id=current_user.id,
        organization_id=oid,
        person_detection_enabled=payload.person_detection_enabled,
        crowd_roi_enabled=payload.crowd_roi_enabled,
        crowd_roi_x1=payload.crowd_roi_x1,
        crowd_roi_y1=payload.crowd_roi_y1,
        crowd_roi_x2=payload.crowd_roi_x2,
        crowd_roi_y2=payload.crowd_roi_y2,
        crowd_limit_enabled=payload.crowd_limit_enabled,
        crowd_max_people=payload.crowd_max_people,
        fire_enabled=payload.fire_enabled,
        fire_min_confidence=payload.fire_min_confidence,
        fall_enabled=payload.fall_enabled,
        fall_consecutive_frames=payload.fall_consecutive_frames,
        face_enabled=payload.face_enabled,
        face_min_similarity=payload.face_min_similarity,
        ppe_enabled=payload.ppe_enabled,
        ppe_items=payload.ppe_items,
        ppe_confidence=payload.ppe_confidence,
        weapon_enabled=payload.weapon_enabled,
        weapon_confidence=payload.weapon_confidence,
        footfall_enabled=payload.footfall_enabled,
        footfall_mode=payload.footfall_mode,
        footfall_line_y=payload.footfall_line_y,
        heatmap_enabled=payload.heatmap_enabled,
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam

@router.get("/", response_model=list[CameraOut])
def list_cameras(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return cameras visible to the current user."""
    return cameras_query_for_user(db, current_user).order_by(Camera.id.asc()).all()

@router.get("/{camera_id}", response_model=CameraOut)
def get_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_camera_or_404(camera_id, db, current_user)

@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(
    camera_id: int,
    payload: CameraUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    cam = _get_camera_or_404(camera_id, db, admin)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cam, field, value)
    db.commit()
    db.refresh(cam)
    # Apply settings immediately if processor is live (no wait for periodic refresh).
    registry.refresh_settings(camera_id)
    return cam

@router.delete("/{camera_id}", status_code=204)
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    cam = _get_camera_or_404(camera_id, db, admin)
    registry.stop(camera_id)
    db.delete(cam)
    db.commit()

# ---------------------------------------------------------------------------
# Processor control
# ---------------------------------------------------------------------------

@router.post("/{camera_id}/start", response_model=ProcessorStatusOut)
async def start_processor(
    camera_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    cam = _get_camera_or_404(camera_id, db, admin)

    # Path Check: If it's a file, ensure it exists before starting AI
    if not cam.rtsp_url.startswith(("rtsp://", "rtmp://", "http://", "https://")):
        if not os.path.exists(cam.rtsp_url):
            raise HTTPException(
                status_code=400, 
                detail=f"Test video file not found: {cam.rtsp_url}. Please check backend folder."
            )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    started = registry.start(
        camera_id=cam.id,
        rtsp_url=cam.rtsp_url,
        camera_name=cam.name,
        db_factory=SessionLocal,
        ws_manager=ws_manager,
        loop=loop,
    )

    if not started:
        return ProcessorStatusOut(
            camera_id=camera_id,
            running=True,
            message="Processor is already running.",
        )

    return ProcessorStatusOut(
        camera_id=camera_id,
        running=True,
        message="Processor started successfully.",
    )

@router.post("/{camera_id}/stop", response_model=ProcessorStatusOut)
def stop_processor(
    camera_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    cam = _get_camera_or_404(camera_id, db, admin)
    stopped = registry.stop(camera_id)
    # Force DB status immediately so UI reflects paused state without delay.
    cam.status = CameraStatusEnum.inactive
    db.commit()
    return ProcessorStatusOut(
        camera_id=camera_id,
        running=False,
        message="Processor stopped." if stopped else "Processor was not running.",
    )

@router.get("/{camera_id}/status", response_model=ProcessorStatusOut)
def processor_status(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_camera_or_404(camera_id, db, current_user)
    running = registry.is_running(camera_id)
    return ProcessorStatusOut(
        camera_id=camera_id,
        running=running,
        message="Running" if running else "Stopped",
    )


@router.get("/{camera_id}/ppe-status")
def ppe_status(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cam = _get_camera_or_404(camera_id, db, current_user)
    proc_status = registry.get_ppe_status(camera_id)
    if proc_status is None:
        return {
            "running": False,
            "ppe_enabled": bool(getattr(cam, "ppe_enabled", False)),
            "model_loaded": False,
            "model_path": os.getenv("YOLO_PPE_MODEL", "ppe.pt"),
            "required_items": list(getattr(cam, "ppe_items", []) or []),
            "confidence_threshold": float(
                getattr(cam, "ppe_confidence", None)
                if getattr(cam, "ppe_confidence", None) is not None
                else float(os.getenv("PPE_CONF_THRESHOLD", "0.45"))
            ),
            "model_classes": [],
            "message": "Processor is not running for this camera.",
        }
    return proc_status


@router.get("/{camera_id}/weapon-status")
def weapon_status(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cam = _get_camera_or_404(camera_id, db, current_user)
    proc_status = registry.get_weapon_status(camera_id)
    if proc_status is None:
        return {
            "running": False,
            "weapon_enabled": bool(getattr(cam, "weapon_enabled", False)),
            "model_loaded": False,
            "model_path": os.getenv("YOLO_WEAPON_MODEL", "") or "(not configured)",
            "confidence_threshold": float(
                getattr(cam, "weapon_confidence", None)
                if getattr(cam, "weapon_confidence", None) is not None
                else float(os.getenv("WEAPON_CONF_THRESHOLD", "0.45"))
            ),
            "model_classes": [],
            "class_filter": [],
            "message": "Processor is not running for this camera.",
        }
    return proc_status


# ---------------------------------------------------------------------------
# Live Preview Feed (MJPEG)
# ---------------------------------------------------------------------------

@router.get("/{camera_id}/video")
def video_feed(
    camera_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_bearer_or_query),
):
    """
    MJPEG stream. When the AI processor is running, frames come from the **same**
    inference pipeline as overlays. When paused, streams a placeholder frame (200 OK)
    so browser <img> tags do not receive 409 / broken images.
    """
    _get_camera_or_404(camera_id, db, current_user)
    paused_jpeg = _paused_placeholder_jpeg()

    def generate():
        while True:
            if not registry.is_running(camera_id):
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + paused_jpeg + b"\r\n"
                )
                time.sleep(0.5)
                continue
            jpeg = registry.get_preview_jpeg(camera_id)
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
                time.sleep(1.0 / 20.0)
            else:
                time.sleep(0.04)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )