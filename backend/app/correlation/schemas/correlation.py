from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SignalType(str, Enum):
    """Types of observability signals that can be correlated."""
    EVENT = "EVENT"
    ANOMALY = "ANOMALY"
    DEPLOYMENT = "DEPLOYMENT"
    ALERT = "ALERT"
    TRACE = "TRACE"


class GroupStatus(str, Enum):
    """Lifecycle status of a correlation group."""
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class SignalInput(BaseModel):
    """Candidate observability signal submitted for correlation analysis."""
    signal_id: str = Field(..., min_length=1, max_length=255, description="Unique signal identifier")
    signal_type: SignalType = Field(..., description="Canonical signal category")
    timestamp: datetime = Field(..., description="Timestamp of the signal (timezone-aware)")
    service: str = Field(..., min_length=1, max_length=128, description="Target or origin service name")
    environment: str = Field(..., min_length=1, max_length=64, description="Target environment")
    severity: str = Field(..., min_length=1, max_length=32, description="Severity of the signal")
    source_reference: Optional[str] = Field(None, max_length=255, description="External reference ID (e.g. evt-001)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary attributes such as trace_id, metric_name")

    @field_validator("timestamp")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("Timestamp must be timezone-aware (e.g. 2026-08-29T12:00:00Z)")
        return v


class CorrelationEvaluationRequest(BaseModel):
    """Request payload for dry-run correlation evaluation across candidate signals."""
    signals: List[SignalInput] = Field(..., min_length=2, description="List of at least two signals to evaluate")


class CorrelationEvaluationResponse(BaseModel):
    """Output from evaluating correlation across candidate signals."""
    correlation_score: float = Field(..., ge=0.0, le=1.0, description="Normalized composite correlation score")
    is_correlated: bool = Field(..., description="Whether composite score meets the configured threshold")
    reasons: List[str] = Field(default_factory=list, description="Deterministic explainable evidence reasons")


class CorrelationGroupSignalResponse(BaseModel):
    """Public representation of an individual signal in a correlation group."""
    signal_id: str
    signal_type: SignalType
    service: str
    environment: str
    timestamp: datetime
    severity: str
    source_reference: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    relationship_score: float
    relationship_reasons: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CorrelationGroupCreateRequest(BaseModel):
    """Request to create and persist a new correlation group from candidate signals."""
    signals: List[SignalInput] = Field(..., min_length=2, description="Signals to group and persist")
    status: Optional[GroupStatus] = Field(GroupStatus.CANDIDATE, description="Initial group status")


class CorrelationGroupResponse(BaseModel):
    """Public representation of a persisted correlation group."""
    group_key: str
    environment: str
    primary_service: str
    started_at: datetime
    ended_at: datetime
    correlation_score: float
    status: GroupStatus
    reasons: List[str] = Field(default_factory=list)
    incident_key: Optional[str] = None
    signals: List[CorrelationGroupSignalResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, obj: Any) -> "CorrelationGroupResponse":
        return cls(
            group_key=obj.group_key,
            environment=obj.environment,
            primary_service=obj.primary_service,
            started_at=obj.started_at,
            ended_at=obj.ended_at,
            correlation_score=obj.correlation_score,
            status=GroupStatus(obj.status),
            reasons=obj.reasons if obj.reasons is not None else [],
            incident_key=obj.incident_key,
            signals=[
                CorrelationGroupSignalResponse(
                    signal_id=s.signal_id,
                    signal_type=SignalType(s.signal_type),
                    service=s.service,
                    environment=s.environment,
                    timestamp=s.timestamp,
                    severity=s.severity,
                    source_reference=s.source_reference,
                    metadata=s.metadata_json if s.metadata_json is not None else {},
                    relationship_score=s.relationship_score,
                    relationship_reasons=s.relationship_reasons if s.relationship_reasons is not None else [],
                )
                for s in (obj.signals or [])
            ],
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class CorrelationGroupListResponse(BaseModel):
    """Paginated list envelope for correlation groups."""
    items: List[CorrelationGroupResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response schema."""
    service: str = "correlation-service"
    status: str = "healthy"
