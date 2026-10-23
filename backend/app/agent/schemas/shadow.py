from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ShadowModeRequest(BaseModel):
    """Request payload for passive shadow-mode incident evaluation."""
    incident_key: str = Field(..., description="Unique incident identifier to analyze in shadow mode")
    lookback_minutes: int = Field(60, ge=5, le=1440, description="Telemetry window lookback in minutes")
    replay_fixture_path: Optional[str] = Field(None, description="Optional path to sanitized replay fixture")
    redact_secrets: bool = Field(True, description="Whether to mask sensitive tokens, credentials, and PII")


class ShadowModeResponse(BaseModel):
    """Response returned from passive shadow-mode execution."""
    shadow_run_id: str
    incident_key: str
    investigation_key: str
    execution_mode: str = "SHADOW_PASSIVE"
    is_shadow_mode: bool = True
    live_telemetry_verified: bool = False
    telemetry_provenance: str = "SANITIZED_REPLAY_FIXTURE"
    status: str
    leading_hypothesis: Optional[str] = None
    confidence: float = 0.0
    latency_ms: float = 0.0
    is_fallback: bool = True
    secrets_redacted_count: int = 0
    repair_workflow_triggered: bool = False
    git_mutations_count: int = 0
    org_id: str
    created_at: datetime
