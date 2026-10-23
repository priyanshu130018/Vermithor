"""
End-to-end integration and workflow verification test for Vermithor.

Verifies the complete 8-stage incident-to-repair user journey:
  Incident Registration
    -> Telemetry Evidence Collection
      -> AI Investigation (LangGraph)
        -> Root-Cause Analysis & Evidence Calibration
          -> Runbook Retrieval
            -> Repair Proposal (LangGraph)
              -> Isolated Sandbox Validation (4/4 tests pass)
                -> Mandatory Human Review & Approval Gate

Also verifies:
  - Database state persistence across sessions
  - Workflow idempotency (no duplicate repairs on repeat requests)
  - Security safeguards (tenant isolation, RBAC gating, stale patch rejection)
  - Strict prevention of autonomous code merge or deployment
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation, Repair
from backend.app.agent.git.local_provider import LocalGitProvider
from backend.app.agent.schemas.repair import ApprovalStatus, RepairStatus, ValidationStatus
from backend.app.common.security import create_access_token
from backend.app.incidents.db.models import Incident
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService
from backend.app.retrieval.db.models import Runbook
from backend.app.summary.llm.base import LLMProvider


FIXTURE_PAYMENT_REPO = Path(__file__).parent / "fixtures" / "payment_service"


class DeterministicTelemetryService(TelemetryEvidenceService):
    """Deterministic telemetry provider returning simulated Prometheus and Jaeger data."""

    def get_telemetry_snapshot(self, service: str, lookback_minutes: int = 15) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "service": service,
            "lookback_minutes": lookback_minutes,
            "collected_at": now.isoformat(),
            "sources": {
                "prometheus": {
                    "base_url": "http://prometheus:9090",
                    "metrics": {
                        "db_connection_pool_utilization_ratio": {"value": 1.0, "query": "db_pool_util"},
                        "api_request_latency_ms": {"value": 4800.0, "query": "latency"},
                        "http_5xx_error_rate_ratio": {"value": 0.28, "query": "5xx_rate"},
                    },
                },
                "jaeger": {
                    "base_url": "http://jaeger:16686",
                    "total_traces": 1,
                    "summaries": [
                        {
                            "trace_id": "9bf92f3577b34da6a3ce929d0e0e1042",
                            "root_service": service,
                            "root_operation": "POST /api/v1/payments/charge",
                            "start_time": now.isoformat(),
                            "duration_ms": 4800.0,
                            "span_count": 14,
                            "services_involved": [service, "postgres"],
                            "has_error": True,
                            "error_spans": [{"span_id": "sp-101", "error_message": "ConnectionAcquisitionTimeoutException"}],
                            "bottleneck_spans": [{"span_id": "sp-101", "duration_ms": 4800.0}],
                        }
                    ],
                },
            },
        }


class DeterministicInvestigationLLM(LLMProvider):
    """Deterministic LLM generating schema-compliant investigation evaluation."""

    def __init__(self):
        self.provider = "mock_deterministic"
        self.model = "mock-model"

    def generate(self, prompt: str) -> str:
        return """{
  "observed_facts": [
    "[EV-PROM-1] Database connection pool utilization reached 1.0 (100% capacity)",
    "[EV-PROM-2] API request latency spiked to 4800.0ms",
    "[EV-PROM-3] HTTP 5xx error rate reached 0.28 (28%)",
    "[EV-TRACE-1] Jaeger trace 9bf92f3577b34da6 captured ConnectionAcquisitionTimeoutException"
  ],
  "inferred_relationships": [
    "Deployment v2.8.4 preceded database connection acquisition timeouts",
    "HikariCP pool saturation on payment-api caused upstream latency cascade"
  ],
  "confirmed_findings": [
    "Database connection pool exhaustion on payment-api is confirmed as the primary operational failure"
  ],
  "hypotheses_evaluated": [
    {
      "hypothesis": "Database connection pool exhaustion on payment-api",
      "candidate_type": "DATABASE",
      "original_score": 0.94,
      "calibrated_status": "CONFIRMED",
      "supporting_evidence_ids": ["EV-PROM-1", "EV-TRACE-1"],
      "contradicting_evidence_ids": [],
      "reasoning": "Direct evidence of 100% pool utilization and ConnectionAcquisitionTimeoutException error spans"
    },
    {
      "hypothesis": "Recent deployment on payment-api",
      "candidate_type": "DEPLOYMENT",
      "original_score": 0.75,
      "calibrated_status": "PLAUSIBLE",
      "supporting_evidence_ids": ["EV-EVT-1"],
      "contradicting_evidence_ids": [],
      "reasoning": "Deployment v2.8.4 introduced persistent connection configuration immediately preceding the saturation"
    }
  ],
  "identified_uncertainties": [
    "Need confirmation whether pool sizing of 10 was intentional or an accidental regression in v2.8.4"
  ],
  "recommended_diagnostic_steps": [
    {
      "action": "Inspect payment-api pool sizing configuration in source code",
      "target_service": "payment-api",
      "rationale": "Verify whether pool size configuration matches traffic requirements",
      "priority": "HIGH",
      "requires_human_approval": true
    },
    {
      "action": "Review deployment git diff for v2.8.4 changes to database configuration",
      "target_service": "payment-api",
      "rationale": "Identify recent commits modifying connection pool limits",
      "priority": "HIGH",
      "requires_human_approval": true
    }
  ],
  "leading_hypothesis": "Database connection pool exhaustion on payment-api",
  "confidence": 0.94
}"""

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return self.provider

    def get_model_name(self) -> str:
        return self.model


@pytest.fixture
def seeded_incident_and_runbook(db_session: Session):
    """Seed synthetic incident INC-2026-1042 and matched runbook RB-000006."""
    from datetime import datetime, timezone
    from backend.app.incidents.schemas.incident import IncidentCreate, IncidentSeverity
    from backend.app.incidents.services.incident_service import IncidentService

    now = datetime.now(timezone.utc)
    inc_in = IncidentCreate(
        incident_key="INC-2026-1042",
        title="Payment API Database Connection Pool Exhaustion & Latency Spike",
        description="Deployment v2.8.4 followed by 100% database pool saturation and 28% HTTP 500 error cascade on payment-api.",
        severity=IncidentSeverity.SEV1,
        environment="production",
        started_at=now,
        confidence=0.94,
    )
    inc = IncidentService.create_incident(db_session, inc_in)

    rb = Runbook(
        runbook_key="RB-000006",
        title="Payment API Connection Pool Sizing and Leak Investigation",
        description="Troubleshoot database pool saturation and connection leaks on payment-api.",
        content="Inspect HikariCP connection pool settings and max_pool_size configuration in payment-api.",
        service="payment-api",
        environment="production",
        category="DATABASE",
    )
    db_session.add(rb)
    db_session.commit()
    db_session.refresh(inc)
    db_session.refresh(rb)
    return {"incident": inc, "runbook": rb}


def test_complete_incident_to_repair_e2e_journey(
    client: TestClient,
    db_session: Session,
    seeded_incident_and_runbook,
    monkeypatch,
):
    """
    Test the full 8-stage journey:
      1. Verify incident exists
      2. Trigger AI Investigation via LangGraph
      3. Assert investigation results (hypotheses, confidence, citations, runbooks)
      4. Trigger AI Code Repair via LangGraph
      5. Assert repair proposal (patch, isolated sandbox 4/4 passing tests, hash, PR branch)
      6. Verify workflow halts at mandatory human review gate (AWAITING_APPROVAL)
      7. Execute Human Review & SRE Approval
      8. Verify approval recorded and autonomous merge/deploy strictly prevented
    """
    telemetry_mock = DeterministicTelemetryService()
    monkeypatch.setattr(
        TelemetryEvidenceService,
        "get_telemetry_snapshot",
        telemetry_mock.get_telemetry_snapshot,
    )
    monkeypatch.setattr(
        "backend.app.summary.llm.factory.ProviderFactory.get_provider",
        lambda *args, **kwargs: DeterministicInvestigationLLM(),
    )
    monkeypatch.setattr(
        "backend.app.agent.git.factory.GitProviderFactory.get_provider",
        lambda *args, **kwargs: LocalGitProvider(root_dir=FIXTURE_PAYMENT_REPO),
    )

    incident_key = "INC-2026-1042"

    # --------------------------------------------------------------------------
    # STAGE 1: Verify Incident Exists
    # --------------------------------------------------------------------------
    inc_resp = client.get(f"/api/v1/incidents/{incident_key}")
    assert inc_resp.status_code == 200
    inc_data = inc_resp.json()
    assert inc_data["incident_key"] == incident_key
    assert inc_data["severity"] == "SEV1"
    assert "payment-api" in inc_data["description"]

    # --------------------------------------------------------------------------
    # STAGE 2 & 3: Trigger AI Investigation via LangGraph
    # --------------------------------------------------------------------------
    inv_payload = {
        "incident_key": incident_key,
        "lookback_minutes": 30,
        "allow_additional_queries": True,
        "max_additional_queries": 2,
        "force_refresh": True,
    }
    inv_resp = client.post("/api/v1/agent/investigations", json=inv_payload)
    assert inv_resp.status_code == 200, f"Investigation failed: {inv_resp.text}"
    inv_data = inv_resp.json()

    investigation_key = inv_data["investigation_key"]
    assert investigation_key.startswith("INV-")
    assert inv_data["status"] == "COMPLETED"
    assert inv_data["target_service"] == "payment-api"
    assert inv_data["confidence"] >= 0.50

    report = inv_data["report"]
    assert report is not None
    assert len(report["observed_facts"]) >= 3
    assert len(report["hypotheses_evaluated"]) >= 2
    assert "payment-api" in report["leading_hypothesis"].lower()
    assert len(report["evidence_items"]) >= 2
    assert len(report["recommended_diagnostic_steps"]) >= 1

    # Verify runbook RB-000006 was retrieved during the investigation
    runbook_keys = [rb["runbook_key"] for rb in report.get("runbook_references", [])]
    assert "RB-000006" in runbook_keys

    # --------------------------------------------------------------------------
    # STAGE 4: Trigger AI Code Repair via LangGraph
    # --------------------------------------------------------------------------
    repair_payload = {
        "investigation_key": investigation_key,
        "repository_url": "local",
        "branch": "main",
        "custom_test_command": "pytest tests/test_payment_pool.py",
        "force_refresh": True,
    }
    rep_resp = client.post("/api/v1/agent/repairs", json=repair_payload)
    assert rep_resp.status_code == 200, f"Repair failed: {rep_resp.text}"
    rep_data = rep_resp.json()

    repair_key = rep_data["repair_key"]
    assert repair_key.startswith("REP-")
    assert rep_data["investigation_key"] == investigation_key
    assert rep_data["incident_key"] == incident_key
    assert rep_data["validation_status"] == ValidationStatus.VALIDATED.value

    # Verify minimal patch targets max_pool_size
    proposed_patch = rep_data["proposed_patch"]
    assert proposed_patch is not None
    assert "-max_pool_size: int = 10" in proposed_patch
    assert "+max_pool_size: int = 50" in proposed_patch

    # Verify isolated sandbox validation results
    test_results = rep_data["test_results"]
    assert test_results is not None
    assert test_results["total_tests"] == 4
    assert test_results["passed"] == 4
    assert test_results["failed"] == 0

    # Verify patch hash generated and stored
    patch_hash = rep_data["patch_hash"]
    assert patch_hash is not None and len(patch_hash) == 64

    # Verify reviewable draft branch staged
    assert rep_data["repair_branch"] is not None
    assert rep_data["repair_branch"].startswith("repair/")

    # --------------------------------------------------------------------------
    # STAGE 5: Mandatory Human Review Gate
    # --------------------------------------------------------------------------
    assert rep_data["status"] == RepairStatus.AWAITING_APPROVAL.value
    assert rep_data["approval_status"] == ApprovalStatus.PENDING.value
    assert rep_data["requires_human_approval"] is True

    # --------------------------------------------------------------------------
    # STAGE 6: Safeguard Verification at the Review Gate
    # --------------------------------------------------------------------------

    # 6a. Stale Patch Rejection (Mismatched hash returns 409 Conflict)
    stale_payload = {
        "action": "APPROVE",
        "notes": "Approving outdated patch revision",
        "expected_patch_hash": "stale_or_tampered_hash_value_that_does_not_match_1234567890abcdef",
    }
    stale_resp = client.post(f"/api/v1/agent/repairs/{repair_key}/approve", json=stale_payload)
    assert stale_resp.status_code == 409
    assert "stale" in stale_resp.json()["detail"].lower()

    # 6b. Unauthorized Role Rejection (Read-only viewer cannot approve)
    viewer_token = create_access_token({
        "sub": "auditor_user",
        "role": "viewer",
        "org_id": "org_default",
    })
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    unauth_role_resp = client.post(
        f"/api/v1/agent/repairs/{repair_key}/approve",
        json={"action": "APPROVE", "notes": "Viewer trying to approve"},
        headers=viewer_headers,
    )
    assert unauth_role_resp.status_code == 403
    assert "not authorized" in unauth_role_resp.json()["detail"].lower()

    # 6c. Rejection Action Requires Notes (Empty notes returns 422)
    empty_notes_reject = {
        "action": "REJECT",
        "notes": "   ",
    }
    empty_reject_resp = client.post(f"/api/v1/agent/repairs/{repair_key}/approve", json=empty_notes_reject)
    assert empty_reject_resp.status_code == 422

    # --------------------------------------------------------------------------
    # STAGE 7: SRE Lead Explicit Human Approval
    # --------------------------------------------------------------------------
    sre_token = create_access_token({
        "sub": "sre_lead_alex",
        "role": "sre_lead",
        "org_id": "org_default",
    })
    sre_headers = {"Authorization": f"Bearer {sre_token}"}
    approval_payload = {
        "action": "APPROVE",
        "notes": "Isolated sandbox verified 4/4 tests pass. Verified max_pool_size=50 mitigates saturation.",
        "reviewer": "sre_lead_alex@vermithor.io",
        "expected_patch_hash": patch_hash,
    }
    approval_resp = client.post(
        f"/api/v1/agent/repairs/{repair_key}/approve",
        json=approval_payload,
        headers=sre_headers,
    )
    assert approval_resp.status_code == 200
    approved_data = approval_resp.json()
    assert approved_data["approval_status"] == ApprovalStatus.APPROVED.value
    assert approved_data["status"] == RepairStatus.APPROVED.value
    assert approved_data["approved_by"] == "sre_lead_alex@vermithor.io"
    assert approved_data["approved_at"] is not None

    # --------------------------------------------------------------------------
    # STAGE 8: Autonomous Merge & Deploy Safeguard
    # --------------------------------------------------------------------------
    # Confirm that neither merging nor deployment occurred autonomously
    # (The repair remains an approved patch artifact, strictly gated for human CI/CD rollout)
    get_rep_resp = client.get(f"/api/v1/agent/repairs/{repair_key}")
    assert get_rep_resp.status_code == 200
    final_rep = get_rep_resp.json()
    assert final_rep["status"] == RepairStatus.APPROVED.value
    assert final_rep["requires_human_approval"] is True


def test_state_persistence_and_idempotency_across_sessions(
    client: TestClient,
    db_session: Session,
    seeded_incident_and_runbook,
    monkeypatch,
):
    """
    Verify state persistence across separate DB sessions and idempotency of repeat requests.
    """
    telemetry_mock = DeterministicTelemetryService()
    monkeypatch.setattr(
        TelemetryEvidenceService,
        "get_telemetry_snapshot",
        telemetry_mock.get_telemetry_snapshot,
    )
    monkeypatch.setattr(
        "backend.app.summary.llm.factory.ProviderFactory.get_provider",
        lambda *args, **kwargs: DeterministicInvestigationLLM(),
    )
    monkeypatch.setattr(
        "backend.app.agent.git.factory.GitProviderFactory.get_provider",
        lambda *args, **kwargs: LocalGitProvider(root_dir=FIXTURE_PAYMENT_REPO),
    )

    incident_key = "INC-2026-1042"

    # Step 1: Run investigation
    inv_resp = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": incident_key, "force_refresh": True},
    )
    assert inv_resp.status_code == 200
    inv_key = inv_resp.json()["investigation_key"]

    # Step 2: Query DB directly in a new session to confirm persistence
    from backend.app.common.database import SessionLocal
    fresh_session = SessionLocal()
    try:
        persisted_inv = fresh_session.query(Investigation).filter(
            Investigation.investigation_key == inv_key
        ).first()
        assert persisted_inv is not None
        assert persisted_inv.status == "COMPLETED"
        assert persisted_inv.incident_key == incident_key
        assert persisted_inv.confidence >= 0.50
        assert persisted_inv.report_json is not None
        assert len(persisted_inv.report_json["observed_facts"]) >= 3
    finally:
        fresh_session.close()

    # Step 3: Run repair
    rep_resp = client.post(
        "/api/v1/agent/repairs",
        json={
            "investigation_key": inv_key,
            "repository_url": "local",
            "custom_test_command": "pytest tests/test_payment_pool.py",
            "force_refresh": True,
        },
    )
    assert rep_resp.status_code == 200
    rep_key = rep_resp.json()["repair_key"]

    # Step 4: Verify repair persistence in fresh session
    fresh_session = SessionLocal()
    try:
        persisted_rep = fresh_session.query(Repair).filter(
            Repair.repair_key == rep_key
        ).first()
        assert persisted_rep is not None
        assert persisted_rep.status == RepairStatus.AWAITING_APPROVAL.value
        assert persisted_rep.validation_status == ValidationStatus.VALIDATED.value
        assert persisted_rep.patch_hash is not None
        assert persisted_rep.test_results["passed"] == 4
    finally:
        fresh_session.close()

    # Step 5: Verify Idempotency - Repeat request with force_refresh=False returns same repair
    idempotent_resp = client.post(
        "/api/v1/agent/repairs",
        json={
            "investigation_key": inv_key,
            "repository_url": "local",
            "custom_test_command": "pytest tests/test_payment_pool.py",
            "force_refresh": False,
        },
    )
    assert idempotent_resp.status_code == 200
    assert idempotent_resp.json()["repair_key"] == rep_key


def test_tenant_isolation_boundary_enforced(
    client: TestClient,
    seeded_incident_and_runbook,
):
    """
    Verify that an untrusted tenant organization cannot access or trigger investigations or repairs.
    """
    unauthorized_token = create_access_token({
        "sub": "external_attacker",
        "role": "engineer",
        "org_id": "malicious_unauthorized_corp",
    })
    headers = {"Authorization": f"Bearer {unauthorized_token}"}

    # Investigation endpoints blocked
    resp = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-2026-1042"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()

    # Repair endpoints blocked
    resp = client.post(
        "/api/v1/agent/repairs",
        json={"investigation_key": "INV-MOCK-101"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()
