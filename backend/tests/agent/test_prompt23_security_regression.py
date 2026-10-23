"""
Prompt 23 Security Regression Proof and Production Readiness Test Suite.

Exhaustively verifies:
1. Organization claim validation: missing, empty, malformed, unauthorized.
2. Tenant isolation across investigation, feedback, repair, and deletion endpoints.
3. Information leakage prevention: 404 responses that do not reveal resource existence or owning tenant.
4. Fail-closed handling for unowned records (org_id=None or empty string).
5. Asynchronous worker-side authorization: task payload spoofing prevention and double-checking DB ownership.
6. Celery retry and duplicate task delivery idempotency.
7. Explicit administrative access rather than implicit defaults.
8. Tenant-scoped cascading data purge isolation.
9. Evidence citation semantic integrity (rejection of nonexistent, contradictory, irrelevant, stale, fabricated, cross-incident, cross-tenant).
10. Explicit reporting of the four citation integrity metrics.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.agent.db.models import (
    Investigation,
    InvestigationFeedback,
    Repair,
)
from backend.app.agent.schemas.investigation import InvestigationStatus
from backend.app.agent.schemas.repair import (
    ApprovalRequest,
    ApprovalStatus,
    RepairRequest,
    RepairStatus,
    ValidationStatus,
)
from backend.app.agent.services.citation_validator import (
    CitationClassification,
    EvidenceCitationValidator,
)
from backend.app.agent.services.pilot_service import PilotService
from backend.app.agent.services.repair_service import RepairService
from backend.app.common.security import create_access_token
from backend.app.main import app
from backend.workers.tasks import investigate_incident_task, repair_code_task


# ============================================================================
# 1. Organization Claim Validation & Rejection of Missing/Malformed Tokens
# ============================================================================

def test_regression_org_claim_validation(client: TestClient):
    """Missing, empty, whitespace, malformed, or unauthorized org claims must be rejected with 403."""
    # Missing org claim
    token_missing = create_access_token({"sub": "attacker-01"})
    res1 = client.get("/api/v1/agent/investigations", headers={"Authorization": f"Bearer {token_missing}"})
    assert res1.status_code == 403
    assert "missing" in res1.json()["detail"].lower()

    # Empty org claim
    token_empty = create_access_token({"sub": "attacker-02", "org_id": ""})
    res2 = client.get("/api/v1/agent/investigations", headers={"Authorization": f"Bearer {token_empty}"})
    assert res2.status_code == 403
    assert "missing" in res2.json()["detail"].lower()

    # Whitespace org claim
    token_ws = create_access_token({"sub": "attacker-03", "org_id": "   "})
    res3 = client.get("/api/v1/agent/investigations", headers={"Authorization": f"Bearer {token_ws}"})
    assert res3.status_code == 403

    # Malformed org claim (directory traversal / injection)
    token_malformed = create_access_token({"sub": "attacker-04", "org_id": "../admin"})
    res4 = client.get("/api/v1/agent/investigations", headers={"Authorization": f"Bearer {token_malformed}"})
    assert res4.status_code == 403
    assert "malformed" in res4.json()["detail"].lower()

    # Unauthorized external org claim
    token_unauth = create_access_token({"sub": "attacker-05", "org_id": "rogue-external-corp"})
    res5 = client.get("/api/v1/agent/investigations", headers={"Authorization": f"Bearer {token_unauth}"})
    assert res5.status_code == 403
    assert "not authorized" in res5.json()["detail"].lower()


# ============================================================================
# 2. Cross-Tenant Record Access & Information Leakage Prevention
# ============================================================================

def test_regression_cross_tenant_record_access_and_info_leakage(client: TestClient, db_session: Session):
    """
    Tenant B attempting to access Tenant A's investigation must receive 404 Not Found,
    without leaking existence or tenant metadata.
    """
    inv_a = Investigation(
        investigation_key="INV-TENANT-ALPHA-01",
        incident_key="INC-ALPHA-01",
        org_id="tenant_alpha",
        status=InvestigationStatus.COMPLETED.value,
        target_service="payment-gateway",
        environment="production",
        leading_hypothesis="Memory leak in worker pool",
        confidence=0.88,
    )
    db_session.add(inv_a)
    db_session.commit()

    token_b = create_access_token({"sub": "engineer_beta", "org_id": "tenant_beta", "role": "sre"})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Direct ID query must return 404 (not 403, which would confirm existence)
    res_get = client.get(f"/api/v1/agent/investigations/{inv_a.investigation_key}", headers=headers_b)
    assert res_get.status_code == 404
    assert "not found" in res_get.json()["detail"].lower()
    assert "tenant_alpha" not in res_get.text

    # Incident key query must return 404
    res_inc = client.get(f"/api/v1/agent/investigations/incident/{inv_a.incident_key}", headers=headers_b)
    assert res_inc.status_code == 404

    # List query must return empty list for Tenant B
    res_list = client.get("/api/v1/agent/investigations", headers=headers_b)
    assert res_list.status_code == 200
    items = res_list.json()["items"]
    assert not any(i["investigation_key"] == inv_a.investigation_key for i in items)


# ============================================================================
# 3. Cross-Tenant Feedback Isolation
# ============================================================================

def test_regression_cross_tenant_feedback_isolation(client: TestClient, db_session: Session):
    """
    Feedback submission or queries targeting another tenant's investigation
    must fail closed with 404 Not Found without creating or listing feedback.
    """
    inv_a = Investigation(
        investigation_key="INV-ALPHA-FEEDBACK",
        incident_key="INC-ALPHA-FB",
        org_id="tenant_alpha",
        status=InvestigationStatus.COMPLETED.value,
        target_service="auth-service",
        environment="production",
    )
    db_session.add(inv_a)
    db_session.commit()

    token_b = create_access_token({"sub": "user_beta", "org_id": "tenant_beta", "role": "sre"})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Attempt to submit feedback for Tenant A's investigation
    res_submit = client.post(
        f"/api/v1/agent/investigations/{inv_a.investigation_key}/feedback",
        json={"feedback_status": "CONFIRMED", "explanation": "Tampered feedback"},
        headers=headers_b,
    )
    assert res_submit.status_code == 404

    # Attempt to list feedback for Tenant A's investigation
    res_list = client.get(
        f"/api/v1/agent/investigations/{inv_a.investigation_key}/feedback",
        headers=headers_b,
    )
    assert res_list.status_code == 404

    # Confirm no feedback was written in database
    fb_count = db_session.query(InvestigationFeedback).filter_by(investigation_key=inv_a.investigation_key).count()
    assert fb_count == 0


# ============================================================================
# 4. Cross-Tenant Repair Approval, Rejection, and Execution
# ============================================================================

def test_regression_cross_tenant_repair_protection(client: TestClient, db_session: Session):
    """
    Tenant B cannot approve, reject, or trigger code repairs for Tenant A.
    Error responses must not disclose Tenant A's identifier.
    """
    rep_a = Repair(
        repair_key="REP-ALPHA-01",
        org_id="tenant_alpha",
        investigation_key="INV-ALPHA-REP",
        incident_key="INC-ALPHA-REP",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
        requires_human_approval=True,
        approval_status=ApprovalStatus.PENDING.value,
    )
    db_session.add(rep_a)
    db_session.commit()

    token_b = create_access_token({"sub": "engineer_beta", "org_id": "tenant_beta", "role": "sre_lead"})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Attempt to approve Tenant A's repair
    res_appr = client.post(
        f"/api/v1/agent/repairs/{rep_a.repair_key}/approve",
        json={"action": "APPROVE", "notes": "Unauthorized approval attempt"},
        headers=headers_b,
    )
    assert res_appr.status_code == 403
    assert "tenant_alpha" not in res_appr.text  # Must not leak victim tenant name

    # Attempt to reject Tenant A's repair
    res_rej = client.post(
        f"/api/v1/agent/repairs/{rep_a.repair_key}/approve",
        json={"action": "REJECT", "notes": "Unauthorized rejection attempt"},
        headers=headers_b,
    )
    assert res_rej.status_code == 403

    # Attempt to create repair for Tenant A's investigation
    inv_a = Investigation(
        investigation_key="INV-ALPHA-REP",
        incident_key="INC-ALPHA-REP",
        org_id="tenant_alpha",
        status=InvestigationStatus.COMPLETED.value,
    )
    db_session.add(inv_a)
    db_session.commit()

    res_run = client.post(
        "/api/v1/agent/repairs",
        json={
            "investigation_key": "INV-ALPHA-REP",
            "repository_url": "https://github.com/org/repo.git",
            "target_branch": "main",
        },
        headers=headers_b,
    )
    assert res_run.status_code == 403


# ============================================================================
# 5. Fail-Closed Handling for Records with Missing Tenant Ownership (org_id=None)
# ============================================================================

def test_regression_unowned_records_fail_closed(client: TestClient, db_session: Session):
    """
    Records with org_id=None or empty string must not silently grant access.
    Non-admin tenants are denied access, while only explicit system admin can triage.
    """
    # Create unowned investigation (legacy record without org_id)
    inv_unowned = Investigation(
        investigation_key="INV-LEGACY-UNOWNED-01",
        incident_key="INC-LEGACY-01",
        org_id="",
        status=InvestigationStatus.COMPLETED.value,
        target_service="legacy-service",
    )
    db_session.add(inv_unowned)

    # Create unowned repair
    rep_unowned = Repair(
        repair_key="REP-LEGACY-UNOWNED-01",
        org_id="",
        investigation_key="INV-LEGACY-UNOWNED-01",
        incident_key="INC-LEGACY-01",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
        requires_human_approval=True,
        approval_status=ApprovalStatus.PENDING.value,
    )
    db_session.add(rep_unowned)
    db_session.commit()

    token_tenant = create_access_token({"sub": "tenant_user", "org_id": "tenant_alpha", "role": "sre_lead"})
    headers_tenant = {"Authorization": f"Bearer {token_tenant}"}

    # Regular tenant must NOT be able to approve unowned repair
    res_appr = client.post(
        f"/api/v1/agent/repairs/{rep_unowned.repair_key}/approve",
        json={"action": "APPROVE", "notes": "Attempt to claim unowned repair"},
        headers=headers_tenant,
    )
    assert res_appr.status_code == 403
    assert "lacks tenant ownership" in res_appr.json()["detail"].lower() or "belongs to another organization" in res_appr.json()["detail"].lower()

    # Regular tenant must NOT be able to run repair against unowned investigation
    res_run = client.post(
        "/api/v1/agent/repairs",
        json={
            "investigation_key": "INV-LEGACY-UNOWNED-01",
            "repository_url": "https://github.com/org/legacy.git",
        },
        headers=headers_tenant,
    )
    assert res_run.status_code == 403
    assert "lacks tenant ownership" in res_run.json()["detail"].lower() or "belongs to another organization" in res_run.json()["detail"].lower()

    # Explicit administrative tenant ('vermithor') CAN triage unowned legacy records
    token_admin = create_access_token({"sub": "admin_user", "org_id": "vermithor", "role": "admin"})
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    res_admin_appr = client.post(
        f"/api/v1/agent/repairs/{rep_unowned.repair_key}/approve",
        json={"action": "APPROVE", "notes": "Authorized administrative triage of legacy repair"},
        headers=headers_admin,
    )
    assert res_admin_appr.status_code == 200
    assert res_admin_appr.json()["approval_status"] == "APPROVED"


# ============================================================================
# 6. Worker-Side Authorization & Task Payload Spoofing Prevention
# ============================================================================

def test_regression_worker_task_payload_validation_and_idempotency(db_session: Session):
    """
    Background Celery tasks must:
    1. Reject task payloads missing required org_id.
    2. Double-check tenant authorization against database records (preventing payload spoofing).
    3. Handle duplicate delivery idempotently without repeated mutation.
    """
    inv = Investigation(
        investigation_key="INV-WORKER-TEST-01",
        incident_key="INC-WORKER-01",
        org_id="tenant_alpha",
        status=InvestigationStatus.COMPLETED.value,
    )
    db_session.add(inv)
    db_session.commit()

    # 1. Missing org_id in repair task payload
    res_missing = repair_code_task({"investigation_key": "INV-WORKER-TEST-01"})
    assert res_missing["status"] == "unauthorized"
    assert "missing" in res_missing["error"].lower()

    # 2. Spoofed org_id (payload claims 'tenant_beta', but DB record belongs to 'tenant_alpha')
    res_spoof = repair_code_task({
        "investigation_key": "INV-WORKER-TEST-01",
        "org_id": "tenant_beta",
        "repository_url": "https://github.com/org/repo.git",
    })
    assert res_spoof["status"] == "unauthorized"
    assert "mismatch" in res_spoof["error"].lower()

    # 3. Missing org_id in investigate task payload
    res_inv_missing = investigate_incident_task({"incident_key": "INC-WORKER-01"})
    assert res_inv_missing["status"] == "unauthorized"

    # 4. Idempotent duplicate task delivery handling
    rep = Repair(
        repair_key="REP-WORKER-DUP-01",
        org_id="tenant_alpha",
        investigation_key="INV-WORKER-TEST-01",
        incident_key="INC-WORKER-01",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
        requires_human_approval=True,
        approval_status=ApprovalStatus.PENDING.value,
    )
    db_session.add(rep)
    db_session.commit()

    res_dup = repair_code_task({
        "investigation_key": "INV-WORKER-TEST-01",
        "org_id": "tenant_alpha",
        "repository_url": "https://github.com/org/repo.git",
    })
    assert res_dup["status"] == "success"
    assert res_dup.get("is_duplicate_delivery") is True
    assert res_dup["repair_key"] == rep.repair_key


# ============================================================================
# 7. Tenant-Scoped Cascading Data Purge Isolation
# ============================================================================

def test_regression_tenant_scoped_purge_isolation(client: TestClient, db_session: Session):
    """
    Data purge executed by Tenant Alpha must strictly delete Tenant Alpha's data,
    leaving Tenant Beta's investigations, feedback, and repairs completely untouched.
    """
    # Seed Tenant Alpha data
    inv_a = Investigation(
        investigation_key="INV-PURGE-ALPHA",
        incident_key="INC-PURGE-ALPHA",
        org_id="org_alpha",
        status=InvestigationStatus.COMPLETED.value,
    )
    fb_a = InvestigationFeedback(
        investigation_key="INV-PURGE-ALPHA",
        incident_key="INC-PURGE-ALPHA",
        org_id="org_alpha",
        feedback_status="CONFIRMED",
        operator_id="operator_a",
    )
    rep_a = Repair(
        repair_key="REP-PURGE-ALPHA",
        org_id="org_alpha",
        investigation_key="INV-PURGE-ALPHA",
        incident_key="INC-PURGE-ALPHA",
        status=RepairStatus.PENDING.value,
    )
    db_session.add_all([inv_a, fb_a, rep_a])

    # Seed Tenant Beta data
    inv_b = Investigation(
        investigation_key="INV-PURGE-BETA",
        incident_key="INC-PURGE-BETA",
        org_id="org_beta",
        status=InvestigationStatus.COMPLETED.value,
    )
    fb_b = InvestigationFeedback(
        investigation_key="INV-PURGE-BETA",
        incident_key="INC-PURGE-BETA",
        org_id="org_beta",
        feedback_status="CONFIRMED",
        operator_id="operator_b",
    )
    rep_b = Repair(
        repair_key="REP-PURGE-BETA",
        org_id="org_beta",
        investigation_key="INV-PURGE-BETA",
        incident_key="INC-PURGE-BETA",
        status=RepairStatus.PENDING.value,
    )
    db_session.add_all([inv_b, fb_b, rep_b])
    db_session.commit()

    # Tenant Alpha executes purge
    token_admin_a = create_access_token({"sub": "admin_a", "org_id": "org_alpha", "role": "admin"})
    res_purge = client.post(
        "/api/v1/agent/pilot/governance/purge",
        json={"confirm_organization_id": "org_alpha", "purge_all_pilot_data": True},
        headers={"Authorization": f"Bearer {token_admin_a}"},
    )
    assert res_purge.status_code == 200

    # Tenant Alpha records are deleted
    assert db_session.query(Investigation).filter_by(org_id="org_alpha").count() == 0
    assert db_session.query(InvestigationFeedback).filter_by(org_id="org_alpha").count() == 0
    assert db_session.query(Repair).filter_by(org_id="org_alpha").count() == 0

    # Tenant Beta records remain 100% intact
    assert db_session.query(Investigation).filter_by(org_id="org_beta").count() == 1
    assert db_session.query(InvestigationFeedback).filter_by(org_id="org_beta").count() == 1
    assert db_session.query(Repair).filter_by(org_id="org_beta").count() == 1


# ============================================================================
# 8. Evidence Citation Rejection Matrix
# ============================================================================

def test_regression_citation_rejection_matrix():
    """
    Verify rejection across all defective citation types:
    - Nonexistent telemetry
    - Wrong incident
    - Wrong tenant
    - Stale evidence
    - Historical postmortem misrepresented as current telemetry
    - Fabricated trace/prom prefix
    - Contradictory evidence
    - Valid identifier but irrelevant evidence
    """
    known_telemetry = {"prom-payment-service-cpu_usage", "trace-auth-0001"}
    known_events = {"evt-INC-100-0001"}

    # 1. Nonexistent telemetry
    st1, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-01",
        source_type="PROMETHEUS",
        source_id="prom-payment-service-nonexistent_metric",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
    )
    assert st1 == CitationClassification.MISSING_OR_UNRESOLVED

    # 2. Wrong tenant
    st2, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-02",
        source_type="PROMETHEUS",
        source_id="prom-payment-service-cpu_usage",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
        data={"org_id": "external_other_tenant"},
    )
    assert st2 == CitationClassification.CROSS_TENANT

    # 3. Wrong incident
    st3, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-03",
        source_type="PROMETHEUS",
        source_id="prom-payment-service-cpu_usage",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
        data={"incident_key": "INC-OTHER-999"},
    )
    assert st3 == CitationClassification.CROSS_INCIDENT

    # 4. Stale evidence
    st4, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-04",
        source_type="PROMETHEUS",
        source_id="prom-payment-service-cpu_usage",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
        data={"is_stale": True},
    )
    assert st4 == CitationClassification.STALE

    # 5. Historical postmortem cited as direct telemetry
    st5, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-05",
        source_type="PROMETHEUS",
        source_id="INC-2024-PREVIOUS-POSTMORTEM",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids={"INC-2024-PREVIOUS-POSTMORTEM"},
        known_event_ids=set(),
    )
    assert st5 == CitationClassification.CROSS_INCIDENT

    # 6. Fabricated trace prefix
    st6, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-06",
        source_type="JAEGER",
        source_id="trace-fabricated-fake-9999",
        service="auth-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
    )
    assert st6 == CitationClassification.MISSING_OR_UNRESOLVED

    # 7. Contradictory evidence
    st7, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-07",
        source_type="PROMETHEUS",
        source_id="prom-payment-service-cpu_usage",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
        data={"is_contradictory": True},
    )
    assert st7 == CitationClassification.MISSING_OR_UNRESOLVED

    # 8. Valid identifier but irrelevant evidence
    st8, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-08",
        source_type="PROMETHEUS",
        source_id="prom-payment-service-cpu_usage",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
        data={"is_irrelevant": True},
    )
    assert st8 == CitationClassification.MISSING_OR_UNRESOLVED


# ============================================================================
# 9. Citation Audit Four Distinct Metrics Computation
# ============================================================================

def test_regression_citation_four_metrics():
    """
    Verify calculation of the four explicit citation integrity metrics:
    1. Identifier resolution rate.
    2. Correct incident and tenant association rate.
    3. Evidence-to-claim support rate.
    4. Historical-versus-current classification accuracy.
    """
    raw_telemetry = {
        "service": "payment-service",
        "metrics": [{"metric_name": "cpu_usage", "service": "payment-service"}],
        "logs": [{"trace_id": "trace-payment-0001"}],
        "traces": [{"trace_id": "trace-payment-0001"}],
    }

    evidence_items = [
        # Valid grounded citation
        {
            "evidence_id": "EV-01",
            "source_type": "PROMETHEUS",
            "source_id": "prom-payment-service-cpu_usage",
            "service": "payment-service",
            "claim": "High CPU utilization detected",
        },
        # Historical RAG analogy (correctly classified as CROSS_INCIDENT)
        {
            "evidence_id": "EV-02",
            "source_type": "HISTORICAL_INCIDENT",
            "source_id": "INC-2024-001",
            "service": "payment-service",
            "claim": "Prior deadlock match",
        },
        # Nonexistent telemetry (unresolved)
        {
            "evidence_id": "EV-03",
            "source_type": "PROMETHEUS",
            "source_id": "prom-nonexistent",
            "service": "payment-service",
            "claim": "Phantom anomaly",
        },
        # Cross-tenant citation
        {
            "evidence_id": "EV-04",
            "source_type": "PROMETHEUS",
            "source_id": "prom-payment-service-cpu_usage",
            "service": "payment-service",
            "data": {"org_id": "other_tenant"},
            "claim": "Cross tenant signal",
        },
    ]

    hypotheses = [
        {"hypothesis_id": "H1", "supporting_evidence_ids": ["EV-01", "EV-02"]}
    ]

    audit = EvidenceCitationValidator.audit_investigation(
        evidence_items=evidence_items,
        hypotheses=hypotheses,
        tenant_id="tenant_alpha",
        incident_key="INC-TEST-01",
        raw_telemetry=raw_telemetry,
    )

    # 1. Identifier resolution rate: EV-01 and EV-02 resolved = 2 / 4 = 0.50
    assert "identifier_resolution_rate" in audit
    assert audit["identifier_resolution_rate"] == 0.50

    # 2. Correct incident and tenant association rate: EV-01 and EV-03 not cross-tenant/cross-incident = 2 / 4 = 0.50
    assert "correct_incident_and_tenant_association_rate" in audit
    assert audit["correct_incident_and_tenant_association_rate"] == 0.50

    # 3. Evidence-to-claim support rate: EV-01 valid = 1 / 4 = 0.25
    assert "evidence_to_claim_support_rate" in audit
    assert audit["evidence_to_claim_support_rate"] == 0.25

    # 4. Historical-versus-current classification accuracy
    assert "historical_versus_current_classification_accuracy" in audit
    assert audit["historical_versus_current_classification_accuracy"] == 1.0
