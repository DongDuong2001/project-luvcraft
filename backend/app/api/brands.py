from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models.brand import BrandProfile
from app.schemas.brand import BrandProfileCreate, BrandProfileResponse, BrandProfileUpdate
from app.services.authorization_service import GLOBAL_ROLES, RoleChecker


router = APIRouter(prefix="/brands", tags=["brands"])


def _visible_brand(brand_id: UUID, current_user: CurrentUser, db: Session) -> BrandProfile:
    brand = db.query(BrandProfile).filter(BrandProfile.brand_id == brand_id).first()
    if brand is None or (current_user.role not in GLOBAL_ROLES and current_user.brand_id != brand_id):
        raise HTTPException(status_code=404, detail="Brand profile not found")
    return brand


@router.get("", response_model=list[BrandProfileResponse])
def list_visible_brands(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(BrandProfile)
    if current_user.role not in GLOBAL_ROLES:
        if current_user.brand_id is None:
            return []
        query = query.filter(BrandProfile.brand_id == current_user.brand_id)
    return query.order_by(BrandProfile.brand_name).all()


@router.get("/{brand_id}", response_model=BrandProfileResponse)
def get_brand(brand_id: UUID, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _visible_brand(brand_id, current_user, db)


@router.post("", response_model=BrandProfileResponse, status_code=status.HTTP_201_CREATED)
def create_brand(payload: BrandProfileCreate, _: CurrentUser = Depends(RoleChecker(GLOBAL_ROLES)), db: Session = Depends(get_db)):
    brand = BrandProfile(**payload.model_dump())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.patch("/{brand_id}", response_model=BrandProfileResponse)
def update_brand(brand_id: UUID, payload: BrandProfileUpdate, current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    brand = _visible_brand(brand_id, current_user, db)
    if current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot edit brand profiles")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    db.commit()
    db.refresh(brand)
    return brand
