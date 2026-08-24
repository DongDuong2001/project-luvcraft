from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.deps import CurrentUser
from app.services.authorization_service import (
    RoleChecker,
    can_read_run,
    get_authorized_run,
    require_run_write_permission,
    resolve_run_target_brand,
    scope_runs_query,
)


def user(role: str, brand_id=None) -> CurrentUser:
    return CurrentUser(
        user_id=uuid4(),
        email=f"{role}@example.com",
        role=role,
        brand_id=brand_id,
    )


@pytest.mark.parametrize("role", ["admin", "analyst"])
def test_global_roles_can_read_any_run(role):
    run = SimpleNamespace(target_brand_id=uuid4(), is_public_demo=False)
    assert can_read_run(run, user(role)) is True


@pytest.mark.parametrize("role", ["client", "viewer"])
def test_brand_roles_are_scoped_to_assigned_brand(role):
    brand_id = uuid4()
    other_brand_id = uuid4()

    assert can_read_run(
        SimpleNamespace(target_brand_id=brand_id, is_public_demo=False),
        user(role, brand_id),
    ) is True
    assert can_read_run(
        SimpleNamespace(target_brand_id=other_brand_id, is_public_demo=False),
        user(role, brand_id),
    ) is False


def test_unassigned_viewer_can_only_read_public_demo():
    viewer = user("viewer")
    assert can_read_run(SimpleNamespace(target_brand_id=None, is_public_demo=True), viewer)
    assert not can_read_run(SimpleNamespace(target_brand_id=None, is_public_demo=False), viewer)


def test_cross_tenant_run_is_reported_as_not_found():
    run = SimpleNamespace(target_brand_id=uuid4(), is_public_demo=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = run

    with pytest.raises(HTTPException) as exc_info:
        get_authorized_run(uuid4(), user("client", uuid4()), db)

    assert exc_info.value.status_code == 404


def test_scope_runs_query_uses_brand_for_client():
    query = MagicMock()
    scoped = MagicMock()
    query.filter.return_value = scoped

    assert scope_runs_query(query, user("client", uuid4())) is scoped
    query.filter.assert_called_once()


def test_scope_runs_query_leaves_global_query_unmodified():
    query = MagicMock()
    assert scope_runs_query(query, user("admin")) is query
    query.filter.assert_not_called()


def test_role_checker_rejects_disallowed_role():
    checker = RoleChecker({"admin"})
    with pytest.raises(HTTPException) as exc_info:
        checker(user("analyst"))
    assert exc_info.value.status_code == 403


def test_viewer_cannot_write_runs():
    with pytest.raises(HTTPException) as exc_info:
        require_run_write_permission(user("viewer"))
    assert exc_info.value.status_code == 403


def test_client_target_brand_is_server_authoritative():
    brand_id = uuid4()
    client = user("client", brand_id)
    assert resolve_run_target_brand(None, client) == brand_id

    with pytest.raises(HTTPException) as exc_info:
        resolve_run_target_brand(uuid4(), client)
    assert exc_info.value.status_code == 403


def test_unassigned_client_cannot_create_runs():
    with pytest.raises(HTTPException) as exc_info:
        resolve_run_target_brand(None, user("client"))
    assert exc_info.value.status_code == 403


def test_viewer_cannot_resolve_target_brand():
    with pytest.raises(HTTPException) as exc_info:
        resolve_run_target_brand(None, user("viewer"))
    assert exc_info.value.status_code == 403


@pytest.mark.parametrize("role", ["admin", "analyst"])
def test_global_writer_can_run_core_research_without_a_brand(role):
    assert resolve_run_target_brand(None, user(role)) is None


@pytest.mark.parametrize("role", ["admin", "analyst"])
def test_global_writer_keeps_explicit_target_brand(role):
    brand_id = uuid4()
    assert resolve_run_target_brand(brand_id, user(role)) == brand_id
