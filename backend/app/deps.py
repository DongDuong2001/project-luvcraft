from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.services.auth_service import (
    verify_supabase_token,
    extract_user_id,
    extract_user_email,
)


# Security scheme for Swagger UI
security = HTTPBearer()


class CurrentUser(BaseModel):
    """Current authenticated user context."""

    user_id: UUID
    email: str | None = None


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
) -> CurrentUser:
    """
    Extract and verify current user from Supabase JWT.

    The frontend should include the token in Authorization header:
    Authorization: Bearer <supabase_access_token>

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        CurrentUser with user_id and email

    Raises:
        HTTPException: 401 if token is invalid or missing
    """
    token = credentials.credentials
    payload = verify_supabase_token(token)
    user_id = extract_user_id(payload)
    email = extract_user_email(payload)

    return CurrentUser(user_id=user_id, email=email)


def get_current_user_optional(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
    ]
) -> CurrentUser | None:
    """
    Get current user if token provided, None otherwise.

    Use this for public endpoints that can optionally track authenticated users.

    Args:
        credentials: HTTP Bearer token if provided, None otherwise

    Returns:
        CurrentUser if valid token provided, None otherwise
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        payload = verify_supabase_token(token)
        user_id = extract_user_id(payload)
        email = extract_user_email(payload)
        return CurrentUser(user_id=user_id, email=email)
    except HTTPException:
        return None
