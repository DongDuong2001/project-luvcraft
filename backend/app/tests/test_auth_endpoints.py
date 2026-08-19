import pytest
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import jwt

from app.main import app
from app.core.config import settings
from app.deps import get_current_user, CurrentUser


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_session_endpoint_sets_cookie(client, monkeypatch):
    """Test that the /auth/session endpoint validates the token and sets the cookie."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"
    
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    
    user_id = str(uuid4())
    payload = {
        "sub": user_id,
        "email": "test@example.com",
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "iss": f"{test_url}/auth/v1",
    }
    token = jwt.encode(payload, test_secret, algorithm="HS256")
    
    # Verify setting the cookie
    response = client.post("/api/v1/auth/session", json={"access_token": token})
    assert response.status_code == 200
    assert response.json() == {"status": "session_active"}
    
    cookie = response.cookies.get("access_token")
    assert cookie == token


def test_auth_logout_clears_cookie(client):
    """Test that the /auth/logout endpoint clears the cookie."""
    # Seed a cookie
    client.cookies.set("access_token", "fake-token-value")
    
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    
    # Cookie should be deleted (value is empty/cleared or cookie is deleted)
    cookie = response.cookies.get("access_token")
    assert cookie is None or cookie == ""


def test_auth_me_returns_authorization_context(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "test@example.com"
    assert body["role"] == "viewer"
    assert body["brand_id"] is None
    assert body["is_active"] is True
    assert body["auth_method"] == "bearer"


def test_dev_login_endpoint(client, monkeypatch):
    """Test that dev-login sets a valid developer cookie when DEBUG is enabled."""
    test_secret = "test-secret-key"
    test_url = "https://test.supabase.co"

    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.services.auth_service.settings.SUPABASE_URL", test_url)
    monkeypatch.setattr("app.api.auth.settings.SUPABASE_JWT_SECRET", test_secret)
    monkeypatch.setattr("app.api.auth.settings.SUPABASE_URL", test_url)
    monkeypatch.setattr("app.api.auth.settings.DEBUG", True)

    response = client.post("/api/v1/auth/dev-login")
    assert response.status_code == 200
    assert response.json()["status"] == "dev_session_active"
    
    token = response.cookies.get("access_token")
    assert token is not None
    
    # Decode token to verify contents
    decoded = jwt.decode(
        token,
        test_secret,
        algorithms=["HS256"],
        audience="authenticated",
        issuer=f"{test_url}/auth/v1",
    )
    assert decoded["email"] == "dev@example.com"
    assert decoded["sub"] == "00000000-0000-0000-0000-000000000000"


def test_dev_login_gated_in_production(client, monkeypatch):
    """Dev-login must be invisible (404) and mint no token when DEBUG is False."""
    monkeypatch.setattr("app.api.auth.settings.DEBUG", False)
    monkeypatch.setattr(
        "app.api.auth.settings.SUPABASE_JWT_SECRET", "production-shaped-secret-value"
    )

    response = client.post("/api/v1/auth/dev-login")
    assert response.status_code == 404
    # No session cookie should be minted.
    assert response.cookies.get("access_token") is None
