from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Alert, AlertTypeEnum, Camera, User
from app.tenancy import (
    alerts_query_for_user,
    camera_accessible,
    cameras_query_for_user,
    is_super_admin,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _bucketize_hourly(alert_rows, since: datetime):
    buckets = defaultdict(int)
    cursor = since.replace(minute=0, second=0, microsecond=0)
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    while cursor <= now:
        buckets[cursor.isoformat()] = 0
        cursor += timedelta(hours=1)

    for ts, count in alert_rows:
        k = ts.replace(minute=0, second=0, microsecond=0).isoformat()
        buckets[k] += int(count)

    return [{"hour": hour, "count": buckets[hour]} for hour in sorted(buckets.keys())]


@router.get("/overview")
def analytics_overview(
    hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    since = datetime.utcnow() - timedelta(hours=hours)

    total_cameras = cameras_query_for_user(db, _user).count()
    active_cameras = (
        cameras_query_for_user(db, _user).filter(Camera.status == "active").count()
    )

    scoped_alerts = alerts_query_for_user(db, _user).filter(Alert.timestamp >= since)
    total_alerts = scoped_alerts.count()
    unack = (
        alerts_query_for_user(db, _user)
        .filter(Alert.timestamp >= since, Alert.acknowledged == False)  # noqa: E712
        .with_entities(func.count(Alert.id))
        .scalar()
        or 0
    )

    by_type_rows = (
        db.query(Alert.type, func.count(Alert.id))
        .select_from(Alert)
        .join(Camera, Alert.camera_id == Camera.id)
        .filter(Alert.timestamp >= since)
    )
    if not is_super_admin(_user):
        if _user.organization_id is None:
            by_type_rows = by_type_rows.filter(Alert.id == -1)
        else:
            by_type_rows = by_type_rows.filter(Camera.organization_id == _user.organization_id)
    by_type_rows = by_type_rows.group_by(Alert.type).all()
    by_type = {"Fire": 0, "Fall": 0, "Crowd": 0, "Face": 0, "PPE": 0, "Weapon": 0}
    for t, c in by_type_rows:
        by_type[t.value] = int(c)

    per_q = (
        db.query(
            Camera.id,
            Camera.name,
            func.count(Alert.id).label("alert_count"),
        )
        .select_from(Camera)
        .outerjoin(Alert, Alert.camera_id == Camera.id)
        .filter((Alert.timestamp >= since) | (Alert.timestamp.is_(None)))
    )
    if not is_super_admin(_user):
        if _user.organization_id is None:
            per_q = per_q.filter(Camera.id == -1)
        else:
            per_q = per_q.filter(Camera.organization_id == _user.organization_id)
    per_camera_rows = (
        per_q.group_by(Camera.id, Camera.name)
        .order_by(func.count(Alert.id).desc(), Camera.id.asc())
        .limit(5)
        .all()
    )

    hourly_rows = (
        alerts_query_for_user(db, _user)
        .filter(Alert.timestamp >= since)
        .with_entities(Alert.timestamp, func.count(Alert.id))
        .group_by(Alert.timestamp)
        .all()
    )
    hourly = _bucketize_hourly(hourly_rows, since)

    fire = by_type["Fire"]
    fall = by_type["Fall"]
    crowd = by_type["Crowd"]
    face = by_type["Face"]
    ppe = by_type["PPE"]
    weapon = by_type["Weapon"]
    dominant_type = max(
        ("Fire", "Fall", "Crowd", "Face", "PPE", "Weapon"), key=lambda k: by_type.get(k, 0)
    )
    alert_rate = round(total_alerts / max(hours, 1), 2)
    unack_ratio = round((unack / total_alerts) * 100, 1) if total_alerts else 0.0

    risk_level = "low"
    if alert_rate >= 2.0 or unack_ratio >= 50:
        risk_level = "high"
    elif alert_rate >= 0.8 or unack_ratio >= 25:
        risk_level = "medium"

    insights = []
    if total_alerts == 0:
        insights.append("No incidents in selected window. System is stable.")
    else:
        insights.append(
            f"{dominant_type} is the dominant alert type with {max(fire, fall, crowd, face, ppe, weapon)} events."
        )
        if unack_ratio >= 40:
            insights.append(
                f"{unack_ratio}% alerts are unacknowledged. Improve response workflow."
            )
        top = next((row for row in per_camera_rows if int(row.alert_count) > 0), None)
        if top and total_alerts > 0:
            share = round((int(top.alert_count) / total_alerts) * 100, 1)
            if share >= 35:
                insights.append(
                    f"Camera '{top.name}' contributes {share}% of incidents; prioritize inspection."
                )

    return {
        "window_hours": hours,
        "since": since.isoformat(),
        "summary": {
            "total_cameras": total_cameras,
            "active_cameras": active_cameras,
            "total_alerts": total_alerts,
            "unacknowledged_alerts": unack,
            "alert_rate_per_hour": alert_rate,
            "risk_level": risk_level,
        },
        "by_type": by_type,
        "top_cameras": [
            {
                "camera_id": row.id,
                "camera_name": row.name,
                "alert_count": int(row.alert_count),
            }
            for row in per_camera_rows
        ],
        "hourly_trend": hourly,
        "intelligent_insights": insights,
    }


@router.get("/cameras/{camera_id}")
def camera_analytics(
    camera_id: int,
    hours: int = Query(72, ge=1, le=1440),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera or not camera_accessible(_user, camera):
        raise HTTPException(status_code=404, detail="Camera not found.")

    since = datetime.utcnow() - timedelta(hours=hours)
    q = db.query(Alert).filter(Alert.camera_id == camera_id, Alert.timestamp >= since)
    alerts = q.order_by(Alert.timestamp.desc()).all()

    total = len(alerts)
    unack = sum(1 for a in alerts if not a.acknowledged)
    fire_count = sum(1 for a in alerts if a.type == AlertTypeEnum.fire)
    fall_count = sum(1 for a in alerts if a.type == AlertTypeEnum.fall)
    crowd_count = sum(1 for a in alerts if a.type == AlertTypeEnum.crowd)
    face_count = sum(1 for a in alerts if a.type == AlertTypeEnum.face)
    ppe_count = sum(1 for a in alerts if a.type == AlertTypeEnum.ppe)
    weapon_count = sum(1 for a in alerts if a.type == AlertTypeEnum.weapon)
    by_type = {
        "Fire": fire_count,
        "Fall": fall_count,
        "Crowd": crowd_count,
        "Face": face_count,
        "PPE": ppe_count,
        "Weapon": weapon_count,
    }

    model_alerts = [
        {
            "model": "Fire Detection Model",
            "alert_type": "Fire",
            "count": fire_count,
            "active": bool(getattr(camera, "fire_enabled", True)),
        },
        {
            "model": "Fall Detection Model",
            "alert_type": "Fall",
            "count": fall_count,
            "active": bool(getattr(camera, "fall_enabled", True)),
        },
        {
            "model": "Crowd Intelligence Model",
            "alert_type": "Crowd",
            "count": crowd_count,
            "active": bool(getattr(camera, "person_detection_enabled", True))
            or bool(getattr(camera, "crowd_roi_enabled", False))
            or bool(getattr(camera, "footfall_enabled", True))
            or bool(getattr(camera, "heatmap_enabled", True)),
        },
        {
            "model": "Face Intelligence Model",
            "alert_type": "Face",
            "count": face_count,
            "active": bool(getattr(camera, "face_enabled", True)),
        },
        {
            "model": "PPE Compliance Model",
            "alert_type": "PPE",
            "count": ppe_count,
            "active": bool(getattr(camera, "ppe_enabled", False)),
        },
        {
            "model": "Weapon Detection Model",
            "alert_type": "Weapon",
            "count": weapon_count,
            "active": bool(getattr(camera, "weapon_enabled", False)),
        },
    ]

    hourly_rows = (
        db.query(Alert.timestamp, func.count(Alert.id))
        .filter(Alert.camera_id == camera_id, Alert.timestamp >= since)
        .group_by(Alert.timestamp)
        .all()
    )
    hourly = _bucketize_hourly(hourly_rows, since)

    dominant_model = max(
        (
            ("Fire Detection Model", fire_count),
            ("Fall Detection Model", fall_count),
            ("Crowd Intelligence Model", crowd_count),
            ("Face Intelligence Model", face_count),
            ("PPE Compliance Model", ppe_count),
            ("Weapon Detection Model", weapon_count),
        ),
        key=lambda x: x[1],
    )[0]
    recommendations = []
    if total == 0:
        recommendations.append("No incidents observed in this window.")
    else:
        recommendations.append(f"Dominant model for this camera: {dominant_model}.")
        if unack > 0:
            recommendations.append(
                f"{unack} events remain unacknowledged. Review alert handling for this camera."
            )
        if crowd_count > 0:
            recommendations.append(
                "Crowd events detected. Review occupancy thresholds and zone settings for this camera."
            )
        if face_count > 0:
            recommendations.append(
                "Face events detected. Review whitelist attendance and blacklist watchlist policy."
            )
        if ppe_count > 0:
            recommendations.append(
                "PPE events detected. Review configured equipment checklist for this camera."
            )
        if weapon_count > 0:
            recommendations.append(
                "Weapon events detected. Review VLM verification notes and scene context for this camera."
            )
        if fire_count > 0 and fall_count > 0:
            recommendations.append(
                "Both models are producing alerts; validate scene conditions and thresholds."
            )
        elif fire_count == 0 and fall_count > 0:
            recommendations.append(
                "Only fall alerts are active. Consider adjusting fire model threshold if expected."
            )
        elif fall_count == 0 and fire_count > 0:
            recommendations.append(
                "Only fire alerts are active. Validate fall posture sensitivity for this scene."
            )

    latest = alerts[0] if alerts else None
    return {
        "window_hours": hours,
        "since": since.isoformat(),
        "camera": {
            "id": camera.id,
            "name": camera.name,
            "location": camera.location,
            "status": str(camera.status.value if hasattr(camera.status, "value") else camera.status),
        },
        "summary": {
            "total_alerts": total,
            "unacknowledged_alerts": unack,
            "by_type": by_type,
            "dominant_model": dominant_model,
            "latest_alert_at": latest.timestamp.isoformat() if latest else None,
        },
        "model_alerts": model_alerts,
        "hourly_trend": hourly,
        "recent_alerts": [
            {
                "id": a.id,
                "type": a.type.value,
                "confidence": a.confidence,
                "acknowledged": a.acknowledged,
                "timestamp": a.timestamp.isoformat(),
                "snapshot_path": a.snapshot_path,
            }
            for a in alerts[:20]
        ],
        "intelligent_recommendations": recommendations,
    }
