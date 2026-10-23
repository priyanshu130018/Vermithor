from typing import Any, Dict, List, Optional, TypedDict


class RepairState(TypedDict, total=False):
    """
    Typed state object managed across the LangGraph AI Code Repair workflow.
    Tracks investigation handoff, repository authorization, inspected code,
    patch proposal, security review, sandboxed validation, and review artifacts.
    """
    # Identifiers
    repair_key: str
    investigation_key: str
    incident_key: str
    target_service: str

    # Repository & Authorization
    repository_url: Optional[str]
    target_branch: str
    repair_branch: Optional[str]
    base_commit: Optional[str]
    is_read_only_pilot: bool
    pilot_audit_notice: Optional[str]
    is_authorized: bool
    authorization_error: Optional[str]


    # Investigation Input & Evidence
    investigation_report: Optional[Dict[str, Any]]
    confidence: float
    evidence_citations: List[str]
    has_sufficient_evidence: bool

    # Code Inspection
    inspected_files: Dict[str, str]  # file_path -> content
    inspected_file_paths: List[str]

    # Code-Level Hypothesis & Patch Generation
    suspected_defect: Optional[str]
    proposed_patch: Optional[str]
    patch_hash: Optional[str]
    files_changed: List[str]
    expected_behavior: Optional[str]
    potential_regressions: List[str]
    security_implications: List[str]

    # Patch Review & Safety
    patch_review_passed: bool
    review_notes: List[str]

    # Isolated Validation Execution
    custom_test_command: Optional[str]
    validation_status: str  # VALIDATED | VALIDATION_FAILED | VALIDATION_BLOCKED | SKIPPED
    validation_result: Optional[Dict[str, Any]]
    test_commands: List[str]

    # Pull Request & Approval
    auto_create_pr: bool
    pull_request_url: Optional[str]
    pull_request_number: Optional[int]
    requires_human_approval: bool
    approval_status: str

    # Agent Iteration & Fallback Tracking
    iteration_count: int
    max_iterations: int
    model_provider: str
    model_name: Optional[str]
    is_fallback: bool

    # Workflow Termination
    status: str
    error_message: Optional[str]
    report: Optional[Dict[str, Any]]
