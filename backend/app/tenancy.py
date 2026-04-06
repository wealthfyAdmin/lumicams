"""
Tenant scoping helpers for multi-organization RBAC.

Roles:
  - super_admin: Lumicams platform — all organizations.
  - org_admin / operator: restricted to organization_id on the User row.
"""

from __future__ import annotations

from typing import Optional, TypeVar

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Query, Session

from app.auth import get_current_user
from app.models import Alert, Camera, Organization, RoleEnum, User

T = TypeVar("T")


def is_super_admin(user: User) -> bool:
    return user.role == RoleEnum.super_admin


def user_org_id(user: User) -> Optional[int]:
    return user.organization_id


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lumicams platform administrator privileges required.",
        )
    return current_user


def require_org_admin(current_user: User = Depends(get_current_user)) -> User:
    if is_super_admin(current_user):
        return current_user
    if current_user.role == RoleEnum.org_admin:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Organization administrator privileges required.",
    )


def require_org_admin_or_super(current_user: User = Depends(get_current_user)) -> User:
    """Super admin or org admin (not plain operator)."""
    if is_super_admin(current_user):
        return current_user
    if current_user.role == RoleEnum.org_admin:
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Administrator privileges required.",
    )


def cameras_query_for_user(db: Session, user: User) -> Query:
    q = db.query(Camera)
    if is_super_admin(user):
        return q
    if user.organization_id is None:
        return q.filter(Camera.id == -1)
    return q.filter(Camera.organization_id == user.organization_id)


def alerts_query_for_user(db: Session, user: User) -> Query:
    q = db.query(Alert).join(Camera, Alert.camera_id == Camera.id)
    if is_super_admin(user):
        return q
    if user.organization_id is None:
        return q.filter(Alert.id == -1)
    return q.filter(Camera.organization_id == user.organization_id)


def camera_accessible(user: User, camera: Camera) -> bool:
    if is_super_admin(user):
        return True
    if user.organization_id is None:
        return False
    return camera.organization_id == user.organization_id


def ensure_camera_access(user: User, camera: Camera) -> None:
    if not camera_accessible(user, camera):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found.")


def org_accessible(user: User, org: Organization) -> bool:
    if is_super_admin(user):
        return True
    if user.organization_id is None:
        return False
    return org.id == user.organization_id


def ensure_org_access(user: User, org: Organization) -> None:
    if not org_accessible(user, org):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")


def users_query_for_admin(db: Session, admin: User) -> Query:
    q = db.query(User)
    if is_super_admin(admin):
        return q
    if admin.organization_id is None:
        return q.filter(User.id == -1)
    return q.filter(User.organization_id == admin.organization_id)


def user_manageable(admin: User, target: User) -> bool:
    if admin.id == target.id:
        return True
    if is_super_admin(admin):
        return True
    if admin.role != RoleEnum.org_admin:
        return False
    if target.role == RoleEnum.super_admin:
        return False
    if admin.organization_id is None or target.organization_id != admin.organization_id:
        return False
    return True
