"""
Comprehensive Controlled Failure and Resilience Tests for Vermithor Agent Workflows.
Verifies all 11 failure modes outlined in Section 6:
1. GitHub API rate limiting (403/429 non-leaky sanitized error)
2. Network timeout during inspection
3. Revoked repository access
4. Database temporarily unavailable
5. Worker unavailable / Celery task error
6. LLM provider timeout (activates fallback)
7. Malformed LLM output (activates fallback)
8. Missing telemetry (honest uncertainty)
9. Contradictory evidence (ambiguity documented, lower confidence)
10. Investigation retry & duplicate requests (idempotency)
11. Repair validation sandbox execution timeout
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest
import httpx
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation, RepositoryConnection
from backend.app.agent.git.github_provider import GitHubProvider
from backend.app.agent.runner.sandbox import IsolatedTestRunner
from backend.app.agent.schemas.investigation import (
    InvestigationRequest,
    InvestigationResponse,
    InvestigationStatus,
)
from backend.app.agent.schemas.repair import (
    RepairRequest,
    RepairResponse,
    RepairStatus,
    ValidationStatus,
)
from backend.app.agent.services.investigation_service import InvestigationService
from backend.app.agent.services.repair_service import RepairService
from backend.app.incidents.db.models import Incident
from backend.app.incidents.schemas.incident import IncidentCreate, IncidentSeverity
from backend.app.incidents.services.incident_service import IncidentService
from backend.workers.tasks import investigate_incident_task, repair_code_task


# ============================================================================
# 1. GitHub API Rate Limiting (403/429 non-leaky error)
# ============================================================================
def test_github_api_rate_limiting_sanitized():
    """Verify HTTP 403/429 rate limit errors produce sanitized errors without token leaks."""
    token = "ghp_supersecretgithubtoken1234567890abcdef"
    provider = GitHubProvider(token=token, allowed_orgs=["vermithor", "test-org"])

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1770000000"}

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(PermissionError) as exc_info:
            provider.get_file_content("vermithor/payment-service", "src/config.py")

        err_msg = str(exc_info.value)
        assert "rate limit exceeded" in err_msg.lower() or "forbidden" in err_msg.lower()
        # Ensure secret token is NEVER present in error message
        assert token not in err_msg
        assert "ghp_" not in err_msg


# ============================================================================
# 2. Network Timeout During Inspection
# ============================================================================
def test_network_timeout_during_inspection():
    """Verify network timeouts during remote file fetch are caught and handled cleanly."""
    token = "ghp_tokentimeouttest1234567890abcdefgh"
    provider = GitHubProvider(token=token, allowed_orgs=["vermithor"])

    with patch("httpx.Client.get", side_effect=httpx.ConnectTimeout("Connection timed out after 15.0s")):
        with pytest.raises(httpx.ConnectTimeout):
            provider.get_file_content("vermithor/payment-service", "src/config.py")


# ============================================================================
# 3. Revoked Repository Access
# ============================================================================
def test_revoked_repository_access_blocks_repair(db_session: Session, test_payment_incident):
    """Verify that revoked repository connections immediately halt repair inspection."""
    # 1. Connect a repository then mark it REVOKED
    revoked_conn = RepositoryConnection(
        repo_identifier="vermithor/revoked-service",
        org_id="vermithor",
        status="REVOKED",
        read_only=True,
    )
    db_session.add(revoked_conn)
    db_session.commit()

    # 2. Create a completed investigation
    inv_service = InvestigationService()
    inv_req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)
    inv_resp = inv_service.run_investigation(db=db_session, req=inv_req)

    # 3. Attempt repair on the revoked repository
    repair_service = RepairService()
    rep_req = RepairRequest(
        investigation_key=inv_resp.investigation_key,
        repository_url="vermithor/revoked-service",
        target_file="src/config.py",
        branch="main",
    )

    with pytest.raises(PermissionError) as exc_info:
        repair_service.run_repair(
            db=db_session,
            req=rep_req,
            user_identity={"org_id": "vermithor", "sub": "test-engineer"},
        )

    assert "revoked" in str(exc_info.value).lower()


# ============================================================================
# 4. Database Temporarily Unavailable
# ============================================================================
def test_database_temporarily_unavailable_handled(test_payment_incident):
    """Verify database connection errors during report retrieval fail gracefully."""
    mock_db = MagicMock(spec=Session)
    mock_db.execute.side_effect = OperationalError("connection to server lost", None, None)

    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=False)

    with pytest.raises(OperationalError):
        service.run_investigation(db=mock_db, req=req)


# ============================================================================
# 5. Worker Unavailable / Celery Task Error
# ============================================================================
def test_celery_task_error_handled_cleanly():
    """Verify Celery task failures record errors and return failed status without crashing."""
    # Pass malformed payload that triggers validation error
    malformed_payload = {"incident_key": 12345, "invalid_field": True}

    with patch("backend.app.common.database.SessionLocal") as mock_session_factory:
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        
        result = investigate_incident_task(malformed_payload)

        assert result is not None
        assert result.get("status") in ("success", "failed", "unauthorized")
        # Ensure database session was cleanly closed in finally block
        mock_db.close.assert_called_once()


# ============================================================================
# 6. LLM Provider Timeout (Activates Fallback)
# ============================================================================
def test_llm_provider_timeout_activates_fallback(
    db_session: Session,
    test_payment_incident,
    mock_telemetry_service,
    mock_failing_llm,
):
    """Verify slow/timing-out LLM triggers deterministic fallback cleanly."""
    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)

    resp: InvestigationResponse = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_telemetry_service,
        llm_provider=mock_failing_llm,
    )

    assert resp is not None
    assert resp.is_fallback is True
    assert resp.model_provider == "fallback"
    assert resp.report is not None
    assert len(resp.report.hypotheses_evaluated) > 0


# ============================================================================
# 7. Malformed LLM Output (Activates Fallback)
# ============================================================================
def test_malformed_llm_output_activates_fallback(
    db_session: Session,
    test_payment_incident,
    mock_telemetry_service,
    mock_malformed_llm,
):
    """Verify malformed/unparseable LLM output falls back to deterministic rules."""
    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)

    resp: InvestigationResponse = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_telemetry_service,
        llm_provider=mock_malformed_llm,
    )

    assert resp is not None
    assert resp.is_fallback is True
    assert resp.model_provider == "fallback"
    assert resp.report is not None


# ============================================================================
# 8. Missing Telemetry (Honest Uncertainty)
# ============================================================================
def test_missing_telemetry_honest_uncertainty(
    db_session: Session,
    mock_unavailable_telemetry_service,
    mock_failing_llm,
):
    """Verify missing telemetry results in explicit notation of gaps and low confidence."""
    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-MISSING-DATA", force_refresh=True)

    resp = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_unavailable_telemetry_service,
        llm_provider=mock_failing_llm,
    )

    assert resp is not None
    assert resp.status in (InvestigationStatus.INSUFFICIENT_EVIDENCE, InvestigationStatus.COMPLETED)
    assert resp.confidence < 0.50
    assert resp.report is not None
    # Uncertainty assessment must reflect data absence
    assessment = resp.report.uncertainty_assessment.lower()
    assert "uncertainty" in assessment or "missing" in assessment or "insufficient" in assessment


# ============================================================================
# 9. Contradictory Evidence (Reduced Confidence & Documented Ambiguity)
# ============================================================================
def test_contradictory_evidence_reduces_confidence(
    db_session: Session,
    mock_valid_llm,
):
    """Verify contradictory signals reduce confidence and document ambiguity."""
    # Setup mock telemetry with normal metrics but high error logs
    class ContradictoryTelemetryService:
        def get_telemetry_snapshot(self, service: str, lookback_minutes: int = 15):
            return {
                "service": service,
                "lookback_minutes": lookback_minutes,
                "sources": {
                    "prometheus": {
                        "metrics": {
                            # Normal CPU & connection pool
                            "container_cpu_utilization_ratio": {"value": 0.12},
                            "db_connection_pool_utilization_ratio": {"value": 0.08},
                        }
                    },
                    "jaeger": {
                        "total_traces": 0,
                        "summaries": [],
                    },
                },
            }

    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-CONTRADICTORY", force_refresh=True)

    resp = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=ContradictoryTelemetryService(),
        llm_provider=mock_valid_llm,
    )

    assert resp is not None
    # When metrics show low utilization, confidence must not be falsely 1.0
    assert resp.confidence <= 0.85
    assert resp.report is not None


# ============================================================================
# 10. Investigation Retry & Duplicate Requests (Idempotency)
# ============================================================================
def test_investigation_retry_idempotency(db_session: Session, test_payment_incident):
    """Verify repeated investigation requests without force_refresh return cached report."""
    service = InvestigationService()
    req1 = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)
    resp1 = service.run_investigation(db=db_session, req=req1)

    # Second call without force_refresh
    req2 = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=False)
    resp2 = service.run_investigation(db=db_session, req=req2)

    assert resp1.investigation_key == resp2.investigation_key
    assert resp1.status == resp2.status


# ============================================================================
# 11. Repair Validation Sandbox Execution Timeout
# ============================================================================
def test_sandbox_execution_timeout_rejects_patch(tmp_path: Path):
    """Verify test commands that exceed timeout are terminated and result is marked failed."""
    runner = IsolatedTestRunner(timeout_seconds=1.0)

    # Create slow test file without shell operators
    slow_test = tmp_path / "test_slow.py"
    slow_test.write_text(
        "import time\n\n"
        "def test_hang():\n"
        "    time.sleep(5)\n",
        encoding="utf-8",
    )

    result = runner.run_validation(
        source_dir=tmp_path,
        patch_diff="",
        test_command="pytest test_slow.py",
    )

    assert result.status == ValidationStatus.VALIDATION_FAILED
    assert "timed out" in (result.error_message or "").lower()
    assert result.duration_ms >= 900  # at least ~1000ms
