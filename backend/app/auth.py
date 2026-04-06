"""
auth.py
-------
JWT-based authentication and Role-Based Access Control (RBAC) for Aegis-Eye.

Flow:
  1. Client POSTs credentials to /api/auth/login.
  2. Server validates, issues a signed JWT (HS256).
  3. Client includes JWT in `Authorization: Bearer <token>` header.
  4. FastAPI dependency `get_current_user` decodes & validates the token.
  5. `require_admin` dependency enforces admin-only routes.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RoleEnum, User
from app.schema import TokenData

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------

SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-use-a-256bit-random-key")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain* password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password."""
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Encode *data* into a signed JWT.

    Args:
        data:          Payload dict (must include `sub` claim).
        expires_delta: Token lifetime; defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    """
    Decode and validate a JWT.

    Raises:
        HTTPException 401 if the token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[int] = payload.get("user_id")
        email: Optional[str] = payload.get("sub")
        role_str: Optional[str] = payload.get("role")

        if email is None or user_id is None:
            raise credentials_exception

        org_raw = payload.get("organization_id")
        org_id: Optional[int] = int(org_raw) if org_raw is not None else None

        return TokenData(
            user_id=user_id,
            email=email,
            role=RoleEnum(role_str) if role_str else None,
            organization_id=org_id,
        )
    except JWTError:
        raise credentials_exception


# ---------------------------------------------------------------------------
# FastAPI OAuth2 scheme & dependencies
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
_http_bearer_optional = HTTPBearer(auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency – resolves a valid JWT to the corresponding User ORM row.

    Raises:
        401 if token is invalid.
        401 if user not found or inactive.
    """
    token_data = decode_access_token(token)
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    return user


def get_current_user_bearer_or_query(
    db: Session = Depends(get_db),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer_optional),
    token: Optional[str] = Query(
        None,
        description="JWT for MJPEG/img tags that cannot send Authorization header",
    ),
) -> User:
    """
    Same as get_current_user but accepts token from `Authorization: Bearer` **or** `?token=`.
    """
    raw = (token or "").strip() or (bearer.credentials if bearer else None)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = decode_access_token(raw)
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Lumicams super admin or organization admin (manage cameras, users in scope, settings).
    """
    if current_user.role not in (RoleEnum.super_admin, RoleEnum.org_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )
    return current_user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Verify email/password credentials.

    Returns:
        User instance on success, None on failure.
    """
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
