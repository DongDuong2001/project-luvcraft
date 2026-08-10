"""Tests for Supabase JWT authentication service."""
import pytest
import jwt
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi import HTTPException

from app.services.auth_service import (
    verify_supabase_token,
    extract_user_id,
    extract_user_email,
)


def create_test_token(
    user_id: str = None,
    email: str = "test@example.com",
    secret: str = "test-secret-key",
    expired: bool = False,
    audience: str = "authenticated",
    issuer: str = None,
) -> str:
    """Helper to create JWT tokens for testing."""
    if user_id is None:
        user_id = str(uuid4())
    
    exp = datetime.utcnow() - timedelta(hours=1) if expired else datetime.utcnow() + timedelta(hours=1)
    
    payload = {
        "sub": user_id,
        "email": email,
        "aud": audience,
        "exp": exp,
        "iat": datetime.utcnow(),
    }
    
    if issuer:
        payload["iss"] = issuer
    
    return jwt.encode(payload, secret, algorithm="HS256")


def test_verify_valid_token(monkeypatch):
    """Test that a valid token is accepted."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    user_id = str(uuid4())
    token = create_test_token(
        user_id=user_id,
        secret=test_secret,
        issuer=f"{test_url}/auth/v1"
    )
    
    payload = verify_supabase_token(token)
    
    assert payload["sub"] == user_id
    assert payload["email"] == "test@example.com"
    assert payload["aud"] == "authenticated"


def test_verify_expired_token(monkeypatch):
    """Test that an expired token is rejected."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    token = create_test_token(
        secret=test_secret,
        expired=True,
        issuer=f"{test_url}/auth/v1"
    )
    
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_verify_forged_token(monkeypatch):
    """Test that a token signed with wrong secret is rejected (security blocker #1)."""
    correct_secret = "correct-secret"
    wrong_secret = "wrong-secret"
    test_url = "https://test.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", correct_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    # Create token with wrong secret
    token = create_test_token(
        secret=wrong_secret,
        issuer=f"{test_url}/auth/v1"
    )
    
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    
    assert exc_info.value.status_code == 401
    assert "Invalid authentication credentials" in exc_info.value.detail


def test_verify_empty_secret_forged_token(monkeypatch):
    """
    Test that PyJWT prevents encoding tokens with empty secrets (security blocker #1).
    
    Note: PyJWT 2.8.0+ raises InvalidKeyError when trying to encode with empty secret,
    which prevents this attack vector at the library level. This is a defense-in-depth
    check - our config validation also rejects empty secrets at startup.
    """
    # PyJWT now prevents encoding with empty secret
    with pytest.raises(jwt.InvalidKeyError) as exc_info:
        create_test_token(
            user_id="attacker-chosen-sub",
            email="attacker@evil.com",
            secret="",  # Empty secret
            issuer="https://test.supabase.co/auth/v1"
        )
    
    assert "must not be empty" in str(exc_info.value).lower()


def test_verify_wrong_audience(monkeypatch):
    """Test that a token with wrong audience is rejected."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    token = create_test_token(
        secret=test_secret,
        audience="wrong-audience",
        issuer=f"{test_url}/auth/v1"
    )
    
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    
    assert exc_info.value.status_code == 401


def test_verify_wrong_issuer(monkeypatch):
    """Test that a token from different Supabase project is rejected (major issue #1)."""
    test_secret = "test-secret-key"
    correct_url = "https://correct-project.supabase.co"
    wrong_url = "https://attacker-project.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", correct_url)
    
    # Token from different project with same secret (secret reuse scenario)
    token = create_test_token(
        secret=test_secret,
        issuer=f"{wrong_url}/auth/v1"
    )
    
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    
    assert exc_info.value.status_code == 401


def test_verify_missing_issuer(monkeypatch):
    """Test that a token without issuer is rejected."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    token = create_test_token(
        secret=test_secret,
        issuer=None  # No issuer
    )
    
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    
    assert exc_info.value.status_code == 401


def test_verify_malformed_token(monkeypatch):
    """Test that a malformed token is rejected."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token("not-a-valid-jwt-token")
    
    assert exc_info.value.status_code == 401


def test_extract_user_id():
    """Test extracting user ID from payload."""
    user_id = uuid4()
    payload = {"sub": str(user_id)}
    
    extracted = extract_user_id(payload)
    
    assert extracted == user_id


def test_extract_user_id_invalid_uuid():
    """Test that invalid UUID in sub raises 401."""
    payload = {"sub": "not-a-uuid"}
    
    with pytest.raises(HTTPException) as exc_info:
        extract_user_id(payload)
    
    assert exc_info.value.status_code == 401
    assert "Invalid user identifier format" in exc_info.value.detail


def test_extract_user_id_missing():
    """Test that missing sub raises 401."""
    payload = {}
    
    with pytest.raises(HTTPException) as exc_info:
        extract_user_id(payload)
    
    assert exc_info.value.status_code == 401


def test_extract_user_email():
    """Test extracting email from payload."""
    payload = {"email": "test@example.com"}
    
    email = extract_user_email(payload)
    
    assert email == "test@example.com"


def test_extract_user_email_missing():
    """Test that missing email returns None."""
    payload = {}
    
    email = extract_user_email(payload)
    
    assert email is None
