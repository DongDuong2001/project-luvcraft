from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

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


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None
) -> CurrentUser:
    """
    Extract and verify current user from Supabase JWT.
    Checks the HTTPOnly cookie "access_token" first, and falls back to the
    Authorization header second.
    """
    token = None
    
    # 1. Check HTTPOnly cookies
    if "access_token" in request.cookies:
        token = request.cookies["access_token"]
    
    # 2. Fall back to Authorization header (e.g. for API testing, CLI, swagger)
    elif credentials is not None:
        token = credentials.credentials
        
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_supabase_token(token)
    user_id = extract_user_id(payload)
    email = extract_user_email(payload)

    return CurrentUser(user_id=user_id, email=email)


def get_current_user_optional(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None
) -> CurrentUser | None:
    """
    Get current user if token provided in cookie or header, None otherwise.
    """
    token = None
    if "access_token" in request.cookies:
        token = request.cookies["access_token"]
    elif credentials is not None:
        token = credentials.credentials

    if not token:
        return None

    try:
        payload = verify_supabase_token(token)
        user_id = extract_user_id(payload)
        email = extract_user_email(payload)
        return CurrentUser(user_id=user_id, email=email)
    except HTTPException:
        return None
