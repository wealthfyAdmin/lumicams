"""
database.py
-----------
SQLAlchemy async engine + session factory for PostgreSQL.
Reads connection settings from environment variables (see .env.example).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://aegis_user:aegis_pass@localhost:5432/aegis_eye",
)

# Create synchronous engine (suitable for FastAPI with sync routes or background threads)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # Checks connection health before use
    pool_size=10,             # Max persistent connections
    max_overflow=20,          # Extra connections under high load
    echo=False,               # Set True for SQL query logging during development
)

# Session factory – use as a context manager via `get_db()`
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# All ORM models inherit from this base
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that provides a SQLAlchemy session per request.
    Automatically closes the session when the request is done.

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables defined in models.py if they do not already exist."""
    # Import models here to ensure they are registered with Base
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def ensure_multitenant_schema_patches() -> None:
    """
    Idempotent PostgreSQL migrations: organizations, tenant columns, role VARCHAR,
    VLM columns, person_sightings, notification org scope.
    """
    import logging

    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return

    log = logging.getLogger(__name__)
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(64) UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
        )
        """,
        """
        INSERT INTO organizations (name, slug, is_active, created_at)
        SELECT 'Default Organization', 'default', TRUE, NOW() AT TIME ZONE 'utc'
        WHERE NOT EXISTS (SELECT 1 FROM organizations LIMIT 1)
        """,
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "ALTER TABLE face_identities ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)",
        "ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS organization_id INTEGER UNIQUE REFERENCES organizations(id)",
        """
        ALTER TABLE alerts ADD COLUMN IF NOT EXISTS vlm_status VARCHAR(32)
        """,
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS vlm_explanation TEXT",
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS vlm_checked_at TIMESTAMP",
        """
        CREATE TABLE IF NOT EXISTS person_sightings (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            camera_id INTEGER NOT NULL REFERENCES cameras(id),
            local_track_id INTEGER,
            timestamp TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
            snapshot_path VARCHAR(512),
            embedding JSON NOT NULL DEFAULT '[]'::json,
            dominant_hue DOUBLE PRECISION,
            notes TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_person_sightings_org_ts ON person_sightings (organization_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_person_sightings_cam ON person_sightings (camera_id, timestamp DESC)",
    ]
    try:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))

            # Migrate legacy enum role column to VARCHAR(32) with new role names
            row = conn.execute(
                text(
                    """
                    SELECT udt_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'role'
                    """
                )
            ).fetchone()
            udt = (row[0] or "").lower() if row else ""
            if udt and udt not in ("varchar", "character varying", "text"):
                conn.execute(text("ALTER TABLE users ALTER COLUMN role DROP DEFAULT"))
                conn.execute(
                    text(
                        """
                        ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(32)
                        USING (
                            CASE
                                WHEN role::text IN ('admin', 'ADMIN') THEN 'org_admin'
                                WHEN role::text IN ('operator', 'OPERATOR') THEN 'operator'
                                WHEN role::text IN ('super_admin', 'SUPER_ADMIN') THEN 'super_admin'
                                WHEN role::text IN ('org_admin', 'ORG_ADMIN') THEN 'org_admin'
                                ELSE COALESCE(role::text, 'operator')
                            END
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        UPDATE users SET role = 'super_admin'
                        WHERE id = (SELECT MIN(id) FROM users)
                          AND NOT EXISTS (SELECT 1 FROM users WHERE role = 'super_admin')
                        """
                    )
                )
            else:
                # Already varchar: normalize legacy labels
                conn.execute(
                    text(
                        """
                        UPDATE users SET role = 'org_admin'
                        WHERE role IN ('admin', 'ADMIN')
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        UPDATE users SET role = 'super_admin'
                        WHERE id = (SELECT MIN(id) FROM users)
                          AND NOT EXISTS (SELECT 1 FROM users WHERE role = 'super_admin')
                        """
                    )
                )

            # Backfill organization_id
            conn.execute(
                text(
                    """
                    UPDATE users SET organization_id = (SELECT id FROM organizations ORDER BY id LIMIT 1)
                    WHERE organization_id IS NULL AND role IN ('org_admin', 'operator')
                    """
                )
            )
            conn.execute(text("UPDATE users SET organization_id = NULL WHERE role = 'super_admin'"))
            conn.execute(
                text(
                    """
                    UPDATE cameras SET organization_id = u.organization_id
                    FROM users u
                    WHERE cameras.user_id = u.id AND cameras.organization_id IS NULL
                      AND u.organization_id IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE cameras SET organization_id = (SELECT id FROM organizations ORDER BY id LIMIT 1)
                    WHERE organization_id IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE face_identities SET organization_id = (SELECT id FROM organizations ORDER BY id LIMIT 1)
                    WHERE organization_id IS NULL
                    """
                )
            )
            # Duplicate notification settings per org if only legacy NULL-org row exists
            conn.execute(
                text(
                    """
                    INSERT INTO notification_settings (
                        organization_id, smtp_enabled, smtp_host, smtp_port, smtp_use_implicit_ssl,
                        smtp_username, smtp_password, smtp_from_email, email_recipients,
                        default_owner_email, whatsapp_enabled, ultramsg_instance_id, ultramsg_token,
                        whatsapp_recipients, email_subject_template, email_body_template,
                        whatsapp_body_template, public_dashboard_url, updated_at
                    )
                    SELECT o.id, n.smtp_enabled, n.smtp_host, n.smtp_port, n.smtp_use_implicit_ssl,
                        n.smtp_username, n.smtp_password, n.smtp_from_email, n.email_recipients,
                        n.default_owner_email, n.whatsapp_enabled, n.ultramsg_instance_id, n.ultramsg_token,
                        n.whatsapp_recipients, n.email_subject_template, n.email_body_template,
                        n.whatsapp_body_template, n.public_dashboard_url, n.updated_at
                    FROM organizations o
                    CROSS JOIN notification_settings n
                    WHERE n.organization_id IS NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM notification_settings ns WHERE ns.organization_id = o.id
                      )
                    """
                )
            )

        log.info("Multitenant schema patches verified.")
    except Exception as exc:
        log.warning("Multitenant schema patch failed: %s", exc)


