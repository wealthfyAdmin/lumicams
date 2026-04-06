"""
models.py
---------
SQLAlchemy ORM models for Aegis-Eye.

Tables:
  - users              : Platform users with RBAC roles.
  - cameras            : RTSP / local video sources managed by users.
  - alerts             : AI-detected events (Fire, Fall) linked to cameras.
  - footfall_crossings : Entry/exit counts per virtual line crossing.
  - crowd_heatmap_hourly : Accumulated presence grid per camera per hour.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RoleEnum(str, enum.Enum):
    """User roles: Lumicams platform vs per-organization."""
    super_admin = "super_admin"  # Lumicams — all orgs
    org_admin = "org_admin"  # Full admin within one organization
    operator = "operator"  # View/ack within one organization


class VlmVerificationStatus(str, enum.Enum):
    """Second-stage vision-language verification on alerts."""
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"  # Likely false positive
    skipped = "skipped"  # VLM disabled or no API key
    error = "error"


class CameraStatusEnum(str, enum.Enum):
    """Live connectivity state of a camera stream."""
    active   = "active"
    inactive = "inactive"
    error    = "error"


class AlertTypeEnum(str, enum.Enum):
    """Category of AI-detected event."""
    fire = "Fire"
    fall = "Fall"
    crowd = "Crowd"
    face = "Face"
    ppe = "PPE"
    weapon = "Weapon"


class FaceCategoryEnum(str, enum.Enum):
    whitelist = "whitelist"
    blacklist = "blacklist"
    neutral = "neutral"


class FootfallDirectionEnum(str, enum.Enum):
    """Direction of line crossing (virtual threshold)."""
    entry = "entry"  # top → bottom of frame (yincreasing)
    exit = "exit"    # bottom → top


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Organization(Base):
    """Customer organization (tenant). Cameras and org users belong here."""

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(64), unique=True, nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="organization")
    cameras = relationship("Camera", back_populates="organization")

    def __repr__(self) -> str:
        return f"<Organization id={self.id} name={self.name}>"


class User(Base):
    """
    Represents a platform user.

    Platform super_admin has no organization_id. Org users must belong to an organization.
    """
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    full_name       = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(
        Enum(RoleEnum, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RoleEnum.operator,
    )
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    organization = relationship("Organization", back_populates="users")
    # One user can own many cameras (legacy owner id; tenant is on Camera.organization_id)
    cameras = relationship("Camera", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


class Camera(Base):
    """
    Represents an RTSP/local video stream source.

    The VideoProcessor in inference.py opens `rtsp_url` using OpenCV.
    """
    __tablename__ = "cameras"

    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String(255), nullable=False)
    rtsp_url = Column(Text, nullable=False)
    location = Column(String(255), nullable=True)
    status   = Column(
        Enum(CameraStatusEnum),
        nullable=False,
        default=CameraStatusEnum.inactive,
    )
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Per-camera AI features (multi-select at create/edit time)
    person_detection_enabled = Column(Boolean, default=True, nullable=False)
    crowd_roi_enabled = Column(Boolean, default=False, nullable=False)
    # Normalized axis-aligned rectangle [0–1] for “people in zone” count (like reference UI)
    crowd_roi_x1 = Column(Float, default=0.22, nullable=False)
    crowd_roi_y1 = Column(Float, default=0.28, nullable=False)
    crowd_roi_x2 = Column(Float, default=0.78, nullable=False)
    crowd_roi_y2 = Column(Float, default=0.72, nullable=False)
    last_crowd_roi_count = Column(Integer, default=0, nullable=False)
    crowd_limit_enabled = Column(Boolean, default=False, nullable=False)
    crowd_max_people = Column(Integer, default=10, nullable=False)
    fire_enabled = Column(Boolean, default=True, nullable=False)
    # Optional per-camera override. If null, global env FIRE_CONF_THRESHOLD is used.
    fire_min_confidence = Column(Float, nullable=True)
    fall_enabled = Column(Boolean, default=True, nullable=False)
    # Optional per-camera override. If null, global env FALL_CONSECUTIVE_FRAMES is used.
    fall_consecutive_frames = Column(Integer, nullable=True)
    face_enabled = Column(Boolean, default=True, nullable=False)
    # Optional per-camera override. If null, global env threshold is used.
    face_min_similarity = Column(Float, nullable=True)
    ppe_enabled = Column(Boolean, default=False, nullable=False)
    # Multi-select equipment list, e.g. ["helmet", "vest"] or ["kit"].
    ppe_items = Column(JSON, nullable=False, default=list)
    # Optional per-camera override. If null, global env PPE_CONF_THRESHOLD is used.
    ppe_confidence = Column(Float, nullable=True)
    weapon_enabled = Column(Boolean, default=False, nullable=False)
    weapon_confidence = Column(Float, nullable=True)

    footfall_enabled = Column(Boolean, default=True, nullable=False)
    # "line" = horizontal virtual line crossing; "zone" = entry/exit when foot point enters/leaves ROI
    footfall_mode = Column(String(16), default="line", nullable=False)
    footfall_line_y = Column(
        Float,
        default=0.5,
        nullable=False,
    )  # normalized 0–1 horizontal line across frame (0 = top)
    heatmap_enabled = Column(Boolean, default=True, nullable=False)

    owner  = relationship("User", back_populates="cameras")
    organization = relationship("Organization", back_populates="cameras")
    alerts = relationship("Alert", back_populates="camera", cascade="all, delete-orphan")
    footfall_crossings = relationship(
        "FootfallCrossing",
        back_populates="camera",
        cascade="all, delete-orphan",
    )
    crowd_heatmaps = relationship(
        "CrowdHeatmapHourly",
        back_populates="camera",
        cascade="all, delete-orphan",
    )
    face_sightings = relationship(
        "FaceSighting",
        back_populates="camera",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Camera id={self.id} name={self.name} status={self.status}>"


class Alert(Base):
    """
    Represents a single AI-detected event on a camera stream.

    `snapshot_path` stores the relative path inside /snapshots/ where the
    frame image was saved at the time of detection.
    """
    __tablename__ = "alerts"

    id            = Column(Integer, primary_key=True, index=True)
    camera_id     = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    type          = Column(Enum(AlertTypeEnum), nullable=False)
    confidence    = Column(String(10), nullable=True)   # e.g. "0.87"
    timestamp     = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    snapshot_path = Column(String(512), nullable=True)  # relative path to saved frame
    acknowledged  = Column(Boolean, default=False, nullable=False)
    notes         = Column(Text, nullable=True)
    vlm_status = Column(
        Enum(VlmVerificationStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    vlm_explanation = Column(Text, nullable=True)
    vlm_checked_at = Column(DateTime, nullable=True)

    camera = relationship("Camera", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert id={self.id} type={self.type} camera_id={self.camera_id}>"


class FootfallCrossing(Base):
    """Single line-crossing event for footfall entry/exit counting."""

    __tablename__ = "footfall_crossings"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    direction = Column(Enum(FootfallDirectionEnum), nullable=False, index=True)
    crossed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    track_id = Column(Integer, nullable=True)

    camera = relationship("Camera", back_populates="footfall_crossings")

    def __repr__(self) -> str:
        return f"<FootfallCrossing id={self.id} camera_id={self.camera_id} {self.direction}>"


class CrowdHeatmapHourly(Base):
    """
    Hourly accumulated crowd presence grid (flattened list, row-major).
    Values are visit-weighted counts from person detections.
    """

    __tablename__ = "crowd_heatmap_hourly"
    __table_args__ = (
        UniqueConstraint("camera_id", "hour_bucket", name="uq_heatmap_camera_hour"),
    )

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    hour_bucket = Column(DateTime, nullable=False, index=True)
    grid_size = Column(Integer, nullable=False, default=16)
    cells = Column(JSON, nullable=False)  # list[int] length grid_size**2

    camera = relationship("Camera", back_populates="crowd_heatmaps")

    def __repr__(self) -> str:
        return f"<CrowdHeatmapHourly cam={self.camera_id} hour={self.hour_bucket}>"


class FaceIdentity(Base):
    """
    Known face identity with one or more normalized embeddings.
    category:
      - whitelist: trusted/attendance
      - blacklist: trigger security alert
      - neutral  : recognized but no alert policy
    """

    __tablename__ = "face_identities"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    employee_code = Column(String(64), nullable=True, index=True)
    face_image_path = Column(String(512), nullable=True)
    category = Column(Enum(FaceCategoryEnum), nullable=False, default=FaceCategoryEnum.neutral)
    embeddings = Column(JSON, nullable=False, default=list)  # list[list[float]]
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sightings = relationship("FaceSighting", back_populates="identity", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FaceIdentity id={self.id} name={self.name} category={self.category}>"


class FaceSighting(Base):
    """Face recognition event for analytics and attendance."""

    __tablename__ = "face_sightings"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    identity_id = Column(Integer, ForeignKey("face_identities.id"), nullable=True, index=True)
    category = Column(Enum(FaceCategoryEnum), nullable=False, default=FaceCategoryEnum.neutral)
    confidence = Column(Float, nullable=True)
    event_type = Column(String(32), nullable=False, default="recognition", index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    snapshot_path = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)

    camera = relationship("Camera", back_populates="face_sightings")
    identity = relationship("FaceIdentity", back_populates="sightings")

    def __repr__(self) -> str:
        return f"<FaceSighting id={self.id} cam={self.camera_id} category={self.category}>"


class NotificationSettings(Base):
    """
    Singleton-style notification configuration (one row).
    Admin manages SMTP and Ultramsg (WhatsApp) from the dashboard.
    Secrets are stored in DB; do not log passwords/tokens.
    """

    __tablename__ = "notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, unique=True, index=True)

    smtp_enabled = Column(Boolean, nullable=False, default=False)
    smtp_host = Column(String(255), nullable=False, default="")
    smtp_port = Column(Integer, nullable=False, default=465)
    # Port 465: SSL implicit; 587: usually STARTTLS
    smtp_use_implicit_ssl = Column(Boolean, nullable=False, default=True)
    smtp_username = Column(String(255), nullable=False, default="")
    smtp_password = Column(String(512), nullable=False, default="")
    smtp_from_email = Column(String(255), nullable=False, default="")
    # Additional recipients; if empty, default_owner_email is used when SMTP is on
    email_recipients = Column(JSON, nullable=False, default=list)
    default_owner_email = Column(String(255), nullable=False, default="")

    whatsapp_enabled = Column(Boolean, nullable=False, default=False)
    ultramsg_instance_id = Column(String(128), nullable=False, default="")
    ultramsg_token = Column(String(512), nullable=False, default="")
    whatsapp_recipients = Column(JSON, nullable=False, default=list)
    # Template placeholders:
    # {alert_id} {alert_type} {confidence} {timestamp_utc} {camera_id} {camera_name}
    # {camera_location} {notes} {snapshot_path} {snapshot_url}
    email_subject_template = Column(
        Text,
        nullable=False,
        default="[Lumicams] {alert_type} alert - {camera_name} (#{alert_id})",
    )
    email_body_template = Column(
        Text,
        nullable=False,
        default=(
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
        ),
    )
    whatsapp_body_template = Column(
        Text,
        nullable=False,
        default=(
            "*LUMICAMS ALERT*\n"
            "Type: {alert_type}\n"
            "Camera: {camera_name}\n"
            "Time: {timestamp_utc}\n"
            "Confidence: {confidence}\n"
            "Details: {notes}\n"
            "Snapshot: {snapshot_url}"
        ),
    )

    # Optional link prefix for emails, e.g. https://cctv.client.com
    public_dashboard_url = Column(String(512), nullable=False, default="")

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PersonSighting(Base):
    """
    Appearance embedding for cross-camera person search (histogram + optional text attributes).
    Written by the inference loop when person detection + ByteTrack IDs are available.
    """

    __tablename__ = "person_sightings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    local_track_id = Column(Integer, nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    snapshot_path = Column(String(512), nullable=True)
    # Normalized feature vector (e.g. HSV histogram) for cosine similarity
    embedding = Column(JSON, nullable=False, default=list)
    dominant_hue = Column(Float, nullable=True)  # OpenCV HSV H channel 0–180
    notes = Column(Text, nullable=True)  # optional VLM caption (filled by async job)

    camera = relationship("Camera")

    def __repr__(self) -> str:
        return f"<PersonSighting id={self.id} cam={self.camera_id} track={self.local_track_id}>"
