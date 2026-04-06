"""
schema.py
---------
Pydantic v2 schemas (request / response models) for Aegis-Eye.

Naming convention:
  - <Model>Create  : Input schema for POST endpoints.
  - <Model>Update  : Input schema for PATCH endpoints (all fields optional).
  - <Model>Out     : Output schema returned from GET / POST responses.
  - <Model>Public  : A stripped-down variant safe to expose publicly.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models import AlertTypeEnum, CameraStatusEnum, FaceCategoryEnum, RoleEnum, VlmVerificationStatus


# ---------------------------------------------------------------------------
# Token / Auth schemas
# ---------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Payload decoded from a JWT access token."""
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[RoleEnum] = None
    organization_id: Optional[int] = None


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: str
    full_name: Optional[str] = None
    password: str = Field(..., min_length=8, description="Minimum 8 characters")
    role: RoleEnum = RoleEnum.operator
    organization_id: Optional[int] = Field(
        None,
        description="Required for org_admin/operator when created by super_admin; omit to use caller org.",
    )


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str]
    role: RoleEnum
    is_active: bool
    created_at: datetime
    organization_id: Optional[int] = None

    model_config = {"from_attributes": True}


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=64)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=64)
    is_active: Optional[bool] = None


class OrganizationOut(BaseModel):
    id: int
    name: str
    slug: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Camera schemas
# ---------------------------------------------------------------------------

