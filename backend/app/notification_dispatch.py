"""
notification_dispatch.py
------------------------
Send email (SMTP) and WhatsApp (Ultramsg API) when alerts are created.

Ultramsg docs: POST https://api.ultramsg.com/{instance_id}/messages/chat
Form body (application/x-www-form-urlencoded): token, to, body

Runs in a background thread so inference is not blocked.
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Camera, NotificationSettings

logger = logging.getLogger(__name__)

ULTRAMSG_CHAT_URL = "https://api.ultramsg.com/{instance_id}/messages/chat"
DEFAULT_EMAIL_SUBJECT_TEMPLATE = "[Lumicams] {alert_type} alert - {camera_name} (#{alert_id})"
DEFAULT_EMAIL_BODY_TEMPLATE = (
    "LUMICAMS - ALERT NOTIFICATION\n\n"
    "Alert ID: {alert_id}\n"
    "Type: {alert_type}\n"
    "Confidence: {confidence}\n"
    "Time (UTC): {timestamp_utc}\n"
    "Camera ID: {camera_id}\n"
    "Camera name: {camera_name}\n"
    "Location: {camera_location}\n"
    "Details: {notes}\n"
    "Snapshot: {snapshot_url}\n"
)
DEFAULT_WHATSAPP_BODY_TEMPLATE = (
    "*LUMICAMS ALERT*\n"
    "Type: {alert_type}\n"
    "Camera: {camera_name}\n"
    "Time: {timestamp_utc}\n"
    "Confidence: {confidence}\n"
    "Details: {notes}\n"
    "Snapshot: {snapshot_url}"
)


def get_or_create_notification_settings(
    db: Session,
    organization_id: Optional[int] = None,
) -> NotificationSettings:
    """Per-organization settings; falls back to legacy global row (organization_id NULL)."""
    if organization_id is not None:
        row = (
            db.query(NotificationSettings)
            .filter(NotificationSettings.organization_id == organization_id)
            .first()
        )
        if row:
            return row
        legacy = (
            db.query(NotificationSettings)
            .filter(NotificationSettings.organization_id.is_(None))
            .order_by(NotificationSettings.id.asc())
            .first()
        )
        if legacy:
            row = NotificationSettings(
                organization_id=organization_id,
                smtp_enabled=legacy.smtp_enabled,
                smtp_host=legacy.smtp_host,
                smtp_port=legacy.smtp_port,
                smtp_use_implicit_ssl=legacy.smtp_use_implicit_ssl,
                smtp_username=legacy.smtp_username,
                smtp_password=legacy.smtp_password,
                smtp_from_email=legacy.smtp_from_email,
                email_recipients=list(legacy.email_recipients or []),
                default_owner_email=legacy.default_owner_email,
                whatsapp_enabled=legacy.whatsapp_enabled,
                ultramsg_instance_id=legacy.ultramsg_instance_id,
                ultramsg_token=legacy.ultramsg_token,
                whatsapp_recipients=list(legacy.whatsapp_recipients or []),
                email_subject_template=legacy.email_subject_template,
                email_body_template=legacy.email_body_template,
                whatsapp_body_template=legacy.whatsapp_body_template,
                public_dashboard_url=legacy.public_dashboard_url,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

    row = (
        db.query(NotificationSettings)
        .filter(NotificationSettings.organization_id.is_(None))
        .order_by(NotificationSettings.id.asc())
        .first()
    )
    if row:
        return row

    def _split_emails(s: str) -> List[str]:
        return [x.strip() for x in (s or "").replace(";", ",").split(",") if x.strip()]

    owner = os.getenv("DEFAULT_OWNER_EMAIL", "").strip()
    support = os.getenv("SUPPORT_EMAIL", "").strip()
    seed_recipients = _split_emails(os.getenv("ALERT_EMAIL_RECIPIENTS", ""))
    if not seed_recipients:
        if owner:
            seed_recipients = [owner]
        elif support:
            seed_recipients = [support]

    row = NotificationSettings(
        smtp_enabled=False,
        smtp_host=(os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST") or "").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        smtp_use_implicit_ssl=os.getenv("SMTP_USE_implicit_SSL", "true").strip().lower()
        not in ("0", "false", "no")
        or int(os.getenv("SMTP_PORT", "465")) == 465,
        smtp_username=(os.getenv("SMTP_USERNAME") or "").strip(),
        smtp_password=(os.getenv("SMTP_PASSWORD") or "").strip(),
        smtp_from_email=(support or os.getenv("SMTP_FROM") or owner or "").strip(),
        email_recipients=seed_recipients,
        default_owner_email=owner or support,
        whatsapp_enabled=False,
        ultramsg_instance_id=(os.getenv("ULTRAMSG_INSTANCE_ID") or "").strip(),
        ultramsg_token=(os.getenv("ULTRAMSG_TOKEN") or "").strip(),
        whatsapp_recipients=[
            x.strip()
            for x in re.split(r"[\s,;]+", os.getenv("WHATSAPP_RECIPIENTS", "") or "")
            if x.strip()
        ],
        public_dashboard_url=(os.getenv("PUBLIC_DASHBOARD_URL") or "").strip(),
        email_subject_template=(os.getenv("ALERT_EMAIL_SUBJECT_TEMPLATE") or DEFAULT_EMAIL_SUBJECT_TEMPLATE),
        email_body_template=(os.getenv("ALERT_EMAIL_BODY_TEMPLATE") or DEFAULT_EMAIL_BODY_TEMPLATE),
        whatsapp_body_template=(os.getenv("ALERT_WHATSAPP_BODY_TEMPLATE") or DEFAULT_WHATSAPP_BODY_TEMPLATE),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("notification_settings row created (defaults from env where set)")
    return row


def _normalize_e164_phone(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        return "+" + digits
    if len(digits) >= 10:
        return "+" + digits
    return s


def _collect_email_recipients(settings: NotificationSettings) -> List[str]:
    emails: List[str] = []
    for src in settings.email_recipients or []:
        if isinstance(src, str) and src.strip():
            emails.append(src.strip())
    if settings.default_owner_email and settings.default_owner_email.strip():
        e = settings.default_owner_email.strip()
        emails.append(e)
    seen: set[str] = set()
    out: List[str] = []
    for e in emails:
        k = e.lower()
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def _collect_whatsapp_recipients(settings: NotificationSettings) -> List[str]:
    out: List[str] = []
    for src in settings.whatsapp_recipients or []:
        if isinstance(src, str) and src.strip():
            n = _normalize_e164_phone(src.strip())
            if n:
                out.append(n)
    seen = set()
    deduped: List[str] = []
    for n in out:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped


def _render_template(template: str, context: dict[str, str], fallback: str) -> str:
    tpl = (template or "").strip()
    if not tpl:
        tpl = fallback
    try:
        return tpl.format_map(context)
    except Exception:
        return fallback.format_map(context)


def build_alert_plain_text(
    *,
    alert_id: int,
    camera_id: int,
    camera_name: str,
    camera_location: Optional[str],
    alert_type: str,
    confidence: str,
    timestamp_utc: datetime,
    notes: Optional[str],
    snapshot_path: Optional[str],
    public_base: str,
) -> str:
    ts = timestamp_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "LUMICAMS — ALERT NOTIFICATION",
        "",
        f"Alert ID:       {alert_id}",
        f"Type:           {alert_type}",
        f"Confidence:     {confidence}",
        f"Time (UTC):     {ts}",
        f"Camera ID:      {camera_id}",
        f"Camera name:    {camera_name}",
    ]
    if camera_location:
        lines.append(f"Location:       {camera_location}")
    if notes:
        lines.append(f"Details:        {notes}")
    if snapshot_path:
        lines.append(f"Snapshot file:  {snapshot_path}")
        if public_base:
            name = Path(str(snapshot_path).replace("\\", "/")).name
            url = public_base.rstrip("/") + "/snapshots/" + name
            lines.append(f"Snapshot URL:   {url}")
    lines.append("")
    lines.append("— Lumicams")
    return "\n".join(lines)


def build_alert_html(
    *,
    alert_id: int,
    camera_id: int,
    camera_name: str,
    camera_location: Optional[str],
    alert_type: str,
    confidence: str,
    timestamp_utc: datetime,
    notes: Optional[str],
    snapshot_path: Optional[str],
    public_base: str,
) -> str:
    ts = timestamp_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    snap_url = ""
    if snapshot_path and public_base:
        snap = str(snapshot_path).replace("\\", "/")
        if "snapshots/" in snap:
            snap_path = snap.split("snapshots/")[-1]
        else:
            snap_path = Path(snap).name
        snap_url = public_base.rstrip("/") + "/snapshots/" + snap_path

    loc_row = (
        f"<tr><td><b>Location</b></td><td>{camera_location}</td></tr>" if camera_location else ""
    )
    notes_row = f"<tr><td><b>Details</b></td><td>{notes or '—'}</td></tr>"
    img_block = ""
    if snap_url:
        img_block = f'<p><a href="{snap_url}">Open snapshot</a></p>'

    return f"""\
