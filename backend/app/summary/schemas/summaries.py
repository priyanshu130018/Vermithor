import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SummaryStatus(str, Enum):
    """Lifecycle states of an incident summary."""
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ImpactSchema(BaseModel):
    """Impact description of an incident."""
    services: List[str] = Field(default_factory=list)
    severity: str = "UNKNOWN"
    description: str = ""


class TimelineItemSchema(BaseModel):
    """Timestamped event in the incident timeline."""
    timestamp: Optional[str] = None
    event: str
    source: str = ""


class EvidenceItemSchema(BaseModel):
    """Evidence claim tied to a verified retrieval source."""
    evidence_id: Optional[str] = None
    claim: str
    source_type: str
    source_id: str
    support: str = ""


class RemediationItemSchema(BaseModel):
    """Remediation recommendation."""
    action: str
    priority: str = "MEDIUM"
    reason: str = ""


class IncidentSummaryGeneratedSchema(BaseModel):
    """Structured output expected from LLM synthesis."""
    executive_summary: str = Field(..., min_length=1)
    what_happened: str = Field(..., min_length=1)
    probable_root_cause: str = Field(..., min_length=1)
    impact: ImpactSchema = Field(default_factory=ImpactSchema)
    timeline: List[TimelineItemSchema] = Field(default_factory=list)
    evidence: List[EvidenceItemSchema] = Field(default_factory=list)
    remediation: List[RemediationItemSchema] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    limitations: List[str] = Field(default_factory=list)
    similar_incidents: List[Dict[str, Any]] = Field(default_factory=list)
    uncertainty: Optional[str] = None


class IncidentSummaryResponse(BaseModel):
    """API response model for an incident summary."""
    id: uuid.UUID
    summary_key: str
    incident_key: str
    status: SummaryStatus
    summary_version: str
    model_provider: str
    model_name: str
    executive_summary: Optional[str] = None
    what_happened: Optional[str] = None
    probable_root_cause: Optional[str] = None
    impact: ImpactSchema
    timeline: List[TimelineItemSchema]
    evidence: List[EvidenceItemSchema]
    remediation: List[RemediationItemSchema]
    confidence: float
    limitations: List[str]
    similar_incidents: List[Dict[str, Any]] = Field(default_factory=list)
    uncertainty: Optional[str] = None
    is_fallback: bool = False
    debug_rag_info: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    @property
    def incident_id(self) -> str:
        return self.incident_key

    @property
    def summary(self) -> Optional[str]:
        return self.executive_summary

    @property
    def root_cause(self) -> Optional[str]:
        return self.probable_root_cause

    @property
    def severity(self) -> str:
        return self.impact.severity if self.impact else "UNKNOWN"

    @property
    def affected_services(self) -> List[str]:
        return self.impact.services if self.impact else []

    @property
    def recommended_actions(self) -> List[RemediationItemSchema]:
        return self.remediation

    model_config = ConfigDict(from_attributes=True)


class IncidentSummaryListResponse(BaseModel):
    """Paginated list envelope for summaries."""
    items: List[IncidentSummaryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response."""
    service: str = "summary-service"
    status: str = "healthy"


class ReadinessResponse(BaseModel):
    """Readiness probe response reporting LLM provider availability."""
    service: str = "summary-service"
    status: str
    llm_provider: str
    model_name: str
    provider_available: bool
