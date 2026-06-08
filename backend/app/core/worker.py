from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "luvcraft_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.celery_result_backend_url,
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
)
