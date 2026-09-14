from datetime import datetime
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.correlation.schemas.correlation import (
    CorrelationEvaluationRequest,
    CorrelationEvaluationResponse,
    CorrelationGroupCreateRequest,
    CorrelationGroupListResponse,
    CorrelationGroupResponse,
    GroupStatus,
)
from backend.app.correlation.services.correlation_service import CorrelationService

router = APIRouter(prefix="/correlations", tags=["correlations"])
correlation_service = CorrelationService()


@router.post(
    "/evaluate",
    response_model=CorrelationEvaluationResponse,
    summary="Evaluate correlation across candidate signals",
    description="Calculates deterministic factor-based correlation score and returns explainable reasons without persisting a group.",
)
def evaluate_signals(
    req: CorrelationEvaluationRequest,
) -> CorrelationEvaluationResponse:
    """Dry-run correlation scoring on candidate signals."""
    score, is_correlated, reasons = correlation_service.evaluate_signals(req.signals)
    return CorrelationEvaluationResponse(
        correlation_score=score,
        is_correlated=is_correlated,
        reasons=reasons,
    )


@router.post(
    "/groups",
    response_model=CorrelationGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Form and persist a new correlation group",
    description="Evaluates candidate signals, assigns relationship scores, persists a CorrelationGroup with associations, and conditionally triggers incident creation.",
)
def create_group(
    req: CorrelationGroupCreateRequest,
    db: Session = Depends(get_db),
) -> CorrelationGroupResponse:
    """Create and persist a new correlation group."""
    group = correlation_service.create_group(db, req)
    return CorrelationGroupResponse.from_orm_model(group)


@router.get(
    "/groups/{group_key}",
    response_model=CorrelationGroupResponse,
    summary="Get correlation group by group_key",
    description="Retrieve details of a specific correlation group including all associated signals and relationship reasons.",
)
def get_group(
    group_key: str,
    db: Session = Depends(get_db),
) -> CorrelationGroupResponse:
    """Retrieve a single correlation group by group_key."""
    group = CorrelationService.get_group(db, group_key)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Correlation group '{group_key}' not found",
        )
    return CorrelationGroupResponse.from_orm_model(group)


@router.get(
    "/groups",
    response_model=CorrelationGroupListResponse,
    summary="List correlation groups with filtering and pagination",
    description="Retrieve a paginated list of correlation groups with optional filters.",
)
def list_groups(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[GroupStatus] = Query(None, description="Filter by group status"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    service: Optional[str] = Query(None, description="Filter by primary service"),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0, description="Filter by minimum correlation score"),
    start_time: Optional[datetime] = Query(None, description="Filter groups started >= start timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter groups ended <= end timestamp"),
    db: Session = Depends(get_db),
) -> CorrelationGroupListResponse:
    """List correlation groups with pagination and multi-attribute filtering."""
    items, total = CorrelationService.list_groups(
        db=db,
        page=page,
        page_size=page_size,
        status=status.value if status else None,
        environment=environment,
        service=service,
        min_score=min_score,
        start_time=start_time,
        end_time=end_time,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return CorrelationGroupListResponse(
        items=[CorrelationGroupResponse.from_orm_model(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
