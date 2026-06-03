"""
Face intelligence module:
 - identity registry (whitelist / blacklist / neutral)
 - attendance views (whitelist sightings)
 - security views (blacklist sightings)
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.face_ort import get_shared_face_app
from app.models import Camera, FaceCategoryEnum, FaceIdentity, FaceSighting, User
from app.tenancy import is_super_admin
from app.schema import (
    FaceIdentityCreate,
    FaceIdentityOut,
    FaceIdentityUpdate,
    FaceSightingOut,
)

router = APIRouter(prefix="/faces", tags=["Face Intelligence"])
logger = logging.getLogger(__name__)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = Path("snapshots")
FACE_IMG_DIR = SNAPSHOT_DIR / "faces"
FACE_IMG_DIR.mkdir(parents=True, exist_ok=True)


def _identity_has_vectors(obj: FaceIdentity) -> bool:
    el = obj.embeddings
    return (
        isinstance(el, list)
        and len(el) > 0
        and any(isinstance(x, list) and len(x) > 0 for x in el)
    )


def _resolve_stored_face_path(rel: str) -> Optional[Path]:
    rel = rel.replace("\\", "/").lstrip("/")
    for base in (_BACKEND_ROOT, Path.cwd()):
        p = (base / rel).resolve()
        if p.is_file():
            return p
    return None


def _extract_embeddings_from_frame(frame: np.ndarray, app: Any) -> List[List[float]]:
    faces = app.get(frame)
    if not faces:
        raise HTTPException(status_code=422, detail="No face detected in image.")
    if len(faces) > 1:
        raise HTTPException(status_code=422, detail="Multiple faces detected. Use one clear face per photo.")
    emb = getattr(faces[0], "normed_embedding", None)
    if emb is None:
        emb = getattr(faces[0], "embedding", None)
    if emb is None:
        raise HTTPException(status_code=500, detail="Face embedding extraction failed.")
    return [np.asarray(emb, dtype=np.float32).reshape(-1).tolist()]

@router.get("/status")
def face_module_status(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    app = get_shared_face_app()
    engine = getattr(app, "_aegis_engine", None) if app is not None else "none"
    pipeline = os.getenv("FACE_RECOGNITION_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    active = (
        db.query(FaceIdentity).filter(FaceIdentity.is_active == True)  # noqa: E712
        .all()
    )
    total = len(active)
    with_emb = sum(
        1
        for r in active
        if isinstance(r.embeddings, list)
        and len(r.embeddings) > 0
        and any(isinstance(x, list) and len(x) > 0 for x in r.embeddings)
    )
    return {
        "insightface_available": bool(app is not None),
        "enroll_mode": "embedding" if app is not None else "image_only",
        "face_engine": engine,
        "camera_pipeline_enabled": pipeline,
        "active_identities": total,
        "identities_with_embeddings": with_emb,
    }


def _face_org_id_for_write(admin: User, payload_org: Optional[int]) -> Optional[int]:
    if is_super_admin(admin):
        return payload_org
    if admin.organization_id is None:
        raise HTTPException(status_code=400, detail="Not assigned to an organization.")
    return admin.organization_id


def _identity_or_404(identity_id: int, db: Session, user: User) -> FaceIdentity:
    obj = db.query(FaceIdentity).filter(FaceIdentity.id == identity_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Face identity not found.")
    if not is_super_admin(user):
        if user.organization_id is None or obj.organization_id != user.organization_id:
            raise HTTPException(status_code=404, detail="Face identity not found.")
    return obj


def _sightings_query(db: Session, user: User):
    q = db.query(FaceSighting)
    if is_super_admin(user):
        return q
    if user.organization_id is None:
        return q.filter(FaceSighting.id == -1)
    cam_ids = [
        r.id
        for r in db.query(Camera.id).filter(Camera.organization_id == user.organization_id).all()
    ]
    if not cam_ids:
        return q.filter(FaceSighting.id == -1)
    return q.filter(FaceSighting.camera_id.in_(cam_ids))


@router.get("/identities", response_model=list[FaceIdentityOut])
def list_identities(
    category: Optional[FaceCategoryEnum] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    q = db.query(FaceIdentity).order_by(FaceIdentity.created_at.desc())
    if not is_super_admin(_user):
        if _user.organization_id is None:
            q = q.filter(FaceIdentity.id == -1)
        else:
            q = q.filter(FaceIdentity.organization_id == _user.organization_id)
    if category is not None:
        q = q.filter(FaceIdentity.category == category)
    if active_only:
        q = q.filter(FaceIdentity.is_active == True)  # noqa: E712
    return q.all()


@router.post("/identities", response_model=FaceIdentityOut)
def create_identity(
    payload: FaceIdentityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    oid = _face_org_id_for_write(_admin, payload.organization_id)
    obj = FaceIdentity(
        organization_id=oid,
        name=payload.name.strip(),
        employee_code=(payload.employee_code or "").strip() or None,
        category=payload.category,
        embeddings=payload.embeddings or [],
        is_active=bool(payload.is_active),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/identities/enroll-image", response_model=FaceIdentityOut)
async def enroll_identity_image(
    name: str = Form(...),
    category: FaceCategoryEnum = Form(FaceCategoryEnum.neutral),
    employee_code: Optional[str] = Form(None),
    organization_id: Optional[int] = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image file.")

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = "".join(ch for ch in name.strip().lower().replace(" ", "_") if ch.isalnum() or ch in ("_", "-"))[:40] or "person"
    ext = Path(image.filename or "face.jpg").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    out_name = f"{safe_name}_{ts}{ext}"
    out_path = FACE_IMG_DIR / out_name
    if ext in (".jpg", ".jpeg"):
        cv2.imwrite(str(out_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    else:
        cv2.imwrite(str(out_path), frame)

    rel_path = f"snapshots/faces/{out_name}"
    embeddings: list[list[float]] = []
    app = get_shared_face_app()
    if app is not None:
        embeddings = _extract_embeddings_from_frame(frame, app)

    oid = _face_org_id_for_write(_admin, organization_id)
    obj = FaceIdentity(
        organization_id=oid,
        name=name.strip(),
        employee_code=(employee_code or "").strip() or None,
        face_image_path=rel_path,
        category=category,
        embeddings=embeddings,
        is_active=True,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/identities/{identity_id}/extract-embedding", response_model=FaceIdentityOut)
def extract_embedding_from_saved_photo(
    identity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Rebuild vectors from the stored enrollment image (fixes identities created without embeddings)."""
    obj = _identity_or_404(identity_id, db, _admin)
    if not obj.face_image_path or not str(obj.face_image_path).strip():
        raise HTTPException(status_code=400, detail="No face photo path stored. Upload a new image via enroll.")
    path = _resolve_stored_face_path(str(obj.face_image_path))
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Image file not found on disk for this identity. Re-enroll with a new photo.",
        )
    frame = cv2.imread(str(path))
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode stored image file.")
    app = get_shared_face_app()
    if app is None:
        raise HTTPException(status_code=503, detail="Face recognition backend is not available.")
    obj.embeddings = _extract_embeddings_from_frame(frame, app)
    db.commit()
    db.refresh(obj)
    logger.info("Rebuilt embeddings for face identity id=%s from %s", identity_id, path)
    return obj


