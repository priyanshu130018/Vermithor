import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MetricObservationBase(BaseModel):
    """Base schema for a raw metric observation."""
    observation_id: str = Field(..., min_length=1, max_length=255, description="Unique observation identifier")
    timestamp: datetime = Field(..., description="Observation timestamp (timezone-aware)")
    service: str = Field(..., min_length=1, max_length=128, description="Originating service name")
    environment: str = Field(..., min_length=1, max_length=64, description="Deployment environment (e.g. production)")
    metric_name: str = Field(..., min_length=1, max_length=128, description="Standardized metric name")
    metric_value: float = Field(..., description="Observed numeric metric value")
    unit: Optional[str] = Field(None, max_length=32, description="Metric unit (e.g. ms, percent, count)")
    labels: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary dimensional labels")

    @field_validator("timestamp")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("Timestamp must be timezone-aware (e.g. 2026-08-29T12:00:00Z)")
        return v


class MetricObservationCreate(MetricObservationBase):
    """Payload for submitting a new metric observation for ingestion and anomaly analysis."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "observation_id": "metric-001",
                "timestamp": "2026-08-29T12:00:00Z",
                "service": "booking-api",
                "environment": "production",
                "metric_name": "request_latency",
                "metric_value": 820.5,
                "unit": "ms",
                "labels": {
                    "endpoint": "/api/book",
                    "region": "ap-south-1"
                }
            }
        }
    )


class MetricObservationResponse(BaseModel):
    """Public representation of an ingested metric observation."""
    id: uuid.UUID
    observation_id: str
    timestamp: datetime
    service: str
    environment: str
    metric_name: str
    metric_value: float
    unit: Optional[str] = None
    labels: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "observation_id": "metric-001",
                "timestamp": "2026-08-29T12:00:00Z",
                "service": "booking-api",
                "environment": "production",
                "metric_name": "request_latency",
                "metric_value": 820.5,
                "unit": "ms",
                "labels": {
                    "endpoint": "/api/book",
                    "region": "ap-south-1"
                },
                "created_at": "2026-08-29T12:00:01Z"
            }
        }
    )

    @classmethod
    def from_orm_model(cls, obj: Any) -> "MetricObservationResponse":
        return cls(
            id=obj.id,
            observation_id=obj.observation_id,
            timestamp=obj.timestamp,
            service=obj.service,
            environment=obj.environment,
            metric_name=obj.metric_name,
            metric_value=obj.metric_value,
            unit=obj.unit,
            labels=obj.labels if obj.labels is not None else {},
            created_at=obj.created_at,
        )


class MetricObservationListResponse(BaseModel):
    """Paginated list envelope for metric observations."""
    items: List[MetricObservationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
