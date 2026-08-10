"""Shared pytest fixtures for test suite."""
import pytest
from uuid import uuid4

from app.deps import get_current_user, CurrentUser


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    """
    Override authentication dependency for all tests.
    
    This prevents 401 errors in tests by providing a fake authenticated user.
    Tests can override this fixture if they need to test authentication.
    """
    def fake_current_user() -> CurrentUser:
        return CurrentUser(
            user_id=uuid4(),
            email="test@example.com"
        )
    
    from app import main
    main.app.dependency_overrides[get_current_user] = fake_current_user
    
    yield
    
    # Clean up after test
    main.app.dependency_overrides.clear()
