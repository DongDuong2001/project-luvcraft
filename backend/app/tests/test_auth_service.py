"""Tests for Supabase JWT authentication service."""
import pytest
import jwt
from datetime import datetime, timedelta, timezone
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
    
    exp = datetime.now(timezone.utc) - timedelta(hours=1) if expired else datetime.now(timezone.utc) + timedelta(hours=1)
    
    payload = {
        "sub": user_id,
        "email": email,
        "aud": audience,
        "exp": exp,
        "iat": datetime.now(timezone.utc),
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
    Test that verify_supabase_token rejects auth when secret is empty (security blocker #1).
    
    An attacker who can mint a JWT with an empty secret should not be able to authenticate.
    The guard at point-of-use prevents this attack vector.
    """
    test_url = "https://test.supabase.co"
    
    # Simulate production config with empty secret (misconfiguration or env var unset)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    # Attacker creates a forged token (using any secret, doesn't matter)
    token = create_test_token(
        user_id="attacker-chosen-sub",
        email="attacker@evil.com",
        secret="attacker-controlled-secret",
        issuer=f"{test_url}/auth/v1"
    )
    
    # Verification should fail-closed (refuse to verify with empty secret)
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)
    
    assert exc_info.value.status_code == 500
    assert "not configured" in exc_info.value.detail.lower()


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


def test_verify_valid_es256_token(monkeypatch):
    """Test verifying a valid ES256 token using mocked JWKS key."""
    from unittest.mock import MagicMock
    from cryptography.hazmat.primitives.asymmetric import ec

    test_url = "https://test.supabase.co"
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    user_id = str(uuid4())

    payload = {
        "sub": user_id,
        "email": "analyst@pluto.studio",
        "aud": "authenticated",
        "iss": f"{test_url}/auth/v1",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "key-1"})

    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    monkeypatch.setattr("app.services.auth_service.get_jwks_client", lambda url: mock_jwks_client)

    verified = verify_supabase_token(token)
    assert verified["sub"] == user_id
    assert verified["email"] == "analyst@pluto.studio"
    assert verified["aud"] == "authenticated"


def test_verify_disallowed_algorithm(monkeypatch):
    """Test that tokens using disallowed algorithms (e.g. HS384, none) are rejected."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)

    payload = {
        "sub": str(uuid4()),
        "email": "attacker@evil.com",
        "aud": "authenticated",
        "iss": f"{test_url}/auth/v1",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, test_secret, algorithm="HS384")

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)

    assert exc_info.value.status_code == 401
    assert "Invalid authentication credentials" in exc_info.value.detail


def test_verify_es256_jwks_resolution_error(monkeypatch):
    """Test that JWKS client error raises 401."""
    from unittest.mock import MagicMock
    from cryptography.hazmat.primitives.asymmetric import ec

    test_url = "https://test.supabase.co"
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)

    private_key = ec.generate_private_key(ec.SECP256R1())
    payload = {
        "sub": str(uuid4()),
        "aud": "authenticated",
        "iss": f"{test_url}/auth/v1",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "missing-kid"})

    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.side_effect = jwt.PyJWKClientError("Key not found in JWKS")
    monkeypatch.setattr("app.services.auth_service.get_jwks_client", lambda url: mock_jwks_client)

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_token(token)

    assert exc_info.value.status_code == 401

