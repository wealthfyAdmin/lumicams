"""
Footfall analytics and crowd heatmap REST APIs.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Camera, CrowdHeatmapHourly, FootfallCrossing, FootfallDirectionEnum, User
from app.tenancy import camera_accessible, is_super_admin

router = APIRouter(prefix="/crowd", tags=["Crowd Analytics"])


def _camera_or_404(camera_id: int, db: Session, user: User) -> Camera:
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam or not camera_accessible(user, cam):
        raise HTTPException(status_code=404, detail="Camera not found.")
    return cam


def _footfall_query(db: Session, user: User, camera_id: Optional[int], since: datetime):
    q = db.query(FootfallCrossing).filter(FootfallCrossing.crossed_at >= since)
    if camera_id is not None:
        q = q.filter(FootfallCrossing.camera_id == camera_id)
    elif not is_super_admin(user):
        if user.organization_id is None:
            return q.filter(FootfallCrossing.id == -1)
        cam_ids = [
            r.id
            for r in db.query(Camera.id)
            .filter(Camera.organization_id == user.organization_id)
            .all()
        ]
        if not cam_ids:
            return q.filter(FootfallCrossing.id == -1)
        q = q.filter(FootfallCrossing.camera_id.in_(cam_ids))
    return q


@router.get("/footfall/summary")
def footfall_summary(
    hours: int = Query(168, ge=1, le=744),
    camera_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Aggregated entry/exit counts and peak-hour hints (all cameras or one)."""
    since = datetime.utcnow() - timedelta(hours=hours)
    q = _footfall_query(db, _user, camera_id, since)
    rows = q.all()
    entry = sum(1 for r in rows if r.direction == FootfallDirectionEnum.entry)
    exit_ = sum(1 for r in rows if r.direction == FootfallDirectionEnum.exit)
    net_flow = entry - exit_

    by_hour: dict[str, dict[str, int]] = defaultdict(lambda: {"entry": 0, "exit": 0})
    for r in rows:
        key = r.crossed_at.replace(minute=0, second=0, microsecond=0).isoformat()
        if r.direction == FootfallDirectionEnum.entry:
            by_hour[key]["entry"] += 1
        else:
            by_hour[key]["exit"] += 1

    hourly = sorted(by_hour.items(), key=lambda x: x[0])
    peak_hour = None
    peak_total = 0
    for hkey, counts in hourly:
        t = counts["entry"] + counts["exit"]
        if t > peak_total:
            peak_total = t
            peak_hour = hkey

    # Simple day / week rollups from same window
    by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"entry": 0, "exit": 0})
    for r in rows:
        dkey = r.crossed_at.date().isoformat()
        if r.direction == FootfallDirectionEnum.entry:
            by_day[dkey]["entry"] += 1
        else:
            by_day[dkey]["exit"] += 1

    return {
        "window_hours": hours,
        "since": since.isoformat(),
        "totals": {"entry": entry, "exit": exit_, "net_flow": net_flow},
        "hourly": [{"hour": k, **v} for k, v in hourly],
        "by_day": [{"date": d, **c} for d, c in sorted(by_day.items())],
        "peak_hour": peak_hour,
        "peak_hour_total_crossings": peak_total,
        "insights": _footfall_insights(entry, exit_, peak_hour, peak_total),
    }


def _format_peak_hour_label(iso_hour: str) -> str:
    """Turn ISO hour bucket into a short human-readable label for operators."""
    try:
        s = iso_hour.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%d %b %Y · %H:%M")
    except Exception:
        return iso_hour


def _footfall_insights(
    entry: int,
    exit_: int,
    peak_hour: Optional[str],
    peak_total: int,
) -> List[str]:
    insights: List[str] = []
    if entry + exit_ == 0:
        insights.append(
            "No crossings in this period. Start the camera processor, enable footfall on the camera, "
            "and set the counting line in camera settings."
        )
        return insights
    if entry > exit_ * 1.2:
        insights.append("More entries than exits — net inward foot traffic.")
    elif exit_ > entry * 1.2:
        insights.append("More exits than entries — net outward foot traffic.")
    else:
        insights.append("Entry and exit counts are balanced.")
    if peak_hour and peak_total > 0:
        label = _format_peak_hour_label(peak_hour)
        insights.append(f"Busiest hour: {label} — {peak_total} crossings.")
    return insights


