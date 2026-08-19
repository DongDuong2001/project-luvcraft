from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser
from app.models.access_control import ApiKey
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse
from app.services.api_key_service import generate_api_key
from app.services.audit_service import record_audit_event
from app.services.authorization_service import RoleChecker


router = APIRouter(prefix="/api-keys", tags=["api-keys"])
require_api_key_user = RoleChecker({"admin", "analyst", "client"})


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_api_key_user),
    db: Session = Depends(get_db),
):
    raw_key, key_prefix, key_hash = generate_api_key()
    key = ApiKey(
        user_id=current_user.user_id,
        key_name=payload.key_name.strip(),
        key_prefix=key_prefix,
        key_hash=key_hash,
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days),
    )
    db.add(key)
    record_audit_event(
        db=db,
        actor=current_user,
        action_type="API_KEY_CREATED",
        resource_type="api_key",
        new_state={"key_name": key.key_name, "key_prefix": key.key_prefix},
        request=request,
    )
    db.commit()
    db.refresh(key)
    key_response = ApiKeyResponse.model_validate(key, from_attributes=True)
    return ApiKeyCreatedResponse(
        **key_response.model_dump(),
        raw_key=raw_key,
    )


@router.get("", response_model=list[ApiKeyResponse])
def list_api_keys(
    current_user: CurrentUser = Depends(require_api_key_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ApiKey)
        .filter(ApiKey.user_id == current_user.user_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: UUID,
    request: Request,
    current_user: CurrentUser = Depends(require_api_key_user),
    db: Session = Depends(get_db),
):
    query = db.query(ApiKey).filter(ApiKey.key_id == key_id)
    if current_user.role != "admin":
        query = query.filter(ApiKey.user_id == current_user.user_id)
    key = query.first()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    key.is_active = False
    record_audit_event(
        db=db,
        actor=current_user,
        action_type="API_KEY_REVOKED",
        resource_type="api_key",
        resource_id=str(key.key_id),
        old_state={"is_active": True, "key_prefix": key.key_prefix},
        new_state={"is_active": False, "key_prefix": key.key_prefix},
        request=request,
    )
    db.commit()
