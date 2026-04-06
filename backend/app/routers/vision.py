"""
Cross-camera person appearance search (Re-ID lite) using stored histogram embeddings.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Camera, PersonSighting, User
from app.person_embedding import cosine_similarity
from app.tenancy import is_super_admin

router = APIRouter(prefix="/vision", tags=["Vision & Re-ID"])


def _hue_band_from_query(q: str) -> Optional[Tuple[float, float]]:
    """Map simple color words in *q* to OpenCV H ranges (0–180). Returns first band or None."""
    s = q.lower()
    bands = {
        "red": [(0, 15), (165, 180)],
        "orange": [(8, 28)],
        "yellow": [(22, 38)],
        "green": [(38, 85)],
        "blue": [(85, 130)],
        "purple": [(130, 165)],
        "white": [(0, 180)],
        "black": [(0, 180)],
    }
    for word, ranges in bands.items():
        if word in s:
            if word in ("white", "black"):
                return None
            return ranges[0]
    return None


class PersonSightingOut(BaseModel):
    id: int
    organization_id: int
    camera_id: int
    camera_name: Optional[str] = None
    local_track_id: Optional[int] = None
    timestamp: datetime
    snapshot_path: Optional[str] = None
    embedding: List[float] = Field(default_factory=list)
    dominant_hue: Optional[float] = None
    similarity: Optional[float] = None

    model_config = {"from_attributes": True}


class PersonTimelineResponse(BaseModel):
    query: str
    reference_sighting_id: Optional[int] = None
    matches: List[PersonSightingOut]


def _org_scope(user: User, organization_id: Optional[int]) -> int:
    if is_super_admin(user):
        if organization_id is None:
            raise HTTPException(status_code=422, detail="organization_id is required for platform admin.")
        return organization_id
    if user.organization_id is None:
        raise HTTPException(status_code=403, detail="No organization context.")
    if organization_id is not None and organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Cannot query another organization.")
    return user.organization_id


@router.get("/person-timeline", response_model=PersonTimelineResponse)
def person_timeline(
    q: str = Query(..., min_length=1, description='e.g. "person in red shirt"'),
    organization_id: Optional[int] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    min_similarity: float = Query(0.72, ge=0.0, le=1.0),
    reference_sighting_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Find correlated person sightings across cameras using embedding similarity.
    Optional reference_sighting_id uses that row's embedding as the query vector.
    """
    oid = _org_scope(current_user, organization_id)
    since = datetime.utcnow() - timedelta(hours=hours)

    ref_vec: Optional[List[float]] = None
    if reference_sighting_id is not None:
        ref = (
            db.query(PersonSighting)
            .filter(
                PersonSighting.id == reference_sighting_id,
                PersonSighting.organization_id == oid,
            )
            .first()
        )
        if not ref:
            raise HTTPException(status_code=404, detail="Reference sighting not found.")
        ref_vec = list(ref.embedding or [])

    rows = (
        db.query(PersonSighting)
        .filter(
            PersonSighting.organization_id == oid,
            PersonSighting.timestamp >= since,
        )
        .order_by(PersonSighting.timestamp.desc())
        .limit(2000)
        .all()
    )

    hue_band = _hue_band_from_query(q)
    out: List[PersonSighting] = []
    for r in rows:
        if hue_band and r.dominant_hue is not None:
            lo, hi = hue_band
            if not (lo <= r.dominant_hue <= hi):
                # Do not drop the reference sighting when color words don't match its hue.
                if reference_sighting_id is None or r.id != reference_sighting_id:
                    continue
        if ref_vec:
            sim = cosine_similarity(ref_vec, list(r.embedding or []))
            if sim < min_similarity:
                continue
        else:
            # No reference: filter by hue band only; rank by recency
            if hue_band is None and "person" not in q.lower():
                pass
        out.append(r)

    cams = {c.id: c.name for c in db.query(Camera).filter(Camera.organization_id == oid).all()}
    payload_clean: List[PersonSightingOut] = []
    for r in out[:200]:
        sim = None
        if ref_vec:
            sim = cosine_similarity(ref_vec, list(r.embedding or []))
        emb = [float(x) for x in (r.embedding or [])][:32]
        payload_clean.append(
            PersonSightingOut(
                id=r.id,
                organization_id=r.organization_id,
                camera_id=r.camera_id,
                camera_name=cams.get(r.camera_id),
                local_track_id=r.local_track_id,
                timestamp=r.timestamp,
                snapshot_path=r.snapshot_path,
                embedding=emb,
                dominant_hue=r.dominant_hue,
                similarity=sim,
            )
        )

    return PersonTimelineResponse(
        query=q,
        reference_sighting_id=reference_sighting_id,
        matches=payload_clean,
    )


@router.get("/sightings/recent", response_model=list[PersonSightingOut])
def recent_sightings(
    organization_id: Optional[int] = Query(None),
    camera_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    oid = _org_scope(current_user, organization_id)
    q = db.query(PersonSighting).filter(PersonSighting.organization_id == oid)
    if camera_id is not None:
        cam = db.query(Camera).filter(Camera.id == camera_id).first()
        if not cam or cam.organization_id != oid:
            raise HTTPException(status_code=404, detail="Camera not found.")
        q = q.filter(PersonSighting.camera_id == camera_id)
    rows = q.order_by(PersonSighting.timestamp.desc()).limit(limit).all()
    cams = {c.id: c.name for c in db.query(Camera).filter(Camera.organization_id == oid).all()}
    return [
        PersonSightingOut(
            id=r.id,
            organization_id=r.organization_id,
            camera_id=r.camera_id,
            camera_name=cams.get(r.camera_id),
            local_track_id=r.local_track_id,
            timestamp=r.timestamp,
            snapshot_path=r.snapshot_path,
            embedding=list(r.embedding or [])[:32],
            dominant_hue=r.dominant_hue,
            similarity=None,
        )
        for r in rows
    ]
