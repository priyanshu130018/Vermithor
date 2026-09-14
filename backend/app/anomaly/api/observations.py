from datetime import datetime
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.anomaly.schemas.anomaly import AnomalyResultResponse, ObservationWithAnomaliesResponse
from backend.app.anomaly.schemas.observation import (
    MetricObservationCreate,
    MetricObservationListResponse,
    MetricObservationResponse,
)
from backend.app.anomaly.services.anomaly_service import AnomalyService
from backend.app.anomaly.services.observation_service import ObservationService

router = APIRouter(prefix="/observations", tags=["observations"])
anomaly_service = AnomalyService()


@router.post(
    "",
    response_model=ObservationWithAnomaliesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a metric observation and evaluate anomalies",
    description="Ingests a raw numeric metric observation, runs statistical and Isolation Forest anomaly detectors, and returns evaluation outputs.",
)
def create_observation(
    obs_in: MetricObservationCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> ObservationWithAnomaliesResponse:
    """Ingest observation and run anomaly detection pipeline."""
    obs, is_new = ObservationService.create_observation(db, obs_in)
    if not is_new:
        response.status_code = status.HTTP_200_OK

    # Run anomaly detector pipeline
    anomalies = anomaly_service.analyze_observation(db, obs)

    return ObservationWithAnomaliesResponse(
        observation=MetricObservationResponse.from_orm_model(obs),
        anomalies=[AnomalyResultResponse.from_orm_model(a) for a in anomalies],
    )


@router.get(
    "/{observation_id}",
    response_model=MetricObservationResponse,
    summary="Get metric observation by observation_id",
    description="Retrieve a single metric observation record by its unique identifier.",
)
def get_observation(
    observation_id: str,
    db: Session = Depends(get_db),
) -> MetricObservationResponse:
    """Retrieve an observation by observation_id."""
    obs = ObservationService.get_observation(db, observation_id)
    if not obs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric observation with id '{observation_id}' not found",
        )
    return MetricObservationResponse.from_orm_model(obs)


@router.get(
    "",
    response_model=MetricObservationListResponse,
    summary="List metric observations with filtering and pagination",
    description="Retrieve a paginated list of metric observations with optional multi-attribute filters.",
)
def list_observations(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    metric_name: Optional[str] = Query(None, description="Filter by metric name"),
    start_time: Optional[datetime] = Query(None, description="Filter observations >= start timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter observations <= end timestamp"),
    db: Session = Depends(get_db),
) -> MetricObservationListResponse:
    """List metric observations with pagination and filters."""
    items, total = ObservationService.list_observations(
        db=db,
        page=page,
        page_size=page_size,
        service=service,
        environment=environment,
        metric_name=metric_name,
        start_time=start_time,
        end_time=end_time,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return MetricObservationListResponse(
        items=[MetricObservationResponse.from_orm_model(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
