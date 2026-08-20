import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.core.config import settings
from app.services.auth_service import verify_supabase_token
from app.deps import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


class SessionPayload(BaseModel):
    access_token: str


class CurrentUserResponse(BaseModel):
    user_id: str
    email: str | None
    role: str
    brand_id: str | None
    is_active: bool
    auth_method: str


@router.get("/auth/me", response_model=CurrentUserResponse)
def get_auth_profile(current_user: CurrentUser = Depends(get_current_user)):
    """Return the server-authoritative session and authorization context."""
    return CurrentUserResponse(
        user_id=str(current_user.user_id),
        email=current_user.email,
        role=current_user.role,
        brand_id=str(current_user.brand_id) if current_user.brand_id else None,
        is_active=current_user.is_active,
        auth_method=current_user.auth_method,
    )


@router.post("/auth/session")
def set_auth_session(payload: SessionPayload, response: Response):
    """
    Verify the Supabase JWT sent by the frontend, and set it as a secure HTTPOnly cookie.
    """
    try:
        # Verify that the token is valid before setting the cookie
        verify_supabase_token(payload.access_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Token verification failed during session set: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session",
        )

    # Set secure HTTPOnly cookie
    response.set_cookie(
        key="access_token",
        value=payload.access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=3600,  # 1 hour matching Supabase token duration
    )
    return {"status": "session_active"}


@router.post("/auth/logout")
def logout(response: Response):
    """
    Clear the session cookie to log out the user.
    """
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return {"status": "logged_out"}


@router.post("/auth/dev-login")
def dev_login(response: Response):
    """
    Developer bypass login route to set a mock JWT for local development.
    Only available when DEBUG is enabled; returns 404 in production so the
    endpoint is invisible.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Create a mock token
    import jwt
    from datetime import datetime, timedelta, timezone

    mock_payload = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "email": "dev@example.com",
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "iss": f"{settings.SUPABASE_URL}/auth/v1",
    }

    token = jwt.encode(mock_payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=3600,
    )
    return {"status": "dev_session_active"}
