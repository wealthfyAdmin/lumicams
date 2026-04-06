"""
routers/alerts.py
-----------------
Alert management endpoints.

  GET    /api/alerts/              – Paginated alert list  (Operator+)
  GET    /api/alerts/{id}          – Single alert          (Operator+)
  PATCH  /api/alerts/{id}/ack      – Acknowledge alert     (Operator+)
  DELETE /api/alerts/{id}          – Delete alert          (Admin)
  GET    /api/alerts/stats         – Counts by type        (Operator+)
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Alert, AlertTypeEnum, Camera, User
from app.schema import AlertAcknowledge, AlertOut
from app.tenancy import alerts_query_for_user, camera_accessible

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _normalize_alert_type(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s not in ("fire", "fall", "crowd", "face", "ppe", "weapon"):
        raise HTTPException(
            status_code=422,
            detail='alert_type must be one of: "Fire", "Fall", "Crowd", "Face", "PPE", "Weapon".',
        )
    return s


def _get_alert_or_404(alert_id: int, db: Session, user: User) -> Alert:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    cam = db.query(Camera).filter(Camera.id == alert.camera_id).first()
    if not cam or not camera_accessible(user, cam):
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert




@router.get("/stats")
def alert_stats(
    hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Return alert counts broken down by type for the last *hours* hours.
    Useful for dashboard stat cards.
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    scoped = alerts_query_for_user(db, _user).filter(Alert.timestamp >= since)
    rows = (
        scoped.with_entities(Alert.type, func.count(Alert.id))
        .group_by(Alert.type)
        .all()
    )
    totals = scoped.with_entities(func.count(Alert.id)).scalar()
    unacked = (
        alerts_query_for_user(db, _user)
        .filter(Alert.timestamp >= since, Alert.acknowledged == False)  # noqa: E712
        .with_entities(func.count(Alert.id))
        .scalar()
    )
    return {
        "total":        totals,
        "unacknowledged": unacked,
        "by_type":      {str(r[0].value): r[1] for r in rows},
        "since":        since.isoformat(),
    }


@router.get("/", response_model=list[AlertOut])
def list_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    camera_id: Optional[int] = None,
    alert_type: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Paginated list of alerts with optional filters.

    Query params:
      skip          – offset for pagination (default 0)
      limit         – page size (default 50, max 200)
      camera_id     – filter by camera
      alert_type    – Fire | Fall
      acknowledged  – true / false
    """
    q = alerts_query_for_user(db, _user).order_by(Alert.timestamp.desc())
    if camera_id is not None:
        q = q.filter(Alert.camera_id == camera_id)
    normalized_type = _normalize_alert_type(alert_type)
    if normalized_type is not None:
        # Compare as lowercase text to avoid enum bind casing/name mismatches.
        q = q.filter(func.lower(cast(Alert.type, String)) == normalized_type)
    if acknowledged is not None:
        q = q.filter(Alert.acknowledged == acknowledged)
    return q.offset(skip).limit(limit).all()


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_alert_or_404(alert_id, db, current_user)


@router.patch("/{alert_id}/ack", response_model=AlertOut)
def acknowledge_alert(
    alert_id: int,
    payload: AlertAcknowledge,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Mark an alert as acknowledged and optionally attach a note."""
    alert = _get_alert_or_404(alert_id, db, _user)
    alert.acknowledged = True
    if payload.notes:
        alert.notes = payload.notes
    db.commit()
    db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=204)
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Permanently delete an alert record. Requires Admin."""
    alert = _get_alert_or_404(alert_id, db, admin)
    db.delete(alert)
    db.commit()
