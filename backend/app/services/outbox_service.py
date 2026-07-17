from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import func, select

from app.models.collector_runtime import CollectorTaskOutbox

logger = logging.getLogger(__name__)

OUTBOX_DISPATCH_TASK_NAME = "luvcraft.dispatch_collector_outbox"
OUTBOX_BATCH_SIZE = 50
OUTBOX_MAX_RETRY_DELAY_SECONDS = 300

TaskPublisher = Callable[..., Any]


@dataclass(frozen=True)
class OutboxDispatchResult:
    claimed: int
    published: int
    failed: int


def _retry_delay_seconds(attempt_count: int) -> int:
    return min(2 ** max(0, attempt_count - 1), OUTBOX_MAX_RETRY_DELAY_SECONDS)


def _default_publisher(task_name: str, **options: Any) -> Any:
    from app.core.worker import celery_app

    return celery_app.send_task(task_name, **options)


def dispatch_pending_collector_tasks(
    *,
    session_factory=None,
    publisher: TaskPublisher | None = None,
    batch_size: int = OUTBOX_BATCH_SIZE,
) -> OutboxDispatchResult:
    """Publish one locked outbox batch with at-least-once delivery semantics."""
    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal
    publish = publisher or _default_publisher

    db = session_factory()
    try:
        database_now = db.execute(select(func.clock_timestamp())).scalar_one()
        events = (
            db.execute(
                select(CollectorTaskOutbox)
                .where(
                    CollectorTaskOutbox.status == "pending",
                    CollectorTaskOutbox.available_at <= database_now,
                )
                .order_by(
                    CollectorTaskOutbox.created_at,
                    CollectorTaskOutbox.outbox_id,
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        published = 0
        failed = 0
        for event in events:
            event.attempt_count += 1
            try:
                publish(
                    event.task_name,
                    args=list(event.task_args),
                    task_id=str(event.outbox_id),
                )
            except Exception as exc:
                failed += 1
                # Persist only the exception category; broker errors can embed
                # connection URLs or credentials in their message text.
                event.last_error = type(exc).__name__
                event.available_at = database_now + timedelta(
                    seconds=_retry_delay_seconds(event.attempt_count)
                )
                logger.warning(
                    "Outbox publication failed for event %s (attempt %s, error %s)",
                    event.outbox_id,
                    event.attempt_count,
                    type(exc).__name__,
                )
            else:
                published += 1
                event.status = "published"
                event.published_at = database_now
                event.last_error = None

        db.commit()
        return OutboxDispatchResult(
            claimed=len(events),
            published=published,
            failed=failed,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
