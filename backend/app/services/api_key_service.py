import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.access_control import ApiKey, UserProfile


API_KEY_PREFIX = "pluto_live_"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    raw_key = f"{API_KEY_PREFIX}{secrets.token_hex(32)}"
    return raw_key, raw_key[:24], hash_api_key(raw_key)


def authenticate_api_key(raw_key: str, db: Session) -> UserProfile:
    if not raw_key.startswith(API_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    incoming_hash = hash_api_key(raw_key)
    key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == incoming_hash, ApiKey.is_active.is_(True))
        .first()
    )
    if key is None or not hmac.compare_digest(key.key_hash, incoming_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    now = datetime.now(timezone.utc)
    expires_at = key.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key has expired")

    profile = db.query(UserProfile).filter(UserProfile.user_id == key.user_id).first()
    if profile is None or not profile.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    return profile
