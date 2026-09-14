import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.anomaly.schemas.observation import MetricObservationResponse


class DetectorType(str, Enum):
    """Supported anomaly detector algorithms."""
    STATISTICAL = "STATISTICAL"
    ISOLATION_FOREST = "ISOLATION_FOREST"


class AnomalySeverity(str, Enum):
    """Classified anomaly severity levels."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AnomalyResultResponse(BaseModel):
    """Output evaluation from an anomaly detector."""
    id: uuid.UUID
    observation_id: str
    detector: DetectorType
    detector_version: str
    anomaly_score: float = Field(..., ge=0.0, le=1.0, description="Normalized anomaly score (0.0 to 1.0)")
    is_anomaly: bool
    severity: AnomalySeverity
    expected_value: Optional[float] = None
    deviation: Optional[float] = None
    reason: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "observation_id": "metric-001",
                "detector": "STATISTICAL",
                "detector_version": "1.0",
                "anomaly_score": 0.95,
                "is_anomaly": True,
                "severity": "CRITICAL",
                "expected_value": 120.0,
                "deviation": 700.5,
                "reason": "request_latency was 4.25 standard deviations above historical baseline (~120.0ms, observed 820.5ms).",
                "created_at": "2026-08-29T12:00:01Z"
            }
        }
    )

    @classmethod
    def from_orm_model(cls, obj: Any) -> "AnomalyResultResponse":
        return cls(
            id=obj.id,
            observation_id=obj.observation_id,
            detector=DetectorType(obj.detector),
            detector_version=obj.detector_version,
            anomaly_score=obj.anomaly_score,
            is_anomaly=obj.is_anomaly,
            severity=AnomalySeverity(obj.severity),
            expected_value=obj.expected_value,
            deviation=obj.deviation,
            reason=obj.reason,
            created_at=obj.created_at,
        )


class ObservationWithAnomaliesResponse(BaseModel):
    """Composite response returning an observation and all detector results."""
    observation: MetricObservationResponse
    anomalies: List[AnomalyResultResponse]


class AnomalyResultListResponse(BaseModel):
    """Paginated list envelope for anomaly results."""
    items: List[AnomalyResultResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response schema."""
    service: str = "anomaly-service"
    status: str = "healthy"
