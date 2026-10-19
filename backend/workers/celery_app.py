from celery import Celery
from backend.app.common.config import get_settings

settings = get_settings()

celery_app = Celery(
    "vermithor_workers",
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

# Autodiscover tasks from workers package
celery_app.autodiscover_tasks(["backend.workers", "backend.workers.tasks", "backend.app.ingestion.workers"])


from celery.signals import worker_process_init

@worker_process_init.connect
def on_worker_init(**kwargs):
    """Initialize OpenTelemetry tracer provider with vermithor-worker service name when worker starts."""
    try:
        from backend.app.common.telemetry import init_tracer
        init_tracer("vermithor-worker")
    except Exception:
        pass

