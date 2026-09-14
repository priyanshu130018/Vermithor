from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    """Categorization of retrieval sources."""
    LOG = "LOG"
    INCIDENT = "INCIDENT"
    RCA = "RCA"
    RUNBOOK = "RUNBOOK"
    DEPLOYMENT = "DEPLOYMENT"


class RetrievalQuery(BaseModel):
    """Query payload for multi-source hybrid retrieval."""
    query: Optional[str] = None
    incident_key: Optional[str] = None
    group_key: Optional[str] = None
    service: Optional[str] = None
    environment: Optional[str] = None
    severity: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    top_k: int = Field(5, ge=1, le=20)
    source_types: Optional[List[SourceType]] = None
    min_score: Optional[float] = None


class RetrievalResultItem(BaseModel):
    """Normalized retrieval match across heterogeneous sources."""
    source_type: SourceType
    source_id: str
    title: str
    content: str
    service: Optional[str] = None
    environment: Optional[str] = None
    timestamp: Optional[datetime] = None
    similarity_score: float = Field(0.0, ge=0.0, le=1.0)
    metadata_score: float = Field(0.0, ge=0.0, le=1.0)
    recency_score: float = Field(0.0, ge=0.0, le=1.0)
    source_score: float = Field(0.0, ge=0.0, le=1.0)
    final_score: float = Field(0.0, ge=0.0, le=1.0)
    citation: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class RetrievalResponse(BaseModel):
    """Response envelope for hybrid retrieval search."""
    query: str
    incident_key: Optional[str] = None
    total_results: int
    sources_attempted: int
    sources_available: int
    warnings: List[str] = Field(default_factory=list)
    results: List[RetrievalResultItem]


class RAGContextRequest(BaseModel):
    """Request payload to assemble grounded RAG context for LLM synthesis."""
    query: Optional[str] = None
    incident_key: Optional[str] = None
    top_k: int = Field(10, ge=1, le=20)
    source_types: Optional[List[SourceType]] = None


class RAGContextResponse(BaseModel):
    """Grounded RAG context assembled for LLM consumption."""
    query: str
    incident_key: Optional[str] = None
    total_results: int
    included_results: int
    truncated: bool
    warnings: List[str] = Field(default_factory=list)
    context: List[RetrievalResultItem]
    context_text: str


class HealthResponse(BaseModel):
    """Health check response schema."""
    service: str = "retrieval-service"
    status: str = "healthy"