@router.get("/footfall/cameras/{camera_id}")
def footfall_camera(
    camera_id: int,
    hours: int = Query(168, ge=1, le=744),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _camera_or_404(camera_id, db, _user)
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(FootfallCrossing)
        .filter(
            FootfallCrossing.camera_id == camera_id,
            FootfallCrossing.crossed_at >= since,
        )
        .order_by(FootfallCrossing.crossed_at.desc())
        .limit(2000)
        .all()
    )
    entry = sum(1 for r in rows if r.direction == FootfallDirectionEnum.entry)
    exit_ = sum(1 for r in rows if r.direction == FootfallDirectionEnum.exit)
    by_hour: dict[str, dict[str, int]] = defaultdict(lambda: {"entry": 0, "exit": 0})
    for r in rows:
        key = r.crossed_at.replace(minute=0, second=0, microsecond=0).isoformat()
        if r.direction == FootfallDirectionEnum.entry:
            by_hour[key]["entry"] += 1
        else:
            by_hour[key]["exit"] += 1
    hourly = [{"hour": k, **v} for k, v in sorted(by_hour.items())]

    return {
        "camera_id": camera_id,
        "window_hours": hours,
        "since": since.isoformat(),
        "totals": {"entry": entry, "exit": exit_, "net_flow": entry - exit_},
        "hourly": hourly,
        "recent": [
            {
                "id": r.id,
                "direction": r.direction.value,
                "crossed_at": r.crossed_at.isoformat(),
                "track_id": r.track_id,
            }
            for r in rows[:100]
        ],
    }


@router.get("/heatmap/cameras/{camera_id}")
def heatmap_camera(
    camera_id: int,
    hours: int = Query(168, ge=1, le=744),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Merged hourly heatmap cells for high-traffic / bottleneck hints."""
    _camera_or_404(camera_id, db, _user)
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(CrowdHeatmapHourly)
        .filter(
            CrowdHeatmapHourly.camera_id == camera_id,
            CrowdHeatmapHourly.hour_bucket >= since,
        )
        .order_by(CrowdHeatmapHourly.hour_bucket.asc())
        .all()
    )
    if not rows:
        return {
            "camera_id": camera_id,
            "window_hours": hours,
            "grid_size": 16,
            "merged_cells": [],
            "hot_zones": [],
            "insights": ["No heatmap data yet. Run the camera with heatmap enabled."],
        }

    gs = rows[0].grid_size
    acc = [0] * (gs * gs)
    for row in rows:
        c = row.cells
        if not c or len(c) != len(acc):
            continue
        acc = [a + int(b) for a, b in zip(acc, c)]

    mx = max(acc) if acc else 0
    hot_zones: List[dict[str, Any]] = []
    if mx > 0:
        ranked = sorted(
            ((i, v) for i, v in enumerate(acc) if v > 0),
            key=lambda x: -x[1],
        )[:12]
        for idx, val in ranked:
            iy, ix = divmod(idx, gs)
            hot_zones.append(
                {
                    "grid_x": ix,
                    "grid_y": iy,
                    "weight": val,
                    "normalized": round(val / mx, 4),
                    "label": f"cell ({ix},{iy})",
                }
            )

    insights: List[str] = []
    if hot_zones:
        top = hot_zones[0]
        insights.append(
            f"Highest congregation grid cell: {top['label']} (relative intensity {top['normalized']})."
        )
        if len(hot_zones) >= 3:
            insights.append(
                "Multiple hot cells suggest distributed traffic or moving queues; review camera placement."
            )
    else:
        insights.append("Heatmap is flat — no sustained congregation detected.")

    return {
        "camera_id": camera_id,
        "window_hours": hours,
        "grid_size": gs,
        "merged_cells": acc,
        "hot_zones": hot_zones,
        "insights": insights,
    }