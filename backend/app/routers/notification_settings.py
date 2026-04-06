"""
Admin API for SMTP and Ultramsg (WhatsApp) notification settings.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import NotificationSettings, User
from app.tenancy import is_super_admin
from app.notification_dispatch import get_or_create_notification_settings, send_test_notifications
from app.schema import NotificationSettingsOut, NotificationSettingsUpdate

router = APIRouter(tags=["Notification settings"])


def _notification_org_id(user: User) -> int | None:
    """Super admin uses legacy global row (NULL); org admins use their org."""
    if is_super_admin(user):
        return None
    return user.organization_id


def _serialize(row: NotificationSettings) -> NotificationSettingsOut:
    emails = [str(x).strip() for x in (row.email_recipients or []) if str(x).strip()]
    phones = [str(x).strip() for x in (row.whatsapp_recipients or []) if str(x).strip()]
    return NotificationSettingsOut(
        smtp_enabled=bool(row.smtp_enabled),
        smtp_host=row.smtp_host or "",
        smtp_port=int(row.smtp_port or 465),
        smtp_use_implicit_ssl=bool(row.smtp_use_implicit_ssl),
        smtp_username=row.smtp_username or "",
        smtp_from_email=row.smtp_from_email or "",
        email_recipients=emails,
        default_owner_email=row.default_owner_email or "",
        smtp_password_configured=bool(row.smtp_password),
        whatsapp_enabled=bool(row.whatsapp_enabled),
        ultramsg_instance_id=row.ultramsg_instance_id or "",
        ultramsg_token_configured=bool(row.ultramsg_token),
        whatsapp_recipients=phones,
        public_dashboard_url=row.public_dashboard_url or "",
        email_subject_template=row.email_subject_template or "",
        email_body_template=row.email_body_template or "",
        whatsapp_body_template=row.whatsapp_body_template or "",
        updated_at=row.updated_at,
    )


@router.get("/settings/notifications", response_model=NotificationSettingsOut)
def read_notification_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    row = get_or_create_notification_settings(db, organization_id=_notification_org_id(admin))
    return _serialize(row)


@router.patch("/settings/notifications", response_model=NotificationSettingsOut)
def update_notification_settings(
    payload: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    row = get_or_create_notification_settings(db, organization_id=_notification_org_id(admin))
    data = payload.model_dump(exclude_unset=True)
    if "smtp_password" in data:
        if not data["smtp_password"]:
            del data["smtp_password"]
    if "ultramsg_token" in data:
        if not data["ultramsg_token"]:
            del data["ultramsg_token"]
    for key, val in data.items():
        setattr(row, key, val)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.post("/settings/notifications/test")
def test_notification_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    get_or_create_notification_settings(db, organization_id=_notification_org_id(admin))
    return send_test_notifications(db, organization_id=_notification_org_id(admin))
