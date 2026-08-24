from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.profile_service import (
    email_domain,
    get_or_create_user_profile,
    normalize_email,
    resolve_initial_access,
)


def test_normalize_email_and_extract_domain():
    assert normalize_email("  Person@Example.COM ") == "person@example.com"
    assert email_domain("Person@Example.COM") == "example.com"


@pytest.mark.parametrize("email", ["", "missing-at.example", "@example.com", "user@"])
def test_normalize_email_rejects_invalid_identity_email(email):
    with pytest.raises(HTTPException) as exc_info:
        normalize_email(email)
    assert exc_info.value.status_code == 401


def test_internal_domain_is_provisioned_as_analyst(monkeypatch):
    monkeypatch.setattr(
        "app.services.profile_service.settings.INTERNAL_EMAIL_DOMAINS",
        "pluto.studio,projectpluto.studio",
    )
    db = MagicMock()

    assert resolve_initial_access("member@pluto.studio", db) == ("analyst", None)
    db.query.assert_not_called()


def test_explicit_admin_allowlist_takes_precedence(monkeypatch):
    monkeypatch.setattr(
        "app.services.profile_service.settings.RBAC_ADMIN_EMAILS",
        "owner@pluto.studio",
    )
    db = MagicMock()

    assert resolve_initial_access("OWNER@pluto.studio", db) == ("admin", None)
    db.query.assert_not_called()


def test_brand_domain_is_provisioned_as_client():
    brand_id = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        brand_id=brand_id
    )

    assert resolve_initial_access("manager@cocacola.com", db) == ("client", brand_id)


def test_unknown_domain_is_provisioned_as_unassigned_viewer():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert resolve_initial_access("person@gmail.com", db) == ("viewer", None)


def test_first_login_profile_is_committed(monkeypatch):
    user_id = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [None, None]
    monkeypatch.setattr(
        "app.services.profile_service.resolve_initial_access",
        lambda email, session: ("viewer", None),
    )

    profile = get_or_create_user_profile(
        user_id=user_id,
        email="Person@Example.com",
        db=db,
    )

    assert profile.user_id == user_id
    assert profile.email == "person@example.com"
    assert profile.role == "viewer"
    db.add.assert_called_once_with(profile)
    db.flush.assert_called_once()
    db.commit.assert_called_once()


def test_existing_profile_is_reused_without_commit():
    profile = SimpleNamespace(
        user_id=uuid4(), email="person@example.com", role="viewer"
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = profile

    result = get_or_create_user_profile(
        user_id=profile.user_id,
        email="person@example.com",
        db=db,
    )

    assert result is profile
    assert result.role == "viewer"
    db.commit.assert_not_called()


def test_existing_profile_is_promoted_when_email_joins_admin_allowlist(monkeypatch):
    monkeypatch.setattr(
        "app.services.profile_service.settings.RBAC_ADMIN_EMAILS",
        "admin.test@example.com",
    )
    profile = SimpleNamespace(
        user_id=uuid4(), email="admin.test@example.com", role="viewer"
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = profile

    result = get_or_create_user_profile(
        user_id=profile.user_id,
        email=None,
        db=db,
    )

    assert result is profile
    assert result.role == "admin"
    db.commit.assert_called_once()


def test_existing_admin_on_allowlist_is_not_recommitted(monkeypatch):
    monkeypatch.setattr(
        "app.services.profile_service.settings.RBAC_ADMIN_EMAILS",
        "admin.test@example.com",
    )
    profile = SimpleNamespace(
        user_id=uuid4(), email="admin.test@example.com", role="admin"
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = profile

    result = get_or_create_user_profile(
        user_id=profile.user_id,
        email="admin.test@example.com",
        db=db,
    )

    assert result.role == "admin"
    db.commit.assert_not_called()