<html><body style="font-family:system-ui,Segoe UI,sans-serif;font-size:14px;color:#111;">
<h2 style="color:#0a6;">Lumicams — Alert</h2>
<table cellpadding="6" style="border-collapse:collapse;">
<tr><td><b>Alert ID</b></td><td>{alert_id}</td></tr>
<tr><td><b>Type</b></td><td>{alert_type}</td></tr>
<tr><td><b>Confidence</b></td><td>{confidence}</td></tr>
<tr><td><b>Time (UTC)</b></td><td>{ts}</td></tr>
<tr><td><b>Camera ID</b></td><td>{camera_id}</td></tr>
<tr><td><b>Camera</b></td><td>{camera_name}</td></tr>
{loc_row}
{notes_row}
</table>
{img_block}
<p style="color:#666;font-size:12px;">Automated message from Lumicams.</p>
</body></html>"""


def send_email_alert(
    settings: NotificationSettings,
    *,
    subject: str,
    plain_body: str,
    html_body: str,
    attachment_path: Optional[str],
) -> tuple[bool, str]:
    recipients = _collect_email_recipients(settings)
    if not recipients:
        return False, "No email recipients configured"
    if not settings.smtp_host or not settings.smtp_from_email:
        return False, "SMTP host or from-address missing"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    if attachment_path:
        p = Path(attachment_path)
        if not p.is_file():
            alt_p = Path("snapshots") / p.name
            if alt_p.is_file():
                p = alt_p
        if p.is_file():
            try:
                with open(p, "rb") as f:
                    img = MIMEImage(f.read(), _subtype="jpeg")
                    img.add_header("Content-Disposition", "attachment", filename=p.name)
                    msg.attach(img)
            except OSError as exc:
                logger.warning("Snapshot attach failed: %s", exc)

    try:
        # Port 465 is implicit TLS per convention; 587 typically STARTTLS.
        use_ssl = settings.smtp_port == 465 or settings.smtp_use_implicit_ssl
        if use_ssl and settings.smtp_port != 587:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.sendmail(settings.smtp_from_email, recipients, msg.as_string())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                try:
                    smtp.starttls()
                    smtp.ehlo()
                except smtplib.SMTPException:
                    pass
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.sendmail(settings.smtp_from_email, recipients, msg.as_string())
        return True, "sent"
    except Exception as exc:
        logger.warning("SMTP send failed: %s", exc)
        return False, str(exc)


def send_ultramsg_text(
    instance_id: str,
    token: str,
    to_phone: str,
    body: str,
) -> tuple[bool, str]:
    if not instance_id or not token:
        return False, "Ultramsg instance id or token missing"
    base_url = ULTRAMSG_CHAT_URL.format(instance_id=instance_id)
    # Ultramsg expects application/x-www-form-urlencoded (see official Python examples).
    to_clean = to_phone.strip()
    if to_clean.startswith("+"):
        to_clean = to_clean[1:]
    payload = urllib.parse.urlencode(
        {
            "to": to_clean,
            "body": body[:4090],
        }
    ).encode("utf-8")
    # Some deployments require token in querystring; keep it there and in body-compatible format.
    url = f"{base_url}?token={urllib.parse.quote(token, safe='')}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "AegisEye/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return True, raw[:500]
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        logger.warning("Ultramsg HTTP %s: %s", exc.code, err_body)
        return False, f"HTTP {exc.code}: {err_body[:300]}"
    except Exception as exc:
        logger.warning("Ultramsg request failed: %s", exc)
        return False, str(exc)


def dispatch_alert_notifications(
    *,
    alert_id: int,
    camera_id: int,
    camera_name: str,
    alert_type: str,
    confidence: str,
    snapshot_path: Optional[str],
    notes: Optional[str],
    timestamp_utc: datetime,
) -> None:
    db = SessionLocal()
    try:
        cam = db.query(Camera).filter(Camera.id == camera_id).first()
        org_id = getattr(cam, "organization_id", None) if cam else None
        settings = get_or_create_notification_settings(db, organization_id=org_id)
        camera_location = cam.location if cam else None

        public_base = (settings.public_dashboard_url or "").strip() or os.getenv(
            "PUBLIC_DASHBOARD_URL", ""
        ).strip()
        snap_name = Path(str(snapshot_path).replace("\\", "/")).name if snapshot_path else ""
        snapshot_url = f"{public_base.rstrip('/')}/snapshots/{snap_name}" if public_base and snap_name else ""
        ts_text = timestamp_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        context = {
            "alert_id": str(alert_id),
            "alert_type": str(alert_type),
            "confidence": str(confidence),
            "timestamp_utc": ts_text,
            "camera_id": str(camera_id),
            "camera_name": camera_name or "",
            "camera_location": camera_location or "-",
            "notes": notes or "-",
            "snapshot_path": snapshot_path or "-",
            "snapshot_url": snapshot_url or "-",
        }
        subject = _render_template(
            settings.email_subject_template,
            context,
            DEFAULT_EMAIL_SUBJECT_TEMPLATE,
        )
        plain = _render_template(
            settings.email_body_template,
            context,
            DEFAULT_EMAIL_BODY_TEMPLATE,
        )
        html = (
            "<html><body><pre style=\"font-family:Segoe UI,Arial,sans-serif;"
            "white-space:pre-wrap;line-height:1.4\">"
            + plain
            + "</pre></body></html>"
        )
        whatsapp_text = _render_template(
            settings.whatsapp_body_template,
            context,
            DEFAULT_WHATSAPP_BODY_TEMPLATE,
        )

        if settings.smtp_enabled:
            ok, msg = send_email_alert(
                settings,
                subject=subject,
                plain_body=plain,
                html_body=html,
                attachment_path=snapshot_path,
            )
            if ok:
                logger.info("Alert %s email sent to %s", alert_id, "recipients")
            else:
                logger.warning("Alert %s email not sent: %s", alert_id, msg)

        if settings.whatsapp_enabled and settings.ultramsg_instance_id and settings.ultramsg_token:
            phones = _collect_whatsapp_recipients(settings)
            if not phones:
                logger.warning("WhatsApp enabled but no recipients for alert %s", alert_id)
            for phone in phones:
                ok, info = send_ultramsg_text(
                    settings.ultramsg_instance_id,
                    settings.ultramsg_token,
                    phone,
                    whatsapp_text,
                )
                if ok:
                    logger.info("Alert %s WhatsApp queued/sent to %s", alert_id, phone)
                else:
                    logger.warning("Alert %s WhatsApp failed %s: %s", alert_id, phone, info)
    except Exception as exc:
        logger.warning("dispatch_alert_notifications error: %s", exc)
    finally:
        db.close()


def schedule_alert_notifications(
    *,
    alert_id: int,
    camera_id: int,
    camera_name: str,
    alert_type: str,
    confidence: str,
    snapshot_path: Optional[str],
    notes: Optional[str],
    timestamp_utc: datetime,
) -> None:
    kwargs = dict(
        alert_id=alert_id,
        camera_id=camera_id,
        camera_name=camera_name,
        alert_type=alert_type,
        confidence=confidence,
        snapshot_path=snapshot_path,
        notes=notes,
        timestamp_utc=timestamp_utc,
    )
    threading.Thread(target=lambda: dispatch_alert_notifications(**kwargs), daemon=True).start()


def send_test_notifications(db: Session, organization_id: Optional[int] = None) -> dict[str, Any]:
    """Sync test from API (admin)."""
    settings = get_or_create_notification_settings(db, organization_id=organization_id)
    public_base = (settings.public_dashboard_url or "").strip()
    now = datetime.utcnow()
    context = {
        "alert_id": "0",
        "alert_type": "Test",
        "confidence": "1.0",
        "timestamp_utc": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "camera_id": "0",
        "camera_name": "Test camera",
        "camera_location": "Test location",
        "notes": "This is a test message from Lumicams notification settings.",
        "snapshot_path": "-",
        "snapshot_url": (f"{public_base.rstrip('/')}/snapshots/test.jpg" if public_base else "-"),
    }
    plain = _render_template(
        settings.email_body_template,
        context,
        DEFAULT_EMAIL_BODY_TEMPLATE,
    )
    html = (
        "<html><body><pre style=\"font-family:Segoe UI,Arial,sans-serif;"
        "white-space:pre-wrap;line-height:1.4\">"
        + plain
        + "</pre></body></html>"
    )
    whatsapp_text = _render_template(
        settings.whatsapp_body_template,
        context,
        DEFAULT_WHATSAPP_BODY_TEMPLATE,
    )
    subject = _render_template(
        settings.email_subject_template,
        context,
        DEFAULT_EMAIL_SUBJECT_TEMPLATE,
    )
    out: dict[str, Any] = {"email": None, "whatsapp": None}

    if settings.smtp_enabled:
        ok, msg = send_email_alert(
            settings,
            subject=subject,
            plain_body=plain,
            html_body=html,
            attachment_path=None,
        )
        out["email"] = {"ok": ok, "detail": msg}
    else:
        out["email"] = {"ok": False, "detail": "SMTP disabled"}

    if settings.whatsapp_enabled and settings.ultramsg_instance_id and settings.ultramsg_token:
        phones = _collect_whatsapp_recipients(settings)
        results = []
        for phone in phones:
            ok, info = send_ultramsg_text(
                settings.ultramsg_instance_id,
                settings.ultramsg_token,
                phone,
                whatsapp_text,
            )
            results.append({"to": phone, "ok": ok, "detail": info})
        out["whatsapp"] = results if results else [{"ok": False, "detail": "No recipients"}]
    else:
        out["whatsapp"] = {"ok": False, "detail": "WhatsApp disabled or not configured"}

    return out
