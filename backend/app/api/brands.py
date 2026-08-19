from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.models.brand import BrandProfile
from app.schemas.brand import BrandProfileResponse
from app.services.authorization_service import GLOBAL_ROLES


router = APIRouter(prefix="/brands", tags=["brands"])


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
