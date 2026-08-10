"""Supabase JWT verification and user extraction."""
import jwt
from typing import Optional
from uuid import UUID
from fastapi import HTTPException, status

from app.core.config import settings


def verify_supabase_token(token: str) -> dict:
    """
    Verify Supabase JWT and return payload.
    
    Args:
        token: JWT access token from Supabase Auth
        
    Returns:
        Decoded JWT payload containing user information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_user_id(token_payload: dict) -> UUID:
    """
    Extract and validate user_id from JWT payload.
    
    Args:
        token_payload: Decoded JWT payload from verify_supabase_token
        
    Returns:
        UUID of the authenticated user
        
    Raises:
        HTTPException: If user_id is missing or invalid
    """
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier",
        )
    
    try:
        return UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier format",
        )


def extract_user_email(token_payload: dict) -> Optional[str]:
    """
    Extract email from JWT payload.
    
    Args:
        token_payload: Decoded JWT payload from verify_supabase_token
        
    Returns:
        User's email address if present in token, None otherwise
    """
    return token_payload.get("email")
