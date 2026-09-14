from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CandidateType(str, Enum):
    """Categorization of root cause candidates."""
    DATABASE = "DATABASE"
    DEPLOYMENT = "DEPLOYMENT"
    SERVICE = "SERVICE"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    NETWORK = "NETWORK"
    DEPENDENCY = "DEPENDENCY"
    RESOURCE = "RESOURCE"
    UNKNOWN = "UNKNOWN"


class AnalysisStatus(str, Enum):
    """Lifecycle status of an RCA analysis."""
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvidenceType(str, Enum):
    """Types of evidence supporting root cause reasoning."""
    TEMPORAL = "TEMPORAL"
    ANOMALY = "ANOMALY"
    SERVICE = "SERVICE"
    TRACE = "TRACE"
    DEPLOYMENT = "DEPLOYMENT"
    ERROR = "ERROR"
    METRIC = "METRIC"
    CORRELATION = "CORRELATION"
    DEPENDENCY = "DEPENDENCY"
    LOG_CLUSTER = "LOG_CLUSTER"
    TOPOLOGY = "TOPOLOGY"
    HISTORICAL = "HISTORICAL"


class EvidenceItem(BaseModel):
    """Structured evidence item supporting a candidate or edge."""
    type: EvidenceType
    description: str
    strength: float = Field(..., ge=0.0, le=1.0)


class EvidenceBreakdown(BaseModel):
    """Multi-dimensional categorized evidence summary for explainable root cause reasoning."""
    temporal: Optional[str] = Field(None, description="Temporal sequence and timing evidence")
    metric: Optional[str] = Field(None, description="Observed metric anomaly deviations and percentages")
    log: Optional[str] = Field(None, description="Log messages or cluster error summaries")
    trace: Optional[str] = Field(None, description="Span latency bottlenecks and distributed trace status")
    topology: Optional[str] = Field(None, description="Service dependency path and propagation validation")
    deployment: Optional[str] = Field(None, description="Preceding software deployment details")
    historical: Optional[str] = Field(None, description="Past incident similarity and resolution references")


class CausalChainNode(BaseModel):
    """An individual step in the reconstructed causal sequence."""
    signal_id: str
    signal_type: str
    service: str
    role: str
    timestamp: datetime
    description: str


class RootCauseCandidateResponse(BaseModel):
    """Evaluated and ranked root cause candidate."""
    candidate_type: CandidateType
    candidate_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rank: int = Field(..., ge=1)
    is_primary: bool
    affected_services: List[str] = Field(default_factory=list)
    evidence_breakdown: Optional[EvidenceBreakdown] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CausalEdgeResponse(BaseModel):
    """Directed causal relationship between two signals."""
    source_signal_id: str
    target_signal_id: str
    relationship: str
    score: float
    evidence: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class RCAAnalysisResponse(BaseModel):
    """Complete RCA analysis output representation."""
    analysis_key: str
    group_key: str
    analysis_version: str
    status: AnalysisStatus
    primary_root_cause: str
    primary_confidence: float = Field(..., ge=0.0, le=1.0)
    causal_chain: List[CausalChainNode] = Field(default_factory=list)
    candidates: List[RootCauseCandidateResponse] = Field(default_factory=list)
    edges: List[CausalEdgeResponse] = Field(default_factory=list)
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, obj: Any) -> "RCAAnalysisResponse":
        return cls(
            analysis_key=obj.analysis_key,
            group_key=obj.group_key,
            analysis_version=obj.analysis_version,
            status=AnalysisStatus(obj.status),
            primary_root_cause=obj.primary_root_cause,
            primary_confidence=obj.primary_confidence,
            causal_chain=[
                CausalChainNode(**item) if isinstance(item, dict) else item
                for item in (obj.causal_chain or [])
            ],
            candidates=[
                RootCauseCandidateResponse(
                    candidate_type=CandidateType(c.candidate_type),
                    candidate_name=c.candidate_name,
                    score=c.score,
                    confidence=getattr(c, "confidence", c.score),
                    rank=c.rank,
                    is_primary=c.is_primary,
                    affected_services=getattr(c, "affected_services", []),
                    evidence_breakdown=(
                        EvidenceBreakdown(**c.evidence_breakdown)
                        if isinstance(getattr(c, "evidence_breakdown", None), dict)
                        else getattr(c, "evidence_breakdown", None)
                    ),
                    evidence=[
                        EvidenceItem(**ev) if isinstance(ev, dict) else ev
                        for ev in (c.evidence or [])
                    ],
                )
                for c in (obj.candidates or [])
            ],
            edges=[
                CausalEdgeResponse(
                    source_signal_id=e.source_signal_id,
                    target_signal_id=e.target_signal_id,
                    relationship=e.relationship,
                    score=e.score,
                    evidence=e.evidence if e.evidence is not None else {},
                )
                for e in (obj.edges or [])
            ],
            error_message=obj.error_message,
            started_at=obj.started_at,
            completed_at=obj.completed_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class RCAAnalysisListResponse(BaseModel):
    """Paginated list envelope for RCA analyses."""
    items: List[RCAAnalysisResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response schema."""
    service: str = "rca-service"
    status: str = "healthy"
