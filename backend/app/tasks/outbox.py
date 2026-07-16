from dataclasses import asdict

from app.core.worker import celery_app
from app.services.outbox_service import (
    OUTBOX_DISPATCH_TASK_NAME,
    dispatch_pending_collector_tasks,
)


@celery_app.task(name=OUTBOX_DISPATCH_TASK_NAME, ignore_result=True)
def execute_outbox_dispatch():
    """Publish pending collector tasks from the durable database outbox."""
    return asdict(dispatch_pending_collector_tasks())
