import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentSeverity(str, Enum):
    """Incident severity levels."""
    SEV1 = "SEV1"  # Critical production impact
    SEV2 = "SEV2"  # Major impact
    SEV3 = "SEV3"  # Moderate impact
    SEV4 = "SEV4"  # Low impact


class IncidentStatus(str, Enum):
    """Incident lifecycle state machine statuses."""
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class RelationType(str, Enum):
    """Relation type between an incident and an observability event."""
    PRIMARY_SIGNAL = "PRIMARY_SIGNAL"
    RELATED_ERROR = "RELATED_ERROR"
    METRIC_ANOMALY = "METRIC_ANOMALY"
    TRACE_SIGNAL = "TRACE_SIGNAL"
    DEPLOYMENT = "DEPLOYMENT"
    ALERT = "ALERT"


IncidentRelationType = RelationType


class IncidentBase(BaseModel):
    """Base schema for an incident."""
    title: str = Field(..., min_length=1, max_length=255, description="Brief summary of the incident")
    description: Optional[str] = Field(None, description="Detailed context and impact description")
    severity: IncidentSeverity = Field(..., description="Operational severity classification")
    environment: str = Field(..., min_length=1, max_length=64, description="Target environment (e.g. production)")
    started_at: datetime = Field(..., description="Incident start timestamp (timezone-aware)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Correlation confidence score (0.0 - 1.0)")

    @field_validator("started_at")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("Timestamp must be timezone-aware (e.g. 2026-08-29T12:00:00Z)")
        return v


class IncidentCreate(IncidentBase):
    """Payload for declaring or reporting a new incident."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Database Connection Saturation",
                "description": "Database connection pool reached critical utilization.",
                "severity": "SEV1",
                "environment": "production",
                "started_at": "2026-08-29T12:00:00Z",
                "confidence": 0.89
            }
        }
    )


class IncidentResponse(BaseModel):
    """Public representation of an operational incident."""
    id: uuid.UUID
    incident_key: str
    title: str
    description: Optional[str] = None
    severity: IncidentSeverity
    status: IncidentStatus
    environment: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    confidence: float

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "incident_key": "INC-000001",
                "title": "Database Connection Saturation",
                "description": "Database connection pool reached critical utilization.",
                "severity": "SEV1",
                "status": "DETECTED",
                "environment": "production",
                "started_at": "2026-08-29T12:00:00Z",
                "ended_at": None,
                "created_at": "2026-08-29T12:01:00Z",
                "updated_at": "2026-08-29T12:01:00Z",
                "confidence": 0.89
            }
        }
    )

    @classmethod
    def from_orm_model(cls, obj: Any) -> "IncidentResponse":
        return cls(
            id=obj.id,
            incident_key=obj.incident_key,
            title=obj.title,
            description=obj.description,
            severity=IncidentSeverity(obj.severity),
            status=IncidentStatus(obj.status),
            environment=obj.environment,
            started_at=obj.started_at,
            ended_at=obj.ended_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            confidence=obj.confidence,
        )


class IncidentListResponse(BaseModel):
    """Paginated list envelope for incidents."""
    items: List[IncidentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class IncidentEventCreate(BaseModel):
    """Payload to associate an observability event with an incident."""
    event_id: str = Field(..., min_length=1, max_length=255, description="Canonical event ID from Ingestion Service")
    relation_type: RelationType = Field(..., description="Role of the signal in the incident")
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Optional correlation confidence score")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": "evt-001",
                "relation_type": "RELATED_ERROR",
                "score": 0.92
            }
        }
    )


class IncidentEventResponse(BaseModel):
    """Response representing an associated event link."""
    event_id: str
    relation_type: RelationType
    score: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "event_id": "evt-001",
                "relation_type": "RELATED_ERROR",
                "score": 0.92,
                "created_at": "2026-08-29T12:05:00Z"
            }
        }
    )

    @classmethod
    def from_orm_model(cls, obj: Any) -> "IncidentEventResponse":
        return cls(
            event_id=obj.event_id,
            relation_type=RelationType(obj.relation_type),
            score=obj.score,
            created_at=obj.created_at,
        )


class HealthResponse(BaseModel):
    """Health check response."""
    service: str = "incident-service"
    status: str = "healthy"