def ensure_camera_schema_patches() -> None:
    """
    Apply idempotent ALTER TABLE ... ADD COLUMN IF NOT EXISTS for PostgreSQL.

    SQLAlchemy create_all() does not add new columns to existing tables; this
    keeps dev/prod DBs in sync when Camera gains fields.
    """
    import logging

    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return

    log = logging.getLogger(__name__)
    stmts = [
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS person_detection_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS crowd_roi_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS crowd_roi_x1 DOUBLE PRECISION NOT NULL DEFAULT 0.22",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS crowd_roi_y1 DOUBLE PRECISION NOT NULL DEFAULT 0.28",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS crowd_roi_x2 DOUBLE PRECISION NOT NULL DEFAULT 0.78",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS crowd_roi_y2 DOUBLE PRECISION NOT NULL DEFAULT 0.72",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS last_crowd_roi_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS crowd_limit_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS crowd_max_people INTEGER NOT NULL DEFAULT 10",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS fire_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS fire_min_confidence DOUBLE PRECISION",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS fall_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS fall_consecutive_frames INTEGER",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS face_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS face_min_similarity DOUBLE PRECISION",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ppe_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ppe_items JSON NOT NULL DEFAULT '[]'::json",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS ppe_confidence DOUBLE PRECISION",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS weapon_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS weapon_confidence DOUBLE PRECISION",
        "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS footfall_mode VARCHAR(16) NOT NULL DEFAULT 'line'",
    ]
    try:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
        log.info("Camera table schema patches verified.")
    except Exception as exc:
        log.warning("Camera schema patch failed (run sql/upgrade_camera_ai_models.sql): %s", exc)


def ensure_alert_schema_patches() -> None:
    """
    Ensure Alert enum values are in sync (PostgreSQL).
    """
    import logging
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return

    log = logging.getLogger(__name__)
    stmts = [
        # Some deployments use enum labels from python names (fire/fall/crowd),
        # others may have title-case labels. Ensure both crowd variants exist.
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'crowd'",
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'Crowd'",
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'face'",
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'Face'",
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'ppe'",
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'PPE'",
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'weapon'",
        "ALTER TYPE alerttypeenum ADD VALUE IF NOT EXISTS 'Weapon'",
    ]
    try:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
        log.info("Alert enum schema patches verified.")
    except Exception as exc:
        log.warning("Alert schema patch failed: %s", exc)


def ensure_face_schema_patches() -> None:
    """
    Ensure optional face intelligence columns exist for existing deployments.
    """
    import logging
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return

    log = logging.getLogger(__name__)
    stmts = [
        "ALTER TABLE face_identities ADD COLUMN IF NOT EXISTS face_image_path VARCHAR(512)",
    ]
    try:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
        log.info("Face table schema patches verified.")
    except Exception as exc:
        log.warning("Face schema patch failed: %s", exc)


def ensure_notification_schema_patches() -> None:
    """
    Ensure notification_settings table has template columns on existing deployments.
    """
    import logging
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return

    log = logging.getLogger(__name__)
    stmts = [
        "ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS email_subject_template TEXT NOT NULL DEFAULT '[Lumicams] {alert_type} alert - {camera_name} (#{alert_id})'",
        "ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS email_body_template TEXT NOT NULL DEFAULT 'LUMICAMS - ALERT NOTIFICATION\n\nAlert ID: {alert_id}\nType: {alert_type}\nConfidence: {confidence}\nTime (UTC): {timestamp_utc}\nCamera ID: {camera_id}\nCamera name: {camera_name}\nLocation: {camera_location}\nDetails: {notes}\nSnapshot: {snapshot_url}\n'",
        "ALTER TABLE notification_settings ADD COLUMN IF NOT EXISTS whatsapp_body_template TEXT NOT NULL DEFAULT '*LUMICAMS ALERT*\nType: {alert_type}\nCamera: {camera_name}\nTime: {timestamp_utc}\nConfidence: {confidence}\nDetails: {notes}\nSnapshot: {snapshot_url}'",
    ]
    try:
        with engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
        log.info("Notification table schema patches verified.")
    except Exception as exc:
        log.warning("Notification schema patch failed: %s", exc)