class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    rtsp_url: str = Field(..., description="RTSP stream URL or local video file path")
    location: Optional[str] = Field(None, max_length=255)
    organization_id: Optional[int] = Field(
        None,
        description="Super admin only: assign camera to this org. Others use their own org.",
    )
    person_detection_enabled: bool = True
    crowd_roi_enabled: bool = False
    crowd_roi_x1: float = Field(0.22, ge=0.0, le=1.0)
    crowd_roi_y1: float = Field(0.28, ge=0.0, le=1.0)
    crowd_roi_x2: float = Field(0.78, ge=0.0, le=1.0)
    crowd_roi_y2: float = Field(0.72, ge=0.0, le=1.0)
    crowd_limit_enabled: bool = False
    crowd_max_people: int = Field(10, ge=1, le=500)
    fire_enabled: bool = True
    fire_min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    fall_enabled: bool = True
    fall_consecutive_frames: Optional[int] = Field(None, ge=1, le=30)
    face_enabled: bool = True
    face_min_similarity: Optional[float] = Field(None, ge=0.0, le=1.0)
    ppe_enabled: bool = False
    ppe_items: list[str] = Field(default_factory=list)
    ppe_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    weapon_enabled: bool = False
    weapon_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    footfall_enabled: bool = True
    footfall_mode: str = Field(
        "line",
        description='Footfall: "line" = horizontal crossing, "zone" = entry/exit via ROI rectangle',
    )
    footfall_line_y: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Virtual counting line (horizontal): Y normalized 0–1",
    )
    heatmap_enabled: bool = True

    @field_validator("footfall_mode")
    @classmethod
    def validate_footfall_mode(cls, v: str) -> str:
        s = (v or "line").strip().lower()
        if s not in ("line", "zone"):
            raise ValueError('footfall_mode must be "line" or "zone"')
        return s

    @model_validator(mode="after")
    def _validate_roi_box(self) -> "CameraCreate":
        if self.crowd_roi_x1 == self.crowd_roi_x2 or self.crowd_roi_y1 == self.crowd_roi_y2:
            raise ValueError("Crowd ROI rectangle must have non-zero width and height.")
        return self

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, v: str) -> str:
        v = v.strip()
        # Define allowed video extensions for local files
        valid_video_extensions = (".mp4", ".avi", ".mkv", ".mov", ".wmv")
        
        if not (
            v.startswith("rtsp://")
            or v.startswith("rtsps://")
            or v.startswith("http://")
            or v.startswith("https://")
            or v.startswith("/")               # absolute local path
            or (len(v) > 1 and v[1] == ":")      # Windows drive letter e.g. C:\...
            or v.isdigit()                       # OpenCV device index
            or v.lower().endswith(valid_video_extensions) # ALLOWS: test1.mp4, video.avi, etc.
        ):
            raise ValueError(
                "rtsp_url must be an RTSP/HTTP URL, absolute path, device index, or a valid video file (mp4, avi, etc.)"
            )
        return v


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    rtsp_url: Optional[str] = None
    location: Optional[str] = None
    status: Optional[CameraStatusEnum] = None
    person_detection_enabled: Optional[bool] = None
    crowd_roi_enabled: Optional[bool] = None
    crowd_roi_x1: Optional[float] = Field(None, ge=0.0, le=1.0)
    crowd_roi_y1: Optional[float] = Field(None, ge=0.0, le=1.0)
    crowd_roi_x2: Optional[float] = Field(None, ge=0.0, le=1.0)
    crowd_roi_y2: Optional[float] = Field(None, ge=0.0, le=1.0)
    crowd_limit_enabled: Optional[bool] = None
    crowd_max_people: Optional[int] = Field(None, ge=1, le=500)
    fire_enabled: Optional[bool] = None
    fire_min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    fall_enabled: Optional[bool] = None
    fall_consecutive_frames: Optional[int] = Field(None, ge=1, le=30)
    face_enabled: Optional[bool] = None
    face_min_similarity: Optional[float] = Field(None, ge=0.0, le=1.0)
    ppe_enabled: Optional[bool] = None
    ppe_items: Optional[list[str]] = None
    ppe_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    weapon_enabled: Optional[bool] = None
    weapon_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    footfall_enabled: Optional[bool] = None
    footfall_mode: Optional[str] = None
    footfall_line_y: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Horizontal virtual line Y position (0=top, 1=bottom)",
    )
    heatmap_enabled: Optional[bool] = None

    @field_validator("footfall_mode")
    @classmethod
    def validate_footfall_mode_opt(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        s = v.strip().lower()
        if s not in ("line", "zone"):
            raise ValueError('footfall_mode must be "line" or "zone"')
        return s


class CameraOut(BaseModel):
    id: int
    name: str
    rtsp_url: str
    location: Optional[str]
    status: CameraStatusEnum
    user_id: int
    organization_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    person_detection_enabled: bool = True
    crowd_roi_enabled: bool = False
    crowd_roi_x1: float = 0.22
    crowd_roi_y1: float = 0.28
    crowd_roi_x2: float = 0.78
    crowd_roi_y2: float = 0.72
    last_crowd_roi_count: int = 0
    crowd_limit_enabled: bool = False
    crowd_max_people: int = 10
    fire_enabled: bool = True
    fire_min_confidence: Optional[float] = None
    fall_enabled: bool = True
    fall_consecutive_frames: Optional[int] = None
    face_enabled: bool = True
    face_min_similarity: Optional[float] = None
    ppe_enabled: bool = False
    ppe_items: list[str] = Field(default_factory=list)
    ppe_confidence: Optional[float] = None
    weapon_enabled: bool = False
    weapon_confidence: Optional[float] = None
    footfall_enabled: bool = True
    footfall_mode: str = "line"
    footfall_line_y: float = 0.5
    heatmap_enabled: bool = True

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Alert schemas
# ---------------------------------------------------------------------------

class AlertOut(BaseModel):
    id: int
    camera_id: int
    type: AlertTypeEnum
    confidence: Optional[str]
    timestamp: datetime
    snapshot_path: Optional[str]
    acknowledged: bool
    notes: Optional[str]
    vlm_status: Optional[VlmVerificationStatus] = None
    vlm_explanation: Optional[str] = None
    vlm_checked_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AlertAcknowledge(BaseModel):
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# WebSocket broadcast payload
# ---------------------------------------------------------------------------

class AlertBroadcast(BaseModel):
    """
    JSON payload pushed to all connected WebSocket clients
    when an alert is detected by the AI engine.
    """
    event: str = "alert"          # constant discriminator
    alert_id: int
    camera_id: int
    camera_name: str
    type: AlertTypeEnum
    confidence: Optional[str]
    timestamp: str                # ISO-8601
    snapshot_path: Optional[str]


# ---------------------------------------------------------------------------
# Processor control
# ---------------------------------------------------------------------------

class ProcessorStatusOut(BaseModel):
    camera_id: int
    running: bool
    message: str


# ---------------------------------------------------------------------------
# Face intelligence schemas
# ---------------------------------------------------------------------------

class FaceIdentityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    employee_code: Optional[str] = Field(None, max_length=64)
    category: FaceCategoryEnum = FaceCategoryEnum.neutral
    embeddings: list[list[float]] = Field(default_factory=list)
    is_active: bool = True
    organization_id: Optional[int] = Field(
        None,
        description="Platform admin: assign identity to this organization.",
    )


class FaceIdentityUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    employee_code: Optional[str] = Field(None, max_length=64)
    category: Optional[FaceCategoryEnum] = None
    embeddings: Optional[list[list[float]]] = None
    is_active: Optional[bool] = None


class FaceIdentityOut(BaseModel):
    id: int
    organization_id: Optional[int] = None
    name: str
    employee_code: Optional[str]
    face_image_path: Optional[str] = None
    category: FaceCategoryEnum
    embeddings: list[list[float]]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class FaceSightingOut(BaseModel):
    id: int
    camera_id: int
    identity_id: Optional[int]
    identity_name: Optional[str] = None
    category: FaceCategoryEnum
    confidence: Optional[float]
    event_type: str
    timestamp: datetime
    snapshot_path: Optional[str]
    notes: Optional[str]


# ---------------------------------------------------------------------------
# Notification settings (SMTP + Ultramsg WhatsApp)
# ---------------------------------------------------------------------------


class NotificationSettingsOut(BaseModel):
    smtp_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_use_implicit_ssl: bool
    smtp_username: str
    smtp_from_email: str
    email_recipients: list[str]
    default_owner_email: str
    smtp_password_configured: bool

    whatsapp_enabled: bool
    ultramsg_instance_id: str
    ultramsg_token_configured: bool
    whatsapp_recipients: list[str]

    public_dashboard_url: str
    email_subject_template: str
    email_body_template: str
    whatsapp_body_template: str
    updated_at: Optional[datetime] = None


class NotificationSettingsUpdate(BaseModel):
    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = Field(None, max_length=255)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_use_implicit_ssl: Optional[bool] = None
    smtp_username: Optional[str] = Field(None, max_length=255)
    smtp_password: Optional[str] = Field(None, max_length=512)
    smtp_from_email: Optional[str] = Field(None, max_length=255)
    email_recipients: Optional[list[str]] = None
    default_owner_email: Optional[str] = Field(None, max_length=255)

    whatsapp_enabled: Optional[bool] = None
    ultramsg_instance_id: Optional[str] = Field(None, max_length=128)
    ultramsg_token: Optional[str] = Field(None, max_length=512)
    whatsapp_recipients: Optional[list[str]] = None
    email_subject_template: Optional[str] = None
    email_body_template: Optional[str] = None
    whatsapp_body_template: Optional[str] = None

    public_dashboard_url: Optional[str] = Field(None, max_length=512)
