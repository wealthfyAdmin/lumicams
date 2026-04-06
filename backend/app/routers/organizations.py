"""Organizations (tenants) — Lumicams super admin only for create/delete."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from sqlalchemy import func

from app.models import Camera, Organization, User
from app.schema import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.tenancy import is_super_admin, require_super_admin

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("/", response_model=OrganizationOut, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    _sa: User = Depends(require_super_admin),
):
    slug = (payload.slug or "").strip() or None
    if slug:
        if db.query(Organization).filter(Organization.slug == slug).first():
            raise HTTPException(status_code=409, detail="Slug already in use.")
    org = Organization(name=payload.name.strip(), slug=slug, is_active=True)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.get("/", response_model=list[OrganizationOut])
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    return db.query(Organization).order_by(Organization.id.asc()).all()


@router.get("/current", response_model=OrganizationOut)
def current_organization(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Organization admins and operators: their single org."""
    if is_super_admin(current_user):
        raise HTTPException(
            status_code=400,
            detail="Platform admin: use GET /organizations/ to list all organizations.",
        )
    if current_user.organization_id is None:
        raise HTTPException(status_code=400, detail="User is not assigned to an organization.")
    org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return org


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if not is_super_admin(current_user):
        if current_user.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Organization not found.")
    return org


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: int,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    data = payload.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"]:
        other = (
            db.query(Organization)
            .filter(Organization.slug == data["slug"], Organization.id != org_id)
            .first()
        )
        if other:
            raise HTTPException(status_code=409, detail="Slug already in use.")
    for k, v in data.items():
        setattr(org, k, v)
    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=204)
def delete_organization(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    n_users = db.query(func.count(User.id)).filter(User.organization_id == org_id).scalar() or 0
    n_cams = db.query(func.count(Camera.id)).filter(Camera.organization_id == org_id).scalar() or 0
    if n_users or n_cams:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Remove or reassign users and cameras before deleting this organization.",
        )
    db.delete(org)
    db.commit()
