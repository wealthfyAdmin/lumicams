"""
routers/users.py
----------------
User management endpoints.

  POST   /api/users/          – Create user (Admin only)
  GET    /api/users/           – List all users (Admin only)
  GET    /api/users/me         – Get current authenticated user
  GET    /api/users/{id}       – Get user by ID (Admin only)
  PATCH  /api/users/{id}       – Update user (Admin only)
  DELETE /api/users/{id}       – Delete user (Admin only)
  POST   /api/auth/login       – Issue JWT access token
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
)
from app.database import get_db
from app.models import Organization, RoleEnum, User
from app.schema import Token, UserCreate, UserOut, UserUpdate
from app.tenancy import is_super_admin, user_manageable, users_query_for_admin

router = APIRouter()


def _resolve_org_for_create(db: Session, admin: User, payload: UserCreate) -> int | None:
    """Returns organization_id for new user, or None for super_admin role."""
    if payload.role == RoleEnum.super_admin:
        if not is_super_admin(admin):
            raise HTTPException(status_code=403, detail="Only platform admin can create super_admin users.")
        return None
    if is_super_admin(admin):
        oid = payload.organization_id
        if oid is None:
            raise HTTPException(status_code=422, detail="organization_id is required for org users.")
        org = db.query(Organization).filter(Organization.id == oid).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found.")
        return oid
    if admin.organization_id is None:
        raise HTTPException(status_code=400, detail="Organization admin is not assigned to an organization.")
    if payload.organization_id is not None and payload.organization_id != admin.organization_id:
        raise HTTPException(status_code=403, detail="Cannot assign users to another organization.")
    return admin.organization_id


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=Token, tags=["Auth"])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate with email (username field) + password.
    Returns a JWT bearer token.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = {
        "sub": user.email,
        "user_id": user.id,
        "role": user.role.value,
        "organization_id": user.organization_id,
    }
    token = create_access_token(data=token_data)
    return Token(access_token=token)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


@router.post("/users/", response_model=UserOut, status_code=201, tags=["Users"])
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create a new platform user. Requires Admin role."""
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{payload.email}' is already registered.",
        )
    org_id = _resolve_org_for_create(db, admin, payload)
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        organization_id=org_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/me", response_model=UserOut, tags=["Users"])
def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user


@router.get("/users/", response_model=list[UserOut], tags=["Users"])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List users visible to this administrator."""
    return users_query_for_admin(db, admin).order_by(User.id.asc()).all()


@router.get("/users/{user_id}", response_model=UserOut, tags=["Users"])
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Fetch a single user by ID. Requires Admin role."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user_manageable(admin, user):
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.patch("/users/{user_id}", response_model=UserOut, tags=["Users"])
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update user fields. Requires Admin role."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user_manageable(admin, user):
        raise HTTPException(status_code=404, detail="User not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))
    if "role" in update_data:
        new_role = update_data["role"]
        if new_role == RoleEnum.super_admin and not is_super_admin(admin):
            raise HTTPException(status_code=403, detail="Cannot assign super_admin role.")
        if not is_super_admin(admin) and new_role == RoleEnum.super_admin:
            raise HTTPException(status_code=403, detail="Cannot promote to platform admin.")
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204, tags=["Users"])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a user. Requires Admin role. Cannot delete yourself."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user_manageable(current_user, user):
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role == RoleEnum.super_admin and not is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="Cannot delete this user.")
    db.delete(user)
    db.commit()
