from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.api_key_service import (
    API_KEY_PREFIX,
    authenticate_api_key,
    generate_api_key,
    hash_api_key,
)


def test_generated_api_key_has_expected_shape_and_hash():
    raw_key, key_prefix, key_hash = generate_api_key()

    assert raw_key.startswith(API_KEY_PREFIX)
    assert len(raw_key) == 75
    assert key_prefix == raw_key[:24]
    assert len(key_hash) == 64
    assert key_hash == hash_api_key(raw_key)


def test_valid_api_key_resolves_active_user_profile():
    raw_key, _, key_hash = generate_api_key()
    user_id = uuid4()
    key = SimpleNamespace(
        key_hash=key_hash,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    profile = SimpleNamespace(user_id=user_id, is_active=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [key, profile]

    assert authenticate_api_key(raw_key, db) is profile


def test_expired_api_key_is_rejected():
    raw_key, _, key_hash = generate_api_key()
    key = SimpleNamespace(
        key_hash=key_hash,
        user_id=uuid4(),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = key

    with pytest.raises(HTTPException) as exc_info:
        authenticate_api_key(raw_key, db)
    assert exc_info.value.status_code == 401


def test_unknown_api_key_is_rejected():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        authenticate_api_key(f"{API_KEY_PREFIX}{'a' * 64}", db)
    assert exc_info.value.status_code == 401
