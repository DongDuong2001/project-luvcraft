from celery import Celery
from celery.signals import worker_init

from app.core.config import settings

celery_app = Celery(
    "luvcraft_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.celery_result_backend_url,
    include=["app.tasks.analyze"],
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_default_queue='luvcraft',
    task_default_delivery_mode='persistent',
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_extended=True,
    worker_enable_remote_control=False,
    worker_send_task_events=False,
)


@worker_init.connect
def validate_worker_collector_configuration(**_kwargs) -> None:
    """Prevent workers from starting with a collector pipeline they cannot run."""
    from app.core.collector_runtime import validate_collector_runtime

    validate_collector_runtime()
