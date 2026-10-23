from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class IntegrationType(str, Enum):
    PROMETHEUS = "PROMETHEUS"
    JAEGER = "JAEGER"
    OPENTELEMETRY = "OPENTELEMETRY"
    REPLAY_MODE = "REPLAY_MODE"


class IntegrationStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED_UNVERIFIED = "CONFIGURED_UNVERIFIED"
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"
    REVOKED = "REVOKED"


class TelemetryProvenance(str, Enum):
    LIVE_CUSTOMER_TELEMETRY = "LIVE_CUSTOMER_TELEMETRY"
    SANITIZED_REPLAY_FIXTURE = "SANITIZED_REPLAY_FIXTURE"
    MOCKED_FIXTURE = "MOCKED_FIXTURE"
    NOT_VERIFIED = "NOT_VERIFIED"


class OnboardingStep(str, Enum):
    CONFIRM_IDENTITY = "CONFIRM_IDENTITY"
    REVIEW_POLICY = "REVIEW_POLICY"
    SELECT_TELEMETRY = "SELECT_TELEMETRY"
    VALIDATE_CONFIG = "VALIDATE_CONFIG"
    CONNECTIVITY_CHECK = "CONNECTIVITY_CHECK"
    SAMPLE_INVESTIGATION = "SAMPLE_INVESTIGATION"
    RECORD_FEEDBACK = "RECORD_FEEDBACK"
    VIEW_READINESS = "VIEW_READINESS"


# --- Request Schemas ---

class IntegrationConfigureRequest(BaseModel):
    integration_type: IntegrationType = Field(..., description="Type of telemetry provider")
    name: str = Field(..., min_length=2, max_length=128, description="Human readable name")
    endpoint_url: Optional[str] = Field(None, max_length=255, description="Provider base URL (HTTPS or approved internal)")
    auth_type: str = Field("NONE", description="Authentication mechanism ('NONE', 'BEARER', 'BASIC', 'API_KEY')")
    auth_credential: Optional[str] = Field(None, max_length=512, description="Secret token/key (masked upon receipt)")
    allow_internal_hosts: bool = Field(True, description="Allow internal docker network hosts (e.g. prometheus:9090)")


class OnboardingStepRequest(BaseModel):
    step: OnboardingStep = Field(..., description="Onboarding step identifier being completed")
    notes: Optional[str] = Field(None, max_length=500, description="Optional administrator notes")
    acknowledged_read_only: Optional[bool] = Field(None, description="Explicit agreement to strict read-only boundary")


class GovernancePolicyUpdateRequest(BaseModel):
    collection_enabled: Optional[bool] = Field(None, description="Kill-switch to toggle new telemetry collection")
    investigations_paused: Optional[bool] = Field(None, description="Pause incoming investigation triggers")
    allow_external_llm: Optional[bool] = Field(None, description="Explicit authorization to transmit telemetry to external LLMs")
    redact_sensitive_fields: Optional[bool] = Field(None, description="Scrub PII and secrets before persistence")
    retention_days: Optional[int] = Field(None, ge=1, le=365, description="Retention window in days for pilot incident data")


class DataPurgeRequest(BaseModel):
    confirm_organization_id: str = Field(..., description="Confirmation of organization ID to purge")
    incident_key: Optional[str] = Field(None, description="Optional specific incident to purge; omit to purge all org data")
    purge_all_pilot_data: bool = Field(False, description="Explicit flag to purge all investigations, feedback, and telemetry")


# --- Response Schemas ---

class IntegrationResponse(BaseModel):
    id: uuid.UUID
    org_id: str
    integration_type: IntegrationType
    name: str
    endpoint_url: Optional[str] = None
    status: IntegrationStatus
    is_verified: bool
    verified_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    last_error: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    auth_type: str
    auth_credentials_masked: Optional[str] = None
    telemetry_provenance: TelemetryProvenance
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntegrationVerifyResponse(BaseModel):
    id: uuid.UUID
    integration_type: IntegrationType
    name: str
    status: IntegrationStatus
    reachable: bool
    is_verified: bool
    telemetry_provenance: TelemetryProvenance
    probe_latency_ms: Optional[float] = None
    message: str
    active_targets_count: Optional[int] = None
    error: Optional[str] = None


class GovernancePolicyResponse(BaseModel):
    id: uuid.UUID
    org_id: str
    onboarding_completed: bool
    current_onboarding_step: int
    completed_steps: List[str]
    collection_enabled: bool
    investigations_paused: bool
    allow_external_llm: bool
    redact_sensitive_fields: bool
    retention_days: int
    acknowledged_read_only: bool
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class DataPurgeResponse(BaseModel):
    status: str
    org_id: str
    incident_key: Optional[str] = None
    deleted_investigations_count: int
    deleted_feedback_count: int
    deleted_repairs_count: int
    deleted_observations_count: int
    deleted_events_count: int
    cache_keys_purged: int
    queued_tasks_revoked: int
    purged_at: datetime
    message: str


class PilotAuditLogResponse(BaseModel):
    id: uuid.UUID
    org_id: str
    actor_sub: str
    actor_role: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details_json: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PilotReadinessResponse(BaseModel):
    org_id: str
    onboarding_completed: bool
    current_step: int
    completed_steps: List[str]
    integrations: List[IntegrationResponse]
    last_telemetry_check: Optional[Dict[str, Any]] = None
    latest_investigation: Optional[Dict[str, Any]] = None
    evidence_completeness: Dict[str, Any]
    abstentions_and_unresolved: Dict[str, Any]
    operator_feedback_history: List[Dict[str, Any]]
    rate_limit_and_resilience: Dict[str, Any]
    provenance_breakdown: Dict[str, Any]
    governance_policy: Dict[str, Any]
    blockers: List[str]
    readiness_verdict: str  # e.g. "GO_REPLAY_PILOT", "CONDITIONAL_GO_LIVE_PILOT", "NO_GO"
    readiness_summary: str
