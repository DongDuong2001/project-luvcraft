from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.deps import CurrentUser, get_current_user
from app.main import app


def test_vibe_check_route_rejects_cross_tenant_run():
    caller_brand_id = uuid4()
    run = SimpleNamespace(target_brand_id=uuid4(), is_public_demo=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = run

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=uuid4(),
        email="client@example.com",
        role="client",
        brand_id=caller_brand_id,
    )
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/runs/{uuid4()}/vibe-checks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}
