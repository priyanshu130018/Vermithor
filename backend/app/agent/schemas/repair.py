from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class RepairStatus(str, Enum):
    """Lifecycle statuses for the LangGraph code repair agent."""
    PENDING = "PENDING"
    EVALUATING = "EVALUATING"
    INSPECTING_CODE = "INSPECTING_CODE"
    GENERATING_PATCH = "GENERATING_PATCH"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNAUTHORIZED = "UNAUTHORIZED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ValidationStatus(str, Enum):
    """Outcomes of running tests in the isolated sandboxed environment."""
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"
    SKIPPED = "SKIPPED"


class ApprovalStatus(str, Enum):
    """Human review approval states for proposed patches."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PatchFileChange(BaseModel):
    """Details of a single file altered in a proposed patch."""
    file_path: str
    change_type: str = "MODIFIED"
    lines_added: int = 0
    lines_removed: int = 0


class TestExecutionResult(BaseModel):
    """Structured report of test execution inside the disposable sandbox."""
    model_config = ConfigDict(extra="ignore")

    status: ValidationStatus
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    commands_run: List[str] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    error_message: Optional[str] = None
    environment_isolated: bool = False
    isolation_level: str = "HOST_SUBPROCESS_RESTRICTED"
    isolation_limitations: List[str] = Field(default_factory=list)


class RepairReport(BaseModel):
    """Evidence-backed code repair report prepared for human review."""
    model_config = ConfigDict(extra="ignore")

    incident_key: str
    investigation_key: str
    suspected_defect: str
    evidence_citations: List[str] = Field(default_factory=list)
    inspected_files: List[str] = Field(default_factory=list)
    files_and_lines_to_modify: List[Dict[str, Any]] = Field(default_factory=list)
    proposed_patch: Optional[str] = None
    patch_hash: Optional[str] = None
    expected_behavior: str = ""
    potential_regressions: List[str] = Field(default_factory=list)
    security_implications: List[str] = Field(default_factory=list)
    tests_required: List[str] = Field(default_factory=list)
    remaining_uncertainty: str = ""
    validation_result: Optional[TestExecutionResult] = None
    pull_request_url: Optional[str] = None
    pull_request_number: Optional[int] = None
    requires_human_approval: bool = True
    model_provider: str = "unknown"
    model_name: Optional[str] = None
    is_fallback: bool = False


class RepairRequest(BaseModel):
    """Input payload to initiate or retrieve a code repair workflow."""
    investigation_key: str = Field(..., description="Canonical investigation key (INV-...)")
    repository_url: Optional[str] = Field(None, description="Repository identifier, URL, or local path")
    target_branch: str = Field("main", description="Target repository branch for repair inspection")
    custom_test_command: Optional[str] = Field(None, description="Optional restricted test command to run")
    auto_create_pr: bool = Field(False, description="Whether to open a draft PR if Git provider credentials are configured")


class ApprovalRequest(BaseModel):
    """Input payload for human review decision on an awaiting repair."""
    action: str = Field(..., description="Decision: 'APPROVE' or 'REJECT'")
    notes: Optional[str] = Field(None, description="Human reviewer explanation or comments (required for REJECT)")
    reviewer: Optional[str] = Field(None, description="Identifier of the human reviewer")
    expected_patch_hash: Optional[str] = Field(None, description="SHA-256 hash of reviewed patch to prevent stale approvals")


class RepairResponse(BaseModel):
    """API response model for a code repair job and its current status."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    repair_key: str
    investigation_key: str
    incident_key: str
    status: RepairStatus
    repository_url: Optional[str] = None
    base_commit: Optional[str] = None
    target_branch: str
    repair_branch: Optional[str] = None
    suspected_defect: Optional[str] = None
    evidence_citations: Optional[List[str]] = None
    inspected_files: Optional[List[str]] = None
    proposed_patch: Optional[str] = None
    patch_hash: Optional[str] = None
    files_changed: Optional[List[str]] = None
    test_commands: Optional[List[str]] = None
    test_results: Optional[Dict[str, Any]] = None
    validation_status: ValidationStatus
    pull_request_url: Optional[str] = None
    pull_request_number: Optional[int] = None
    requires_human_approval: bool
    approval_status: ApprovalStatus
    approved_by: Optional[str] = None
    approval_notes: Optional[str] = None
    approved_at: Optional[datetime] = None
    model_provider: str
    model_name: Optional[str] = None
    is_fallback: bool
    iteration_count: int
    error_message: Optional[str] = None
    report_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
