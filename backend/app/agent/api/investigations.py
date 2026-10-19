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
from backend.app.agent.services.investigation_service import InvestigationService
from backend.app.common.database import get_db
from backend.app.common.security import require_jwt_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])
service = InvestigationService()


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
) -> InvestigationResponse:
    """Initiate an AI-powered investigation for an incident."""
    if not payload.incident_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field 'incident_key' must not be empty",
        )

    if async_mode:
        from backend.workers.tasks import investigate_incident_task
        task = investigate_incident_task.delay(payload.model_dump())
        logger.info("Dispatched async Celery investigation task: %s", task.id)
        # Return pending placeholder
        inv_key = service.generate_investigation_key(db)
        from backend.app.agent.db.models import Investigation
        db_inv = Investigation(
            investigation_key=inv_key,
            incident_key=payload.incident_key,
            status=InvestigationStatus.PENDING.value,
            target_service="pending",
            environment="production",
        )
        db.add(db_inv)
        db.commit()
        db.refresh(db_inv)
        return service._to_response(db_inv)

    try:
        result = service.run_investigation(db=db, req=payload)
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
    inv = service.get_investigation(db, investigation_id)
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
    inv = service.get_latest_for_incident(db, incident_key)
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
    items, total = service.list_investigations(
        db, page=page, page_size=page_size, incident_key=incident_key, status=status
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
