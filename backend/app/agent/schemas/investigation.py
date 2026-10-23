import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class InvestigationStatus(str, Enum):
    """Lifecycle status of an AI incident investigation."""
    PENDING = "PENDING"
    INVESTIGATING = "INVESTIGATING"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class InvestigationRequest(BaseModel):
    """Request payload to initiate or retrieve an incident investigation."""
    incident_key: str = Field(..., min_length=1, max_length=64, description="Canonical incident identifier (e.g. INC-2026-1042)")
    lookback_minutes: int = Field(default=30, ge=5, le=1440, description="Investigation time window before incident start (in minutes)")
    allow_additional_queries: bool = Field(default=True, description="Whether the agent may query additional telemetry if evidence is missing")
    max_additional_queries: int = Field(default=2, ge=0, le=5, description="Maximum bounded query iterations to prevent runaway loops")
    force_refresh: bool = Field(default=False, description="Force a new investigation instead of returning cached result")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "incident_key": "INC-2026-1042",
                "lookback_minutes": 30,
                "allow_additional_queries": True,
                "max_additional_queries": 2,
                "force_refresh": False,
            }
        }
    )


class InvestigationEvidenceItem(BaseModel):
    """Preserved evidence unit with explicit provenance, IDs, and timestamps."""
    evidence_id: str = Field(..., description="Unique evidence reference ID (e.g. EV-METRIC-01)")
    source_type: str = Field(..., description="Evidence source type (PROMETHEUS, JAEGER, EVENT, ANOMALY, DEPLOYMENT, TOPOLOGY)")
    source_id: str = Field(..., description="Original telemetry ID, observation ID, event ID, or trace ID")
    service: str = Field(..., description="Associated service or infrastructure component")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of observation or event")
    claim: str = Field(..., description="Observable factual claim backed by this evidence")
    data: Dict[str, Any] = Field(default_factory=dict, description="Raw or normalized telemetry attributes")
    is_verified: bool = Field(default=True, description="Whether this citation is verified against tenant and incident data")
    verification_status: str = Field(default="VALID", description="Verification classification: VALID, MISSING_OR_UNRESOLVED, MALFORMED, CROSS_TENANT, CROSS_INCIDENT, STALE")


class HypothesisEvaluation(BaseModel):
    """Evaluation of a specific root-cause hypothesis against gathered evidence."""
    hypothesis: str = Field(..., description="Candidate root-cause explanation")
    candidate_type: str = Field(..., description="Category (e.g. DATABASE, DEPLOYMENT, CACHE, UNKNOWN)")
    original_score: float = Field(..., ge=0.0, le=1.0, description="Unmodified score from existing RCA engine")
    calibrated_status: str = Field(..., description="Evidence status: CONFIRMED, PLAUSIBLE, DISPROVEN, or INCONCLUSIVE")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="IDs of evidence supporting this hypothesis")
    contradicting_evidence_ids: List[str] = Field(default_factory=list, description="IDs of evidence contradicting this hypothesis")
    reasoning: str = Field(..., description="Grounding justification explaining why this hypothesis was accepted or challenged")


class DiagnosticStep(BaseModel):
    """Operational recommendation for human SRE review. Strictly non-autonomous."""
    action: str = Field(..., description="Recommended diagnostic or verification procedure")
    target_service: str = Field(..., description="Component to examine")
    rationale: str = Field(..., description="Justification grounded in evidence or runbook")
    priority: str = Field(default="MEDIUM", description="Suggested urgency (HIGH, MEDIUM, LOW)")
    requires_human_approval: bool = Field(default=True, description="Strict operational safeguard: must always require human review")


class InvestigationReport(BaseModel):
    """Structured, evidence-backed final incident investigation report."""
    investigation_id: str = Field(..., description="Unique investigation key or ID")
    incident_key: str = Field(..., description="Associated incident key")
    title: str = Field(..., description="Incident title")
    target_service: str = Field(..., description="Primary service under investigation")
    environment: str = Field(..., description="Deployment environment")
    time_window: Dict[str, Any] = Field(..., description="Bounded time window (start, end, lookback)")
    observed_facts: List[str] = Field(default_factory=list, description="Factual, verifiable observations directly from telemetry")
    inferred_relationships: List[str] = Field(default_factory=list, description="Causal or topological links inferred from events and traces")
    leading_hypothesis: str = Field(..., description="Primary root-cause hypothesis")
    hypothesis_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in leading hypothesis (preserves RCA ranking)")
    hypotheses_evaluated: List[HypothesisEvaluation] = Field(default_factory=list, description="All evaluated candidate hypotheses")
    alternative_explanations: List[str] = Field(default_factory=list, description="Alternative root causes considered but ranked lower")
    confirmed_findings: List[str] = Field(default_factory=list, description="Findings confirmed by definitive telemetry evidence")
    missing_evidence: List[str] = Field(default_factory=list, description="Telemetry or logs that were unavailable or needed for complete diagnosis")
    contradictory_evidence: List[str] = Field(default_factory=list, description="Evidence conflicting with the leading hypothesis")
    uncertainty_assessment: str = Field(..., description="Honest evaluation of uncertainty and evidence gaps")
    recommended_diagnostic_steps: List[DiagnosticStep] = Field(default_factory=list, description="Suggested diagnostic procedures for SREs")
    runbook_references: List[Dict[str, Any]] = Field(default_factory=list, description="Retrieved operational runbooks with excerpts")
    evidence_items: List[InvestigationEvidenceItem] = Field(default_factory=list, description="Catalog of evidence citations")
    model_provider: str = Field(..., description="LLM provider name or 'fallback'")
    model_name: Optional[str] = Field(None, description="LLM model identifier or 'deterministic-rules (non-LLM)'")
    is_fallback: bool = Field(default=False, description="True if deterministic fallback was activated")
    model_call_records: List[Dict[str, Any]] = Field(default_factory=list, description="Audit trace of individual model invocations")
    review_assessment: Optional[Dict[str, Any]] = Field(default=None, description="Report review evaluation result")


class InvestigationResponse(BaseModel):
    """API response model for an incident investigation."""
    id: uuid.UUID
    investigation_key: str
    incident_key: str
    status: InvestigationStatus
    target_service: str
    environment: str
    leading_hypothesis: Optional[str] = None
    confidence: float = 0.0
    is_fallback: bool = False
    model_provider: str = "unknown"
    model_name: Optional[str] = None
    report: Optional[InvestigationReport] = None
    model_call_records: List[Dict[str, Any]] = Field(default_factory=list, description="Audit trace of individual model invocations")
    review_assessment: Optional[Dict[str, Any]] = Field(default=None, description="Report review evaluation result")
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
