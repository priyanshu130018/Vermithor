import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LogCategory(str, Enum):
    """Categorization of operational logs."""
    DATABASE = "DATABASE"
    NETWORK = "NETWORK"
    AUTHENTICATION = "AUTHENTICATION"
    CACHE = "CACHE"
    HTTP = "HTTP"
    RESOURCE = "RESOURCE"
    DEPLOYMENT = "DEPLOYMENT"
    UNKNOWN = "UNKNOWN"


class LogIngestRequest(BaseModel):
    """Payload for ingesting a single observability log event."""
    source_event_id: str = Field(..., min_length=1, max_length=255)
    timestamp: datetime
    service: str = Field(..., min_length=1, max_length=128)
    environment: str = Field(..., min_length=1, max_length=64)
    severity: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1)
    trace_id: Optional[str] = Field(None, max_length=255)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LogBatchIngestRequest(BaseModel):
    """Payload for batch ingesting observability logs."""
    logs: List[LogIngestRequest] = Field(..., min_length=1)


class LogEmbeddingMetadataResponse(BaseModel):
    """Metadata describing a generated log embedding."""
    model_name: str
    model_version: Optional[str] = None
    dimension: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessedLogResponse(BaseModel):
    """Structured and normalized representation of a log."""
    id: uuid.UUID
    source_event_id: str
    timestamp: datetime
    service: str
    environment: str
    severity: str
    category: LogCategory
    raw_message: str
    normalized_message: str
    template: str
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[LogEmbeddingMetadataResponse] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LogBatchIngestResponse(BaseModel):
    """Batch ingestion response envelope."""
    processed: int
    items: List[ProcessedLogResponse]


class SemanticSearchRequest(BaseModel):
    """Query payload for semantic similarity vector search."""
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    service: Optional[str] = None
    environment: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[LogCategory] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    min_similarity: Optional[float] = Field(None, ge=-1.0, le=1.0)


class SearchResultItem(BaseModel):
    """Individual match from a semantic vector search query."""
    log_id: uuid.UUID
    source_event_id: str
    timestamp: datetime
    service: str
    environment: str
    severity: str
    category: LogCategory
    message: str
    normalized_message: str
    template: str
    similarity_score: float = Field(..., ge=-1.0, le=1.0)


class SemanticSearchResponse(BaseModel):
    """Complete semantic vector search result response."""
    query: str
    total_results: int
    results: List[SearchResultItem]


class HealthResponse(BaseModel):
    """Health check endpoint schema."""
    service: str = "log-intelligence-service"
    status: str = "healthy"


class ReadinessResponse(BaseModel):
    """Readiness endpoint schema reporting model load status."""
    service: str = "log-intelligence-service"
    status: str = "ready"
    embedding_model_loaded: bool
    model_name: str
    dimension: int


# ==============================================================================
# HDBSCAN Log Clustering Schemas
# ==============================================================================

class LogClusterItem(BaseModel):
    """Structured representation of a semantic log cluster discovered by HDBSCAN."""
    cluster_id: int = Field(..., description="Unique cluster identifier (-1 indicates noise/outlier)")
    label: str = Field(..., description="Deterministic, human-readable summary label")
    category: LogCategory = Field(..., description="Dominant operational domain category")
    size: int = Field(..., ge=1, description="Total number of log messages in this cluster")
    is_noise: bool = Field(False, description="True if this group contains unclustered outlier logs")
    representative_messages: List[str] = Field(default_factory=list, description="Top representative log messages")
    services: List[str] = Field(default_factory=list, description="List of affected service names")
    environments: List[str] = Field(default_factory=list, description="List of affected environments")
    first_seen: datetime = Field(..., description="Earliest log timestamp in this cluster")
    last_seen: datetime = Field(..., description="Latest log timestamp in this cluster")
    severity_distribution: Dict[str, int] = Field(default_factory=dict, description="Counts of logs by severity level")
    log_ids: List[Any] = Field(default_factory=list, description="List of log IDs belonging to this cluster")
    trace_ids: List[str] = Field(default_factory=list, description="Distinct trace IDs associated with this cluster")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Average clustering membership probability")


class LogClusteringRequest(BaseModel):
    """Parameters for running or filtering log clustering."""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    service: Optional[str] = None
    environment: Optional[str] = None
    min_cluster_size: Optional[int] = Field(None, ge=2, description="Override minimum cluster size")
    min_samples: Optional[int] = Field(None, ge=1, description="Override minimum samples")
    include_noise: bool = Field(True, description="Whether to include noise/outlier cluster in output")


class LogClusteringResponse(BaseModel):
    """Response envelope for log clustering analysis."""
    total_logs: int
    total_clusters: int
    noise_count: int
    duration_ms: float
    clusters: List[LogClusterItem]
