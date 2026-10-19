from datetime import datetime
import math
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.summary.schemas.summaries import IncidentSummaryListResponse, IncidentSummaryResponse
from backend.app.summary.services.summary_service import IncidentSummaryService

router = APIRouter(prefix="/summaries", tags=["summaries"])
summary_service = IncidentSummaryService()


@router.get(
    "/provider/status",
    summary="Get LLM provider connectivity and configuration status",
)
def get_provider_status() -> Dict[str, Any]:
    """Inspect configured LLM provider (Ollama or Hugging Face) connectivity and model status."""
    provider = summary_service.llm_provider
    is_avail = provider.is_available()
    return {
        "provider": provider.get_provider_name(),
        "model": provider.get_model_name(),
        "available": is_avail,
        "status": "connected" if is_avail else "unreachable",
        "fallback_enabled": summary_service.settings.LLM_FALLBACK_ENABLED,
    }


@router.post(
    "/incident/{incident_key}",
    response_model=IncidentSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate or retrieve natural-language incident summary",
    description="Loads incident telemetry, RCA reports, and grounded RAG context, synthesizes an evidence-backed summary with LLM, validates output schema and source citations, and persists the result.",
)
def generate_incident_summary(
    incident_key: str,
    regenerate: bool = Query(False, description="If true, explicitly regenerates summary instead of returning existing version"),
    db: Session = Depends(get_db),
) -> IncidentSummaryResponse:
    """Generate or retrieve grounded natural-language incident summary."""
    try:
        return summary_service.generate_summary_for_incident(
            db=db,
            incident_key=incident_key,
            regenerate=regenerate,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"LLM provider timed out: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Incident summary generation failed: {exc}",
        )


@router.get(
    "/{summary_key}",
    response_model=IncidentSummaryResponse,
    summary="Get incident summary by key",
)
def get_summary_by_key(
    summary_key: str,
    db: Session = Depends(get_db),
) -> IncidentSummaryResponse:
    """Retrieve existing incident summary by its unique key (e.g. SUM-000001)."""
    res = summary_service.get_by_key(db=db, summary_key=summary_key)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident summary with key '{summary_key}' not found",
        )
    return res


@router.get(
    "",
    response_model=IncidentSummaryListResponse,
    summary="List incident summaries with pagination and filters",
)
def list_summaries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    incident_key: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> IncidentSummaryListResponse:
    """List historical incident summaries with optional filters."""
    items, total = summary_service.list_summaries(
        db=db,
        page=page,
        page_size=page_size,
        incident_key=incident_key,
        status=status,
        min_confidence=min_confidence,
        start_time=start_time,
        end_time=end_time,
    )
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    return IncidentSummaryListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
