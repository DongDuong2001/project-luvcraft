from unittest.mock import MagicMock
from uuid import uuid4

from app.api.brands import list_visible_brands
from app.deps import CurrentUser


def test_analyst_can_list_all_brands():
    db = MagicMock()
    expected = [MagicMock()]
    db.query.return_value.order_by.return_value.all.return_value = expected
    analyst = CurrentUser(user_id=uuid4(), role="analyst")

    assert list_visible_brands(analyst, db) == expected
    db.query.return_value.filter.assert_not_called()


def test_client_brand_list_is_tenant_scoped():
    db = MagicMock()
    expected = [MagicMock()]
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = expected
    client = CurrentUser(user_id=uuid4(), role="client", brand_id=uuid4())

    assert list_visible_brands(client, db) == expected
    db.query.return_value.filter.assert_called_once()


def test_unassigned_viewer_has_no_visible_brands():
    db = MagicMock()
    viewer = CurrentUser(user_id=uuid4(), role="viewer")

    assert list_visible_brands(viewer, db) == []
