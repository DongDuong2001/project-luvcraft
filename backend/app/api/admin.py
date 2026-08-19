from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser
from app.models.access_control import AuditLog, BrandDomain, UserProfile
from app.models.brand import BrandProfile
from app.schemas.admin import (
    AuditLogResponse,
    BrandDomainCreate,
    BrandDomainResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.audit_service import record_audit_event
from app.services.authorization_service import RoleChecker


router = APIRouter(prefix="/admin", tags=["admin"])
require_admin = RoleChecker({"admin"})


def _profile_state(profile: UserProfile) -> dict:
    return {
        "role": profile.role,
        "brand_id": str(profile.brand_id) if profile.brand_id else None,
        "is_active": profile.is_active,
    }


@router.get("/users", response_model=list[UserProfileResponse])
def list_users(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(UserProfile)
        .order_by(UserProfile.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.patch("/users/{user_id}", response_model=UserProfileResponse)
def update_user_profile(
    user_id: UUID,
    payload: UserProfileUpdate,
    request: Request,
    admin_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user_id == admin_user.user_id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Administrators cannot deactivate their own account",
        )

    if payload.update_brand and payload.brand_id is not None:
        brand_exists = (
            db.query(BrandProfile)
            .filter(BrandProfile.brand_id == payload.brand_id)
            .first()
        )
        if brand_exists is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Brand not found")

    old_state = _profile_state(profile)
    if payload.role is not None:
        profile.role = payload.role
    if payload.update_brand:
        profile.brand_id = payload.brand_id
    if payload.is_active is not None:
        profile.is_active = payload.is_active

    new_state = _profile_state(profile)
    if new_state != old_state:
        record_audit_event(
            db=db,
            actor=admin_user,
            action_type="USER_ACCESS_UPDATED",
            resource_type="user_profile",
            resource_id=str(profile.user_id),
            old_state=old_state,
            new_state=new_state,
            request=request,
        )
        db.commit()
        db.refresh(profile)
    return profile


@router.get("/brand-domains", response_model=list[BrandDomainResponse])
def list_brand_domains(
    _: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(BrandDomain).order_by(BrandDomain.domain_name).all()


@router.post(
    "/brand-domains",
    response_model=BrandDomainResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_brand_domain(
    payload: BrandDomainCreate,
    request: Request,
    admin_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    brand = db.query(BrandProfile).filter(BrandProfile.brand_id == payload.brand_id).first()
    if brand is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Brand not found")

    domain = BrandDomain(brand_id=payload.brand_id, domain_name=payload.domain_name)
    db.add(domain)
    record_audit_event(
        db=db,
        actor=admin_user,
        action_type="BRAND_DOMAIN_CREATED",
        resource_type="brand_domain",
        new_state={
            "brand_id": str(payload.brand_id),
            "domain_name": payload.domain_name,
        },
        request=request,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email domain is already assigned",
        ) from exc
    db.refresh(domain)
    return domain


@router.delete("/brand-domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand_domain(
    domain_id: UUID,
    request: Request,
    admin_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    domain = db.query(BrandDomain).filter(BrandDomain.domain_id == domain_id).first()
    if domain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")

    old_state = {
        "brand_id": str(domain.brand_id),
        "domain_name": domain.domain_name,
    }
    db.delete(domain)
    record_audit_event(
        db=db,
        actor=admin_user,
        action_type="BRAND_DOMAIN_DELETED",
        resource_type="brand_domain",
        resource_id=str(domain_id),
        old_state=old_state,
        request=request,
    )
    db.commit()


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
