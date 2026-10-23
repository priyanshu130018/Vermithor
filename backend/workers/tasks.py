import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import select

import backend.app.common.database as common_db
from backend.app.common.telemetry import (
    init_tracer,
    CELERY_TASKS_TOTAL,
    CELERY_TASK_DURATION_SECONDS,
)
from opentelemetry import trace
from backend.app.ingestion.db.models import Event
from backend.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def get_worker_tracer() -> trace.Tracer:
    """Retrieve tracer for Celery worker tasks."""
    return trace.get_tracer("vermithor-worker")


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

    task_id = str(getattr(task_instance.request, "id", "") if task_instance and hasattr(task_instance, "request") else "")
    logger.info("Celery task started: process_event for event_id='%s' (task_id='%s')", target_event_id, task_id)
    start_time = time.perf_counter()
    task_status = "SUCCESS"

    with get_worker_tracer().start_as_current_span(
        "celery.process_event",
        attributes={
            "service.name": "vermithor-worker",
            "messaging.system": "celery",
            "celery.task_name": "app.workers.tasks.process_event",
            "celery.task_id": task_id,
            "event_id": str(target_event_id),
        },
    ) as span:
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
            task_status = "FAILURE"
            span.record_exception(exc)
            span.set_attribute("error", True)
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
            duration = time.perf_counter() - start_time
            CELERY_TASKS_TOTAL.labels(task_name="process_event", status=task_status).inc()
            CELERY_TASK_DURATION_SECONDS.labels(task_name="process_event", status=task_status).observe(duration)


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
    task_id = str(getattr(self.request, "id", "") if hasattr(self, "request") else "")
    logger.info("Celery task started: cluster_logs_task (task_id=%s, window=%s, service=%s)", task_id, window_seconds, service)
    start_time = time.perf_counter()
    task_status = "SUCCESS"

    with get_worker_tracer().start_as_current_span(
        "celery.cluster_logs_task",
        attributes={
            "service.name": "vermithor-worker",
            "messaging.system": "celery",
            "celery.task_name": "app.workers.tasks.cluster_logs_task",
            "celery.task_id": task_id,
            "clustering.service": service or "all",
        },
    ) as span:
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
            task_status = "FAILURE"
            span.record_exception(exc)
            span.set_attribute("error", True)
            logger.error("Error executing cluster_logs_task: %s", exc)
            return {"status": "failed", "error": str(exc)}
        finally:
            db.close()
            duration = time.perf_counter() - start_time
            CELERY_TASKS_TOTAL.labels(task_name="cluster_logs_task", status=task_status).inc()
            CELERY_TASK_DURATION_SECONDS.labels(task_name="cluster_logs_task", status=task_status).observe(duration)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.investigate_incident_task",
    max_retries=2,
    default_retry_delay=10,
)
def investigate_incident_task(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asynchronously run LangGraph AI incident investigation using existing Celery worker infrastructure.
    """
    task_id = str(getattr(self.request, "id", "") if hasattr(self, "request") else "")
    incident_key = request_payload.get("incident_key", "UNKNOWN")
    logger.info("Celery task started: investigate_incident_task (task_id=%s, incident_key=%s)", task_id, incident_key)
    start_time = time.perf_counter()
    task_status = "SUCCESS"

    with get_worker_tracer().start_as_current_span(
        "celery.investigate_incident_task",
        attributes={
            "service.name": "vermithor-worker",
            "messaging.system": "celery",
            "celery.task_name": "app.workers.tasks.investigate_incident_task",
            "celery.task_id": task_id,
            "incident_key": incident_key,
        },
    ) as span:
        db = common_db.SessionLocal()
        try:
            from backend.app.agent.schemas.investigation import InvestigationRequest
            from backend.app.agent.services.investigation_service import InvestigationService
            from backend.app.agent.db.models import PilotGovernancePolicy

            raw_org = request_payload.get("org_id")
            if not raw_org or not str(raw_org).strip():
                logger.error("Celery investigate_incident_task aborted: Missing required org_id in task payload")
                return {"status": "unauthorized", "error": "Missing required organization context in task payload"}
            org_id = str(raw_org).strip().lower()

            from backend.app.common.security import is_org_authorized
            if not is_org_authorized(org_id):
                logger.error("Celery investigate_incident_task aborted: org '%s' is not authorized", org_id)
                return {
                    "status": "unauthorized",
                    "error": f"Organization '{org_id}' is not authorized to run investigations",
                    "incident_key": incident_key,
                }

            pol = db.query(PilotGovernancePolicy).filter(PilotGovernancePolicy.org_id == org_id).first()
            if pol and pol.investigations_paused:
                logger.warning("Celery task aborted: investigations paused for org '%s' under pilot policy", org_id)
                return {
                    "status": "aborted",
                    "reason": f"Investigations paused for org '{org_id}' under pilot policy",
                    "incident_key": incident_key,
                }

            req = InvestigationRequest.model_validate(request_payload)
            inv_service = InvestigationService()
            response = inv_service.run_investigation(db=db, req=req, org_id=org_id)

            return {
                "status": "success",
                "investigation_key": response.investigation_key,
                "incident_key": response.incident_key,
                "investigation_status": response.status.value,
                "leading_hypothesis": response.leading_hypothesis,
                "confidence": response.confidence,
                "is_fallback": response.is_fallback,
            }
        except Exception as exc:
            task_status = "FAILURE"
            span.record_exception(exc)
            span.set_attribute("error", True)
            logger.error("Error executing investigate_incident_task: %s", exc)
            return {"status": "failed", "error": str(exc)}
        finally:
            db.close()
            duration = time.perf_counter() - start_time
            CELERY_TASKS_TOTAL.labels(task_name="investigate_incident_task", status=task_status).inc()
            CELERY_TASK_DURATION_SECONDS.labels(task_name="investigate_incident_task", status=task_status).observe(duration)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.repair_code_task",
    max_retries=2,
    default_retry_delay=10,
)
def repair_code_task(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asynchronously run LangGraph AI Code Repair agent using Celery worker infrastructure.
    """
    task_id = str(getattr(self.request, "id", "") if hasattr(self, "request") else "")
    inv_key = request_payload.get("investigation_key", "UNKNOWN")
    logger.info("Celery task started: repair_code_task (task_id=%s, investigation_key=%s)", task_id, inv_key)
    start_time = time.perf_counter()
    task_status = "SUCCESS"

    with get_worker_tracer().start_as_current_span(
        "celery.repair_code_task",
        attributes={
            "service.name": "vermithor-worker",
            "messaging.system": "celery",
            "celery.task_name": "app.workers.tasks.repair_code_task",
            "celery.task_id": task_id,
            "investigation_key": inv_key,
        },
    ) as span:
        db = common_db.SessionLocal()
        try:
            from backend.app.agent.schemas.repair import RepairRequest, RepairStatus
            from backend.app.agent.services.repair_service import RepairService
            from backend.app.agent.db.models import Investigation, Repair

            raw_org = request_payload.get("org_id")
            if not raw_org or not str(raw_org).strip():
                logger.error("Celery repair_code_task aborted: Missing required org_id in task payload")
                return {"status": "unauthorized", "error": "Missing required organization context in task payload"}
            org_id = str(raw_org).strip().lower()

            from backend.app.common.security import is_org_authorized
            if not is_org_authorized(org_id):
                logger.error("Celery repair_code_task aborted: org '%s' is not authorized", org_id)
                return {
                    "status": "unauthorized",
                    "error": f"Organization '{org_id}' is not authorized to run repairs",
                    "investigation_key": inv_key,
                }

            # Worker-side authorization verification: verify DB record tenant matches payload org
            import uuid
            inv_filter = Investigation.investigation_key == inv_key
            try:
                val_uuid = uuid.UUID(inv_key)
                inv_filter = (Investigation.investigation_key == inv_key) | (Investigation.id == val_uuid)
            except (ValueError, AttributeError):
                pass
            inv_record = db.execute(select(Investigation).where(inv_filter)).scalars().first()
            if inv_record:
                if not inv_record.org_id or not str(inv_record.org_id).strip():
                    if org_id not in ("vermithor", "admin"):
                        logger.error("Worker authorization check failed: record '%s' lacks tenant ownership", inv_key)
                        return {"status": "unauthorized", "error": f"Record '{inv_key}' lacks tenant ownership and cannot be processed by '{org_id}'"}
                elif inv_record.org_id.lower() != org_id and org_id not in ("vermithor", "admin"):
                    logger.error("Worker authorization check failed: payload org '%s' does not match record org '%s'", org_id, inv_record.org_id)
                    return {"status": "unauthorized", "error": f"Tenant context mismatch: task payload organization '{org_id}' does not own investigation '{inv_key}'"}

            # Idempotency / duplicate delivery check: if already completed or awaiting approval, return existing
            existing_rep = db.execute(select(Repair).where(
                Repair.investigation_key == inv_key,
                Repair.status.in_([
                    RepairStatus.AWAITING_APPROVAL.value,
                    RepairStatus.APPROVED.value,
                    RepairStatus.VALIDATED.value,
                ]),
            )).scalars().first()
            if existing_rep:
                logger.info("Celery task: idempotent return for already processed repair '%s'", existing_rep.repair_key)
                rep_service = RepairService()
                response = rep_service._to_response(existing_rep)
                return {
                    "status": "success",
                    "repair_key": response.repair_key,
                    "investigation_key": response.investigation_key,
                    "incident_key": response.incident_key,
                    "repair_status": response.status.value,
                    "validation_status": response.validation_status.value,
                    "patch_hash": response.patch_hash,
                    "requires_human_approval": response.requires_human_approval,
                    "is_duplicate_delivery": True,
                }

            req = RepairRequest.model_validate(request_payload)
            rep_service = RepairService()
            response = rep_service.run_repair(db=db, req=req, user_identity={"org_id": org_id})

            return {
                "status": "success",
                "repair_key": response.repair_key,
                "investigation_key": response.investigation_key,
                "incident_key": response.incident_key,
                "repair_status": response.status.value,
                "validation_status": response.validation_status.value,
                "patch_hash": response.patch_hash,
                "requires_human_approval": response.requires_human_approval,
            }
        except Exception as exc:
            task_status = "FAILURE"
            span.record_exception(exc)
            span.set_attribute("error", True)
            logger.error("Error executing repair_code_task: %s", exc)
            return {"status": "failed", "error": str(exc)}
        finally:
            db.close()
            duration = time.perf_counter() - start_time
            CELERY_TASKS_TOTAL.labels(task_name="repair_code_task", status=task_status).inc()
            CELERY_TASK_DURATION_SECONDS.labels(task_name="repair_code_task", status=task_status).observe(duration)
