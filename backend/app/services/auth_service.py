"""Supabase JWT verification and user extraction."""
import jwt
import logging
from typing import Optional
from uuid import UUID
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


# Allowed signing algorithms for Supabase tokens
ALLOWED_SYMMETRIC_ALGORITHMS = {"HS256"}
ALLOWED_ASYMMETRIC_ALGORITHMS = {"ES256", "RS256"}
ALLOWED_ALGORITHMS = ALLOWED_SYMMETRIC_ALGORITHMS | ALLOWED_ASYMMETRIC_ALGORITHMS

_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def get_jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    """Get or create a cached PyJWKClient for the given JWKS URL."""
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = jwt.PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=3600,
        )
    return _jwks_clients[jwks_url]


def verify_supabase_token(token: str) -> dict:
    """
    Verify Supabase JWT and return payload.
    
    Supports:
    - Asymmetric keys (ES256, RS256) resolved via Supabase project JWKS endpoint
    - Symmetric keys (HS256) resolved via SUPABASE_JWT_SECRET
    
    Args:
        token: JWT access token from Supabase Auth
        
    Returns:
        Decoded JWT payload containing user information
        
    Raises:
        HTTPException: If token is invalid, expired, or uses an unsupported algorithm
    """
    if not settings.SUPABASE_URL:
        logger.error("SUPABASE_URL is not configured; refusing to verify tokens")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured",
        )
    
    try:
        header = jwt.get_unverified_header(token)
    except Exception as e:
        logger.warning(f"Invalid JWT header: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg")
    if not alg or alg not in ALLOWED_ALGORITHMS:
        logger.warning(f"Disallowed or missing JWT algorithm: {alg!r}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"

    try:
        if alg in ALLOWED_ASYMMETRIC_ALGORITHMS:
            jwks_url = f"{issuer}/.well-known/jwks.json"
            jwks_client = get_jwks_client(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                issuer=issuer,
            )
        elif alg in ALLOWED_SYMMETRIC_ALGORITHMS:
            # Fail-closed guard: reject empty JWT secret at point of use
            if not settings.SUPABASE_JWT_SECRET:
                logger.error("SUPABASE_JWT_SECRET is not configured; refusing to verify HS256 tokens")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication is not configured",
                )
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=[alg],
                audience="authenticated",
                issuer=issuer,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWKClientError as e:
        logger.warning(f"JWKS key resolution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidKeyError as e:
        logger.exception(f"JWT key configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service configuration error",
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
        logger.warning("Malformed user identifier in token sub claim: %r", user_id_str)
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
