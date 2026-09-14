import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import select

import backend.app.common.database as common_db
from backend.app.ingestion.db.models import Event
from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_event",
    max_retries=3,
    default_retry_delay=5,
    retry_backoff=True,
    retry_backoff_max=60,
)
def process_event(self, event_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Asynchronously process an ingested event.

    Transitions:
        PENDING -> PROCESSING -> PROCESSED (or FAILED)
    """
    if event_id is None and isinstance(self, str):
        target_event_id = self
        task_instance = None
    else:
        target_event_id = event_id or (self if isinstance(self, str) else "")
        task_instance = self

    logger.info("Celery task started: process_event for event_id='%s'", target_event_id)
    db = common_db.SessionLocal()

    retries = getattr(task_instance.request, "retries", 0) if (task_instance and hasattr(task_instance, "request")) else 0
    max_retries = getattr(task_instance, "max_retries", 3) if task_instance else 3

    try:
        # Fetch event from database
        event = db.execute(
            select(Event).where(Event.event_id == target_event_id)
        ).scalar_one_or_none()

        if not event:
            logger.warning(
                "Event with event_id='%s' not found in database. Skipping processing.",
                target_event_id,
            )
            return {"status": "not_found", "event_id": target_event_id}

        # Idempotency check: if already processed, skip duplicate execution
        if event.processing_status == "PROCESSED":
            logger.info(
                "Event with event_id='%s' is already PROCESSED. Skipping duplicate task.",
                target_event_id,
            )
            return {"status": "already_processed", "event_id": target_event_id}

        # Transition status to PROCESSING
        event.processing_status = "PROCESSING"
        db.commit()
        db.refresh(event)

        logger.info(
            "Processing event: event_id='%s', type='%s', severity='%s', service='%s', environment='%s'",
            event.event_id,
            event.event_type,
            event.severity,
            event.service,
            event.environment,
        )

        # Basic domain processing logic
        signal_summary = (
            f"type={event.event_type} severity={event.severity} service={event.service}"
        )
        logger.info(
            "Signal evaluated for event_id='%s': %s. Marking as PROCESSED.",
            event.event_id,
            signal_summary,
        )

        # Transition status to PROCESSED
        event.processing_status = "PROCESSED"
        event.processed_at = datetime.now(timezone.utc)
        event.processing_error = None
        db.commit()

        logger.info(
            "Celery task completed successfully: event_id='%s', processed_at='%s'",
            event.event_id,
            event.processed_at.isoformat(),
        )
        return {"status": "processed", "event_id": event.event_id}

    except Exception as exc:
        db.rollback()
        error_msg = f"{exc.__class__.__name__}: {str(exc)[:500]}"
        logger.error(
            "Error processing event_id='%s' (attempt %d/%d): %s",
            target_event_id,
            retries + 1,
            max_retries + 1,
            error_msg,
        )

        # Record failure status in database
        try:
            failed_event = db.execute(
                select(Event).where(Event.event_id == target_event_id)
            ).scalar_one_or_none()
            if failed_event:
                failed_event.processing_status = "FAILED"
                failed_event.processing_error = error_msg
                db.commit()
        except Exception as db_err:
            db.rollback()
            logger.error(
                "Failed to update error status for event_id='%s': %s",
                target_event_id,
                str(db_err),
            )

        # Retry bounded task if attempts remain
        if task_instance and hasattr(task_instance, "retry") and retries < max_retries:
            raise task_instance.retry(exc=exc)
        return {"status": "failed", "event_id": target_event_id, "error": error_msg}

    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.cluster_logs_task",
    max_retries=2,
    default_retry_delay=10,
)
def cluster_logs_task(
    self,
    window_seconds: Optional[int] = None,
    service: Optional[str] = None,
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Asynchronously run HDBSCAN log clustering across the sliding time window.
    """
    logger.info("Celery task started: cluster_logs_task (window=%s, service=%s)", window_seconds, service)
    db = common_db.SessionLocal()
    try:
        from datetime import timedelta
        from backend.app.log_intelligence.clustering.service import LogClusteringService
        from backend.app.log_intelligence.schemas.logs import LogClusteringRequest

        now = datetime.now(timezone.utc)
        win = window_seconds or 300
        req = LogClusteringRequest(
            start_time=now - timedelta(seconds=win),
            end_time=now,
            service=service,
            environment=environment,
        )
        clustering_service = LogClusteringService()
        result = clustering_service.cluster_db_logs(db=db, req=req)

        return {
            "status": "success",
            "total_logs": result.total_logs,
            "total_clusters": result.total_clusters,
            "noise_count": result.noise_count,
            "duration_ms": result.duration_ms,
        }
    except Exception as exc:
        logger.error("Error executing cluster_logs_task: %s", exc)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
