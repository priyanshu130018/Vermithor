import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(str, Enum):
    """Canonical event types supported by Vermithor."""
    LOG = "LOG"
    METRIC = "METRIC"
    TRACE = "TRACE"
    DEPLOYMENT = "DEPLOYMENT"
    ALERT = "ALERT"


class Severity(str, Enum):
    """Severity levels for observability events."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ProcessingStatus(str, Enum):
    """Asynchronous processing lifecycle status for an event."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class EventBase(BaseModel):
    """Base schema for an observability event."""
    event_id: str = Field(..., min_length=1, max_length=255, description="Unique client/system event identifier")
    timestamp: datetime = Field(..., description="Timestamp when the event occurred (timezone-aware)")
    service: str = Field(..., min_length=1, max_length=128, description="Source service or application name")
    environment: str = Field(..., min_length=1, max_length=64, description="Environment (e.g. production, staging)")
    event_type: EventType = Field(..., description="Canonical event type")
    severity: Severity = Field(..., description="Event severity level")
    message: str = Field(..., min_length=1, description="Event message or log payload")
    trace_id: Optional[str] = Field(None, max_length=255, description="Optional distributed trace identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary contextual metadata")

    @field_validator("timestamp")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("Timestamp must be timezone-aware (e.g. 2026-08-27T15:00:00Z)")
        return v


class EventCreate(EventBase):
    """Payload for ingesting a new event."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": "evt-001",
                "timestamp": "2026-08-27T15:00:00Z",
                "service": "booking-api",
                "environment": "production",
                "event_type": "LOG",
                "severity": "ERROR",
                "message": "database connection timeout",
                "trace_id": "trace-001",
                "metadata": {
                    "host": "booking-api-01",
                    "region": "ap-south-1"
                }
            }
        }
    )


class EventResponse(BaseModel):
    """Public representation of an ingested event including async processing lifecycle state."""
    id: uuid.UUID
    event_id: str
    timestamp: datetime
    service: str
    environment: str
    event_type: EventType
    severity: Severity
    message: str
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    processed_at: Optional[datetime] = None
    processing_error: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "event_id": "evt-001",
                "timestamp": "2026-08-27T15:00:00Z",
                "service": "booking-api",
                "environment": "production",
                "event_type": "LOG",
                "severity": "ERROR",
                "message": "database connection timeout",
                "trace_id": "trace-001",
                "metadata": {
                    "host": "booking-api-01",
                    "region": "ap-south-1"
                },
                "created_at": "2026-08-27T15:00:01Z",
                "processing_status": "PENDING",
                "processed_at": None,
                "processing_error": None
            }
        }
    )

    @classmethod
    def from_orm_model(cls, obj: Any) -> "EventResponse":
        """Construct response from ORM model mapping metadata_json -> metadata and status."""
        return cls(
            id=obj.id,
            event_id=obj.event_id,
            timestamp=obj.timestamp,
            service=obj.service,
            environment=obj.environment,
            event_type=EventType(obj.event_type),
            severity=Severity(obj.severity),
            message=obj.message,
            trace_id=obj.trace_id,
            metadata=obj.metadata_json if obj.metadata_json is not None else {},
            created_at=obj.created_at,
            processing_status=ProcessingStatus(obj.processing_status) if obj.processing_status else ProcessingStatus.PENDING,
            processed_at=obj.processed_at,
            processing_error=obj.processing_error,
        )


class EventListResponse(BaseModel):
    """Paginated response containing a list of events."""
    items: List[EventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response schema."""
    service: str = "ingestion-service"
    status: str = "healthy"
