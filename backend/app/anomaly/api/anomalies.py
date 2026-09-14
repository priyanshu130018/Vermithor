from datetime import datetime
import math
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.anomaly.schemas.anomaly import (
    AnomalyResultListResponse,
    AnomalyResultResponse,
    AnomalySeverity,
    DetectorType,
)
from backend.app.anomaly.services.anomaly_service import AnomalyService

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get(
    "/{observation_id}",
    response_model=List[AnomalyResultResponse],
    summary="Get anomaly results for an observation",
    description="Retrieve all detector evaluation outputs and anomaly scores for a specific observation ID.",
)
def get_anomalies_for_observation(
    observation_id: str,
    db: Session = Depends(get_db),
) -> List[AnomalyResultResponse]:
    """Retrieve anomaly evaluations for a given observation."""
    results = AnomalyService.get_anomalies_for_observation(db, observation_id)
    return [AnomalyResultResponse.from_orm_model(r) for r in results]


@router.get(
    "",
    response_model=AnomalyResultListResponse,
    summary="List anomaly results with filtering and pagination",
    description="Retrieve a paginated list of anomaly detector results with optional multi-attribute filters.",
)
def list_anomalies(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    severity: Optional[AnomalySeverity] = Query(None, description="Filter by classified severity"),
    detector: Optional[DetectorType] = Query(None, description="Filter by detector algorithm"),
    is_anomaly: Optional[bool] = Query(None, description="Filter by boolean anomaly decision"),
    start_time: Optional[datetime] = Query(None, description="Filter results >= start timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter results <= end timestamp"),
    db: Session = Depends(get_db),
) -> AnomalyResultListResponse:
    """List anomaly results with pagination and filters."""
    items, total = AnomalyService.list_anomalies(
        db=db,
        page=page,
        page_size=page_size,
        severity=severity.value if severity else None,
        detector=detector.value if detector else None,
        is_anomaly=is_anomaly,
        start_time=start_time,
        end_time=end_time,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return AnomalyResultListResponse(
        items=[AnomalyResultResponse.from_orm_model(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
