import importlib.metadata
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.agent.schemas.investigation import (
    InvestigationRequest,
    InvestigationResponse,
    InvestigationStatus,
)
from backend.app.agent.schemas.feedback import (
    InvestigationFeedbackCreate,
    InvestigationFeedbackResponse,
)
from backend.app.agent.services.investigation_service import InvestigationService
from backend.app.common.config import get_settings
from backend.app.common.database import get_db
from backend.app.common.rate_limiter import RateLimiter
from backend.app.common.security import require_jwt_auth, verify_org_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])
service = InvestigationService()
settings = get_settings()
investigation_rate_limiter = RateLimiter(
    scope="investigations",
    calls_per_minute=settings.RATE_LIMIT_INVESTIGATIONS_PER_MIN,
)


@router.get(
    "/health",
    summary="Agent system health check",
    description="Reports the operational status of the LangGraph AI incident investigation agent and its runtime environment.",
)
def get_agent_health() -> Dict[str, Any]:
    """Agent health probe reporting LangGraph version and orchestration status."""
    try:
        lg_ver = importlib.metadata.version("langgraph")
    except Exception:
        lg_ver = "unknown"

    return {
        "status": "healthy",
        "service": "vermithor-agent",
        "orchestration_engine": "langgraph",
        "langgraph_version": lg_ver,
        "capabilities": [
            "telemetry_evidence_gathering",
            "anomaly_evaluation",
            "event_correlation",
            "root_cause_analysis_dag",
            "rag_runbook_retrieval",
            "llm_hypothesis_evaluation",
            "bounded_evidence_expansion",
            "deterministic_fallback",
        ],
    }


@router.post(
    "/investigations",
    response_model=InvestigationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger LangGraph AI incident investigation",
    description=(
        "Executes or retrieves an evidence-grounded AI incident investigation using LangGraph, "
        "reusing existing telemetry, RCA, anomaly, and runbook services."
    ),
)
def create_or_run_investigation(
    payload: InvestigationRequest,
    async_mode: bool = Query(False, description="Whether to dispatch to Celery background queue"),
    db: Session = Depends(get_db),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
    _rate_limit: None = Depends(investigation_rate_limiter),
) -> InvestigationResponse:
    """Initiate an AI-powered investigation for an incident."""
    org_id = verify_org_access(_auth)
    if not payload.incident_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field 'incident_key' must not be empty",
        )
    from backend.app.agent.db.models import PilotGovernancePolicy
    pol = db.query(PilotGovernancePolicy).filter(PilotGovernancePolicy.org_id == org_id).first()
    if pol and pol.investigations_paused:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Incident investigations are currently paused for organization '{org_id}' under pilot data governance policy.",
        )

    if async_mode:
        from backend.workers.tasks import investigate_incident_task
        task_payload = payload.model_dump()
        task_payload["org_id"] = org_id
        task = investigate_incident_task.delay(task_payload)
        logger.info("Dispatched async Celery investigation task: %s", task.id)
        # Return pending placeholder
        inv_key = service.generate_investigation_key(db)
        from backend.app.agent.db.models import Investigation
        db_inv = Investigation(
            investigation_key=inv_key,
            incident_key=payload.incident_key,
            org_id=org_id,
            status=InvestigationStatus.PENDING.value,
            target_service="pending",
            environment="production",
        )
        db.add(db_inv)
        db.commit()
        db.refresh(db_inv)
        return service._to_response(db_inv)

    try:
        result = service.run_investigation(db=db, req=payload, org_id=org_id)
        return result
    except Exception as exc:
        logger.error("Investigation failed for incident '%s': %s", payload.incident_key, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation workflow encountered an unexpected error: {str(exc)[:300]}",
        )


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationResponse,
    summary="Get investigation report by ID or key",
    description="Retrieves a completed or in-progress investigation report by its investigation_key (INV-...) or UUID.",
)
def get_investigation_by_id(
    investigation_id: str,
    db: Session = Depends(get_db),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> InvestigationResponse:
    """Retrieve specific investigation report."""
    org_id = verify_org_access(_auth)
    inv = service.get_investigation(db, investigation_id, org_id=org_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found",
        )
    return inv


@router.get(
    "/investigations/incident/{incident_key}",
    response_model=InvestigationResponse,
    summary="Get latest investigation report for incident",
    description="Retrieves the most recent investigation report conducted for a canonical incident key.",
)
def get_investigation_for_incident(
    incident_key: str,
    db: Session = Depends(get_db),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> InvestigationResponse:
    """Retrieve latest investigation for an incident."""
    org_id = verify_org_access(_auth)
    inv = service.get_latest_for_incident(db, incident_key, org_id=org_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No investigation found for incident key '{incident_key}'",
        )
    return inv


@router.get(
    "/investigations",
    summary="List paginated investigations",
    description="Lists past and current incident investigations with filtering by status and incident key.",
)
def list_investigations(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    incident_key: Optional[str] = Query(None, description="Filter by incident key"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> Dict[str, Any]:
    """List investigations."""
    org_id = verify_org_access(_auth)
    items, total = service.list_investigations(
        db, page=page, page_size=page_size, incident_key=incident_key, status=status, org_id=org_id
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "/investigations/{investigation_id}/feedback",
    response_model=InvestigationFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record operator verification feedback on investigation",
    description="Allows authorized SREs to record confirmed, rejected, or unresolved root cause determinations without modifying the immutable original investigation.",
)
def record_investigation_feedback(
    investigation_id: str,
    payload: InvestigationFeedbackCreate,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
    _rate_limit: None = Depends(investigation_rate_limiter),
) -> InvestigationFeedbackResponse:
    org_id = verify_org_access(auth)
    operator_id = str(auth.get("sub") or "anonymous_operator")

    inv = service.get_investigation(db, investigation_id, org_id=org_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found",
        )

    from backend.app.agent.db.models import InvestigationFeedback
    feedback_entry = InvestigationFeedback(
        investigation_key=inv.investigation_key,
        incident_key=inv.incident_key,
        org_id=org_id,
        feedback_status=payload.feedback_status.value,
        operator_id=operator_id,
        confirmed_root_cause=payload.confirmed_root_cause,
        evidence_reference=payload.evidence_reference,
        explanation=payload.explanation,
    )
    db.add(feedback_entry)
    db.commit()
    db.refresh(feedback_entry)
    return InvestigationFeedbackResponse.model_validate(feedback_entry)


@router.get(
    "/investigations/{investigation_id}/feedback",
    response_model=List[InvestigationFeedbackResponse],
    summary="List operator verification feedback for an investigation",
    description="Retrieves operator feedback history for a specific investigation report.",
)
def list_investigation_feedback(
    investigation_id: str,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> List[InvestigationFeedbackResponse]:
    org_id = verify_org_access(auth)

    inv = service.get_investigation(db, investigation_id, org_id=org_id)
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found",
        )

    from backend.app.agent.db.models import InvestigationFeedback
    records = (
        db.query(InvestigationFeedback)
        .filter(
            InvestigationFeedback.investigation_key == inv.investigation_key,
            InvestigationFeedback.org_id == org_id,
        )
        .order_by(InvestigationFeedback.created_at.desc())
        .all()
    )
    return [InvestigationFeedbackResponse.model_validate(r) for r in records]

