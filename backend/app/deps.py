from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.profile_service import get_or_create_user_profile
from app.services.api_key_service import authenticate_api_key
from app.services.auth_service import (
    verify_supabase_token,
    extract_user_id,
    extract_user_email,
)

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    """Current authenticated user context."""

    user_id: UUID
    email: str | None = None
    role: Literal["admin", "analyst", "client", "viewer"] = "viewer"
    brand_id: UUID | None = None
    is_active: bool = True
    auth_method: Literal["cookie", "bearer", "api_key"] = "bearer"


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: Session = Depends(get_db),
) -> CurrentUser:
    """
    Extract and verify current user from Supabase JWT.
    Checks the HTTPOnly cookie "access_token" first, and falls back to the
    Authorization header second.
    """
    token = None
    auth_method: Literal["cookie", "bearer"] = "bearer"
    
    # 1. Check HTTPOnly cookies
    if "access_token" in request.cookies:
        token = request.cookies["access_token"]
        auth_method = "cookie"
    
    # 2. Fall back to Authorization header (e.g. for API testing, CLI, swagger)
    elif credentials is not None:
        token = credentials.credentials
        
    api_key = request.headers.get("X-API-KEY")
    if not token and api_key:
        profile = authenticate_api_key(api_key, db)
        return CurrentUser(
            user_id=profile.user_id,
            email=profile.email,
            role=profile.role,
            brand_id=profile.brand_id,
            is_active=profile.is_active,
            auth_method="api_key",
        )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_supabase_token(token)
    user_id = extract_user_id(payload)
    email = extract_user_email(payload)
    profile = get_or_create_user_profile(user_id=user_id, email=email, db=db)

    if not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return CurrentUser(
        user_id=profile.user_id,
        email=profile.email,
        role=profile.role,
        brand_id=profile.brand_id,
        is_active=profile.is_active,
        auth_method=auth_method,
    )


def get_current_user_optional(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: Session = Depends(get_db),
) -> CurrentUser | None:
    """
    Get current user if token provided in cookie or header, None otherwise.
    """
    token = None
    if "access_token" in request.cookies:
        token = request.cookies["access_token"]
    elif credentials is not None:
        token = credentials.credentials

    api_key = request.headers.get("X-API-KEY")
    if not token and api_key:
        try:
            profile = authenticate_api_key(api_key, db)
            return CurrentUser(
                user_id=profile.user_id,
                email=profile.email,
                role=profile.role,
                brand_id=profile.brand_id,
                is_active=profile.is_active,
                auth_method="api_key",
            )
        except HTTPException:
            return None

    if not token:
        return None

    try:
        payload = verify_supabase_token(token)
        user_id = extract_user_id(payload)
        email = extract_user_email(payload)
        profile = get_or_create_user_profile(user_id=user_id, email=email, db=db)
        if not profile.is_active:
            return None
        return CurrentUser(
            user_id=profile.user_id,
            email=profile.email,
            role=profile.role,
            brand_id=profile.brand_id,
            is_active=profile.is_active,
            auth_method="cookie" if "access_token" in request.cookies else "bearer",
        )
    except HTTPException:
        return None
