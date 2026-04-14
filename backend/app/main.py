"""
main.py
-------
Aegis-Eye FastAPI application entry-point.

Startup sequence:
  1. Load .env configuration.
  2. Create PostgreSQL tables (if they don't exist).
  3. Seed a default Admin user (if the users table is empty).
  4. Mount all API routers under /api.
  5. Register the WebSocket endpoint at /ws/alerts.
  6. Serve static snapshot images at /snapshots.
  7. On shutdown: stop all running VideoProcessors gracefully.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import hash_password
from app.database import (
    SessionLocal,
    create_tables,
    ensure_alert_schema_patches,
    ensure_camera_schema_patches,
    ensure_face_schema_patches,
    ensure_multitenant_schema_patches,
    ensure_notification_schema_patches,
)
from app.inference import registry
from app.models import RoleEnum, User
from app.routers import alerts, analytics, cameras, crowd, faces, notification_settings, organizations, users, vision
from app.websocket_manager import manager as ws_manager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aegis-eye")

# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Code before `yield` runs at startup; code after runs at shutdown.
    """
    logger.info("=== Aegis-Eye API starting up ===")

    # 1. Create DB tables + idempotent column patches (PostgreSQL)
    create_tables()
    ensure_camera_schema_patches()
    ensure_alert_schema_patches()
    ensure_face_schema_patches()
    ensure_notification_schema_patches()
    ensure_multitenant_schema_patches()
    logger.info("Database tables verified/created.")

    # 2. Seed default admin user
    _seed_admin()

    # 2b. Reset stale camera states
    # This often fails if you haven't run your SQL ALTER TABLE commands yet
    try:
        _reset_camera_states()
    except Exception as e:
        logger.warning(f"Could not reset camera states: {e}. Ensure DB columns match models.py")

    # 3. Expose the current event loop for background threads (inference)
    app.state.loop = asyncio.get_running_loop()

    yield  # Application runs here

    # Shutdown
    logger.info("Shutting down – stopping all processors …")
    registry.stop_all()
    logger.info("=== Aegis-Eye API shut down ===")


def _seed_admin() -> None:
    """
    Create a default Admin user if no users exist yet.
    Credentials are read from environment variables (see .env.example).
    """
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@lumicams.com")
            admin_pass  = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")
            admin = User(
                email=admin_email,
                full_name="System Administrator",
                hashed_password=hash_password(admin_pass),
                role=RoleEnum.super_admin,
                organization_id=None,
            )
            db.add(admin)
            db.commit()
            logger.info("Default admin user created: %s", admin_email)
    except Exception as exc:
        db.rollback()
        logger.error("Admin seed failed: %s", exc)
    finally:
        db.close()


def _reset_camera_states() -> None:
    """
    Mark all cameras inactive on API startup.
    Prevents stale "active" state after backend restart/crash.
    """
    from app.models import Camera, CameraStatusEnum

    db = SessionLocal()
    try:
        db.query(Camera).update({Camera.status: CameraStatusEnum.inactive})
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Camera state reset failed: %s", exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Production-oriented configuration (see backend/.env.example)
# ---------------------------------------------------------------------------

def _is_production_env() -> bool:
    e = os.getenv("ENVIRONMENT", os.getenv("AEGIS_ENV", "development")).lower().strip()
    return e in ("production", "prod", "staging")


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, "").strip().lower()
    if v == "":
        return default
    return v in ("1", "true", "yes", "on")


DOCS_ENABLED: bool = _env_bool("DOCS_ENABLED", not _is_production_env())
WS_REQUIRE_TOKEN: bool = _env_bool("WS_REQUIRE_TOKEN", _is_production_env())
APP_VERSION: str = (os.getenv("APP_VERSION", "1.0.0").strip() or "1.0.0")

_docs_url = "/api/docs" if DOCS_ENABLED else None
_redoc_url = "/api/redoc" if DOCS_ENABLED else None
_openapi_url = "/api/openapi.json" if DOCS_ENABLED else None


def _database_ok() -> bool:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database connectivity check failed.")
        return False
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lumicams / Aegis-Eye API",
    description=(
        "AI-powered surveillance: RTSP ingestion, YOLO detection, crowd analytics, "
        "face pipeline, WebSocket alerts, multi-tenant RBAC."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# Optional: reject Host headers not in this list (set in production behind nginx).
_trusted = [h.strip() for h in os.getenv("TRUSTED_HOSTS", "").split(",") if h.strip()]
if _trusted:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted)

# ---------------------------------------------------------------------------
# CORS – allow Next.js dev server and production origin
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files – serve saved snapshots
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "snapshots"))
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=str(SNAPSHOT_DIR)), name="snapshots")

# ---------------------------------------------------------------------------
# API Routers
# ---------------------------------------------------------------------------

app.include_router(users.router,   prefix="/api")
app.include_router(cameras.router, prefix="/api")
app.include_router(alerts.router,  prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(crowd.router, prefix="/api")
app.include_router(faces.router, prefix="/api")
app.include_router(notification_settings.router, prefix="/api")
app.include_router(organizations.router, prefix="/api")
app.include_router(vision.router, prefix="/api")

# ---------------------------------------------------------------------------
# WebSocket – real-time alert feed
# ---------------------------------------------------------------------------

@app.websocket("/ws/alerts")
async def websocket_alerts(ws: WebSocket):
    """
    WebSocket endpoint consumed by the Next.js dashboard.

    Clients connect here and receive JSON `AlertBroadcast` payloads
    whenever the AI engine detects a Fire or Fall event.

    Message format (server → client):
    {
      "event":         "alert",
      "alert_id":      42,
      "camera_id":     3,
      "camera_name":   "Lobby Cam",
      "type":          "Fire",
      "confidence":    "0.87",
      "timestamp":     "2024-01-15T12:34:56.789",
      "snapshot_path": "snapshots/cam3_fire_20240115_123456.jpg"
    }

    Clients can also send a ping message `{"event": "ping"}` to keep
    the connection alive; the server echoes back `{"event": "pong"}`.

    Pass `?token=<JWT>` to scope realtime events to the user's organization.
    When WS_REQUIRE_TOKEN is true (default in production), unauthenticated connections are rejected.
    """
    token = ws.query_params.get("token")
    if WS_REQUIRE_TOKEN and not token:
        await ws.close(code=4401)
        return
    org_id = None
    is_super = True
    if token:
        try:
            from app.auth import decode_access_token
            from app.models import RoleEnum

            td = decode_access_token(token)
            is_super = td.role == RoleEnum.super_admin
            org_id = td.organization_id
        except Exception:
            await ws.close(code=4401)
            return
    await ws_manager.connect(ws, organization_id=org_id, is_super_admin=is_super)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("event") == "ping":
                await ws.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket error: %s", exc)
    finally:
        await ws_manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["System"])
def health_check():
    """
    Liveness + readiness: returns 503 if PostgreSQL is unreachable.
    Use for load balancers and orchestrators (single Uvicorn worker — required for inference).
    """
    db_ok = _database_ok()
    payload = {
        "status": "ok" if db_ok else "unhealthy",
        "service": "Lumicams / Aegis-Eye API",
        "version": APP_VERSION,
        "environment": os.getenv("ENVIRONMENT", os.getenv("AEGIS_ENV", "development")),
        "database": "ok" if db_ok else "error",
        "processors_running": len(registry.running_ids()),
        "ws_connections": ws_manager.connection_count,
        "docs_enabled": DOCS_ENABLED,
    }
    if not db_ok:
        return JSONResponse(status_code=503, content=payload)
    return payload