@router.post("/identities/repair-missing-embeddings")
def repair_missing_embeddings(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """For every active identity with a saved photo but empty embeddings, extract vectors."""
    app = get_shared_face_app()
    if app is None:
        raise HTTPException(status_code=503, detail="Face recognition backend is not available.")
    q = db.query(FaceIdentity).filter(FaceIdentity.is_active == True)  # noqa: E712
    if not is_super_admin(_admin) and _admin.organization_id is not None:
        q = q.filter(FaceIdentity.organization_id == _admin.organization_id)
    rows = q.all()
    repaired: List[dict] = []
    failed: List[dict] = []
    for obj in rows:
        if _identity_has_vectors(obj):
            continue
        if not obj.face_image_path or not str(obj.face_image_path).strip():
            failed.append({"identity_id": obj.id, "name": obj.name, "reason": "no_stored_photo"})
            continue
        path = _resolve_stored_face_path(str(obj.face_image_path))
        if path is None:
            failed.append({"identity_id": obj.id, "name": obj.name, "reason": "file_not_found"})
            continue
        frame = cv2.imread(str(path))
        if frame is None:
            failed.append({"identity_id": obj.id, "name": obj.name, "reason": "decode_error"})
            continue
        try:
            obj.embeddings = _extract_embeddings_from_frame(frame, app)
            repaired.append({"identity_id": obj.id, "name": obj.name})
        except HTTPException as exc:
            detail = exc.detail
            reason = detail if isinstance(detail, str) else str(detail)
            failed.append({"identity_id": obj.id, "name": obj.name, "reason": reason})
    db.commit()
    return {"repaired": repaired, "failed": failed, "repaired_count": len(repaired), "failed_count": len(failed)}


@router.patch("/identities/{identity_id}", response_model=FaceIdentityOut)
def update_identity(
    identity_id: int,
    payload: FaceIdentityUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    obj = _identity_or_404(identity_id, db, _admin)
    if payload.name is not None:
        obj.name = payload.name.strip()
    if payload.employee_code is not None:
        obj.employee_code = payload.employee_code.strip() or None
    if payload.category is not None:
        obj.category = payload.category
    if payload.embeddings is not None:
        obj.embeddings = payload.embeddings
    if payload.is_active is not None:
        obj.is_active = bool(payload.is_active)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/identities/{identity_id}", status_code=204)
def delete_identity(
    identity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    obj = _identity_or_404(identity_id, db, _admin)
    db.delete(obj)
    db.commit()


@router.get("/sightings", response_model=list[FaceSightingOut])
def list_sightings(
    hours: int = Query(24, ge=1, le=720),
    camera_id: Optional[int] = None,
    category: Optional[FaceCategoryEnum] = None,
    event_type: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    q = _sightings_query(db, _user).filter(FaceSighting.timestamp >= since)
    if camera_id is not None:
        q = q.filter(FaceSighting.camera_id == camera_id)
    if category is not None:
        q = q.filter(FaceSighting.category == category)
    if event_type:
        q = q.filter(FaceSighting.event_type == event_type.strip().lower())
    rows = q.order_by(FaceSighting.timestamp.desc()).limit(limit).all()
    return [
        FaceSightingOut(
            id=r.id,
            camera_id=r.camera_id,
            identity_id=r.identity_id,
            identity_name=(r.identity.name if r.identity else None),
            category=r.category,
            confidence=r.confidence,
            event_type=r.event_type,
            timestamp=r.timestamp,
            snapshot_path=r.snapshot_path,
            notes=r.notes,
        )
        for r in rows
    ]


@router.get("/attendance", response_model=list[FaceSightingOut])
def whitelist_attendance(
    hours: int = Query(24, ge=1, le=720),
    camera_id: Optional[int] = None,
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    q = _sightings_query(db, _user).filter(
        FaceSighting.timestamp >= since,
        FaceSighting.category == FaceCategoryEnum.whitelist,
        FaceSighting.event_type == "attendance",
    )
    if camera_id is not None:
        q = q.filter(FaceSighting.camera_id == camera_id)
    rows = q.order_by(FaceSighting.timestamp.desc()).limit(limit).all()
    return [
        FaceSightingOut(
            id=r.id,
            camera_id=r.camera_id,
            identity_id=r.identity_id,
            identity_name=(r.identity.name if r.identity else None),
            category=r.category,
            confidence=r.confidence,
            event_type=r.event_type,
            timestamp=r.timestamp,
            snapshot_path=r.snapshot_path,
            notes=r.notes,
        )
        for r in rows
    ]

