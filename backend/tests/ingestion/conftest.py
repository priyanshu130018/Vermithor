from backend.app.ingestion.workers.celery_app import celery_app
from backend.tests.conftest import TestingSessionLocal
import backend.app.ingestion.workers.tasks as ingestion_tasks
import backend.app.common.database as common_db

celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
)

ingestion_tasks.SessionLocal = TestingSessionLocal
common_db.SessionLocal = TestingSessionLocal
