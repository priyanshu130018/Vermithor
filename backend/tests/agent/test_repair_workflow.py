from pathlib import Path
from unittest.mock import MagicMock
import pytest
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation
from backend.app.agent.git.local_provider import LocalGitProvider
from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.graph.repair_workflow import create_repair_graph
from backend.app.agent.runner.sandbox import IsolatedTestRunner
from backend.app.agent.schemas.repair import RepairRequest, RepairStatus, ValidationStatus
from backend.app.agent.services.repair_service import RepairService
from backend.tests.agent.conftest import FakeFailingLLM, FakeValidLLM


@pytest.fixture
def test_investigation_record(db_session: Session) -> Investigation:
    """Creates a completed investigation record in test session."""
    inv = Investigation(
        investigation_key="INV-TEST-001",
        incident_key="INC-2026-1042",
        status="COMPLETED",
        target_service="payment-api",
        environment="production",
        leading_hypothesis="Database connection pool exhaustion on payment-api",
        confidence=0.88,
        is_fallback=False,
        model_provider="mock_llm",
        evidence_json=[
            {"id": "EV-PROM-1", "description": "Database connection pool utilization reached 1.0 (100% capacity)"},
            {"id": "EV-TRACE-1", "description": "ConnectionAcquisitionTimeoutException on /api/v1/payments/charge"},
        ],
        report_json={
            "observed_facts": [
                "Database connection pool utilization reached 1.0 (100% capacity)",
                "HikariCP pool PaymentPool exhausted after deployment v2.8.4",
            ],
            "leading_hypothesis": "Database connection pool exhaustion on payment-api",
            "confidence": 0.88,
        },
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv


@pytest.fixture
def test_insufficient_investigation(db_session: Session) -> Investigation:
    """Creates an investigation with insufficient evidence."""
    inv = Investigation(
        investigation_key="INV-TEST-LOWCONF",
        incident_key="INC-AMBIGUOUS-999",
        status="INSUFFICIENT_EVIDENCE",
        target_service="payment-api",
        environment="production",
        leading_hypothesis="Insufficient telemetry evidence",
        confidence=0.15,
        is_fallback=True,
        model_provider="deterministic_fallback",
        evidence_json=[],
        report_json={
            "status": "INSUFFICIENT_EVIDENCE",
            "uncertainty_assessment": "High uncertainty: insufficient telemetry to isolate root cause",
        },
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv


def test_repair_workflow_successful_validation(db_session: Session, test_investigation_record: Investigation):
    """
    Verify complete happy path:
    1. Loads investigation
    2. Validates evidence
    3. Locates code in fixture repo
    4. Proposes patch and computes SHA-256 hash
    5. Reviews patch (clean)
    6. Validates in isolated sandbox with pytest
    7. Transitions to AWAITING_APPROVAL with human approval requirement
    """
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "payment_service"
    git_provider = LocalGitProvider(root_dir=fixture_dir)
    runner = IsolatedTestRunner(timeout_seconds=15.0)

    service = RepairService()
    req = RepairRequest(
        investigation_key=test_investigation_record.investigation_key,
        repository_url="local",
        custom_test_command="pytest tests/test_payment_pool.py",
        auto_create_pr=True,
    )

    response = service.run_repair(
        db=db_session,
        req=req,
        git_provider=git_provider,
        test_runner=runner,
        llm_provider=None,  # triggers deterministic fallback logic
        user_identity={"organization": "vermithor"},
        repo_root=fixture_dir,
    )

    assert response.status == RepairStatus.AWAITING_APPROVAL
    assert response.requires_human_approval is True
    assert response.validation_status == ValidationStatus.VALIDATED
    assert response.patch_hash is not None
    assert len(response.patch_hash) == 64
    assert "DatabaseConfig" in response.proposed_patch or "max_pool_size" in response.proposed_patch
    assert response.pull_request_url is not None
    assert response.is_fallback is True


def test_repair_workflow_insufficient_evidence_halts(db_session: Session, test_insufficient_investigation: Investigation):
    """
    Verify that an investigation with insufficient confidence halts early with INSUFFICIENT_EVIDENCE
    and DOES NOT generate speculative patches.
    """
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "payment_service"
    git_provider = LocalGitProvider(root_dir=fixture_dir)

    service = RepairService()
    req = RepairRequest(
        investigation_key=test_insufficient_investigation.investigation_key,
        repository_url="local",
    )

    response = service.run_repair(
        db=db_session,
        req=req,
        git_provider=git_provider,
    )

    assert response.status == RepairStatus.INSUFFICIENT_EVIDENCE
    assert response.proposed_patch is None
    assert response.patch_hash is None
    assert "inconclusive" in (response.error_message or "").lower()


def test_repair_workflow_unauthorized_repository_halts(db_session: Session, test_investigation_record: Investigation):
    """
    Verify that an unauthorized tenant organization is blocked from inspecting the repository.
    """
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "payment_service"
    git_provider = LocalGitProvider(root_dir=fixture_dir, allowed_orgs=["vermithor-core"])

    service = RepairService()
    req = RepairRequest(
        investigation_key=test_investigation_record.investigation_key,
        repository_url="local",
    )

    response = service.run_repair(
        db=db_session,
        req=req,
        git_provider=git_provider,
        user_identity={"organization": "unauthorized-external-org"},
    )

    assert response.status == RepairStatus.UNAUTHORIZED
    assert response.proposed_patch is None
    assert "access denied" in (response.error_message or "").lower()


def test_repair_workflow_handles_llm_failure_with_fallback(db_session: Session, test_investigation_record: Investigation):
    """
    Verify that when the LLM provider times out or fails, deterministic fallback produces
    the repair and marks is_fallback: True.
    """
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "payment_service"
    git_provider = LocalGitProvider(root_dir=fixture_dir)
    failing_llm = FakeFailingLLM()

    service = RepairService()
    req = RepairRequest(
        investigation_key=test_investigation_record.investigation_key,
        repository_url="local",
        custom_test_command="pytest tests/test_payment_pool.py",
    )

    response = service.run_repair(
        db=db_session,
        req=req,
        git_provider=git_provider,
        llm_provider=failing_llm,
        repo_root=fixture_dir,
    )

    assert response.is_fallback is True
    assert response.status == RepairStatus.AWAITING_APPROVAL
    assert response.validation_status == ValidationStatus.VALIDATED
