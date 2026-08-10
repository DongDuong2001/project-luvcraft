#!/usr/bin/env python3
"""
Test script for Supabase authentication.

Usage:
    # Sign up a test user
    python scripts/test_auth.py signup test@example.com password123
    
    # Sign in and get token
    python scripts/test_auth.py login test@example.com password123
    
    # Test API with token
    python scripts/test_auth.py test-api <access_token>
"""
import sys
import httpx
from supabase import create_client, Client

# Add parent directory to path for imports
sys.path.insert(0, "/Users/hoquanghuy/Documents/GitHub/project-luvcraft/backend")
from app.core.config import settings


def get_supabase_client() -> Client:
    """Create Supabase client."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def signup_user(email: str, password: str):
    """Sign up a new test user."""
    supabase = get_supabase_client()
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
        })
        print("✅ User signed up successfully!")
        print(f"User ID: {response.user.id}")
        print(f"Email: {response.user.email}")
        if response.session:
            print(f"\n🔑 Access Token:\n{response.session.access_token}\n")
            print("⚠️  Check your email to confirm account!")
        return response
    except Exception as e:
        print(f"❌ Signup failed: {e}")
        return None


def login_user(email: str, password: str):
    """Sign in and get access token."""
    supabase = get_supabase_client()
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        print("✅ Login successful!")
        print(f"User ID: {response.user.id}")
        print(f"Email: {response.user.email}")
        print(f"\n🔑 Access Token (valid for {response.session.expires_in}s):")
        print(response.session.access_token)
        print(f"\n📋 Copy this token to test API calls:\n")
        print(f"export TOKEN='{response.session.access_token}'")
        return response
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None


def test_api_with_token(token: str):
    """Test FastAPI endpoint with token."""
    print("🧪 Testing API with token...")
    
    # Test health endpoint (no auth required)
    print("\n1. Testing public health endpoint...")
    response = httpx.get("http://localhost:8000/health/db")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Test protected endpoint without token (should fail)
    print("\n2. Testing protected endpoint WITHOUT token (should fail)...")
    try:
        response = httpx.get("http://localhost:8000/api/v1/runs")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Expected error: {e}")
    
    # Test protected endpoint with token (should work)
    print("\n3. Testing protected endpoint WITH token (should work)...")
    try:
        response = httpx.get(
            "http://localhost:8000/api/v1/runs",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Authentication successful!")
            print(f"   Response: {response.json()}")
        else:
            print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1]
    
    if command == "signup" and len(sys.argv) == 4:
        email, password = sys.argv[2], sys.argv[3]
        signup_user(email, password)
    
    elif command == "login" and len(sys.argv) == 4:
        email, password = sys.argv[2], sys.argv[3]
        login_user(email, password)
    
    elif command == "test-api" and len(sys.argv) == 3:
        token = sys.argv[2]
        test_api_with_token(token)
    
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
