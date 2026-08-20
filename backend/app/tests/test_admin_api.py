from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.main import app
from app.models.access_control import AuditLog, UserProfile
from app.services.audit_service import record_audit_event


def _make_profile(user_id, *, role="admin", is_active=True):
    return UserProfile(
        user_id=user_id,
        email=f"user-{user_id}@pluto.studio",
        full_name="Test User",
        role=role,
        brand_id=None,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _db_returning(profile):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = profile
    return db


def test_non_admin_cannot_list_users():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid4(),
        email="analyst@pluto.studio",
        role="analyst",
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    db.query.assert_not_called()


def test_audit_event_joins_callers_transaction_without_commit():
    db = MagicMock()
    actor = CurrentUser(
        user_id=uuid4(),
        email="admin@pluto.studio",
        role="admin",
    )

    entry = record_audit_event(
        db=db,
        actor=actor,
        action_type="USER_ACCESS_UPDATED",
        resource_type="user_profile",
        resource_id=str(uuid4()),
        old_state={"role": "viewer"},
        new_state={"role": "client"},
    )

    assert isinstance(entry, AuditLog)
    assert entry.actor_id == actor.user_id
    assert entry.actor_email == actor.email
    assert entry.old_state == {"role": "viewer"}
    assert entry.new_state == {"role": "client"}
    db.add.assert_called_once_with(entry)
    db.commit.assert_not_called()


def test_admin_cannot_demote_own_role():
    admin_id = uuid4()
    profile = _make_profile(admin_id, role="admin")
    db = _db_returning(profile)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=admin_id,
        email="admin@pluto.studio",
        role="admin",
    )
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{admin_id}", json={"role": "viewer"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Administrators cannot change their own role"
    }
    # The role must not have been mutated before failing closed.
    assert profile.role == "admin"
    db.commit.assert_not_called()


def test_admin_cannot_deactivate_own_account():
    admin_id = uuid4()
    profile = _make_profile(admin_id, role="admin")
    db = _db_returning(profile)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=admin_id,
        email="admin@pluto.studio",
        role="admin",
    )
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{admin_id}", json={"is_active": False}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Administrators cannot deactivate their own account"
    }
    db.commit.assert_not_called()


def test_admin_can_change_another_users_role():
    admin_id = uuid4()
    target_id = uuid4()
    profile = _make_profile(target_id, role="viewer")
    db = _db_returning(profile)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=admin_id,
        email="admin@pluto.studio",
        role="admin",
    )
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{target_id}", json={"role": "client"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["role"] == "client"
    assert profile.role == "client"
    db.commit.assert_called_once()
