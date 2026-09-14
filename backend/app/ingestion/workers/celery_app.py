from celery import Celery
from backend.app.common.config import get_settings

settings = get_settings()

celery_app = Celery(
    "vermithor_ingestion",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Autodiscover tasks from the workers package
celery_app.autodiscover_tasks(["app.workers"])
