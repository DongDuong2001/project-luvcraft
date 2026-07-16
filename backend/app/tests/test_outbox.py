from datetime import datetime, timezone
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest

from app.models.collector_runtime import CollectorTaskOutbox
from app.services.outbox_service import dispatch_pending_collector_tasks


def make_event(task_name: str) -> CollectorTaskOutbox:
    return CollectorTaskOutbox(
        outbox_id=uuid4(),
        run_id=uuid4(),
        module_run_id=uuid4(),
        task_name=task_name,
        task_args=["run-id", "module-id"],
        status="pending",
        attempt_count=0,
    )


def configure_claim(db, events):
    database_now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    now_result = MagicMock()
    now_result.scalar_one.return_value = database_now
    events_result = MagicMock()
    events_result.scalars.return_value.all.return_value = events
    db.execute.side_effect = [now_result, events_result]
    return database_now


def test_outbox_dispatch_tracks_partial_publication_without_failing_modules():
    db = MagicMock()
    first = make_event("luvcraft.collect_youtube")
    second = make_event("luvcraft.collect_community")
    database_now = configure_claim(db, [first, second])
    publisher = MagicMock(side_effect=[object(), RuntimeError("broker failed")])

    result = dispatch_pending_collector_tasks(
        session_factory=lambda: db,
        publisher=publisher,
    )

    assert result.claimed == 2
    assert result.published == 1
    assert result.failed == 1
    assert first.status == "published"
    assert first.published_at == database_now
    assert first.attempt_count == 1
    assert second.status == "pending"
    assert second.published_at is None
    assert second.attempt_count == 1
    assert second.available_at > database_now
    assert second.last_error == "RuntimeError"
    assert publisher.call_args_list == [
        call(
            "luvcraft.collect_youtube",
            args=["run-id", "module-id"],
            task_id=str(first.outbox_id),
        ),
        call(
            "luvcraft.collect_community",
            args=["run-id", "module-id"],
            task_id=str(second.outbox_id),
        ),
    ]
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    db.close.assert_called_once()


def test_outbox_dispatch_rolls_back_claim_transaction_on_database_error():
    db = MagicMock()
    db.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        dispatch_pending_collector_tasks(session_factory=lambda: db)

    db.rollback.assert_called_once()
    db.close.assert_called_once()
