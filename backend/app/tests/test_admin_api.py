from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.main import app
from app.models.access_control import AuditLog
from app.services.audit_service import record_audit_event


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
