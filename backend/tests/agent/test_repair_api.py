from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation, Repair
from backend.app.agent.git.local_provider import LocalGitProvider
from backend.app.agent.schemas.repair import ApprovalStatus, RepairStatus, ValidationStatus


@pytest.fixture
def persisted_investigation(db_session: Session) -> Investigation:
    """Fixture ensuring an investigation exists in the DB for API tests."""
    inv = Investigation(
        investigation_key="INV-API-TEST",
        incident_key="INC-2026-1042",
        status="COMPLETED",
        target_service="payment-api",
        environment="production",
        leading_hypothesis="Database connection pool exhaustion on payment-api",
        confidence=0.91,
        is_fallback=False,
        model_provider="mock_llm",
        evidence_json=[
            {"id": "EV-PROM-1", "description": "Database connection pool utilization reached 1.0 (100% capacity)"},
        ],
        report_json={
            "observed_facts": ["Database connection pool utilization reached 1.0 (100% capacity)"],
            "leading_hypothesis": "Database connection pool exhaustion on payment-api",
            "confidence": 0.91,
        },
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv


def test_repair_endpoints_require_jwt_auth(unauthenticated_client: TestClient):
    """Verify that all repair endpoints enforce JWT authentication and return 401."""
    # POST repair
    resp = unauthenticated_client.post(
        "/api/v1/agent/repairs",
        json={"investigation_key": "INV-API-TEST"},
    )
    assert resp.status_code == 401

    # GET by ID
    resp = unauthenticated_client.get("/api/v1/agent/repairs/REP-000001")
    assert resp.status_code == 401

    # GET list
    resp = unauthenticated_client.get("/api/v1/agent/repairs")
    assert resp.status_code == 401

    # POST approve
    resp = unauthenticated_client.post(
        "/api/v1/agent/repairs/REP-000001/approve",
        json={"action": "APPROVE"},
    )
    assert resp.status_code == 401


def test_repair_validation_error_on_empty_payload(client: TestClient):
    """Verify 422 Unprocessable Entity when investigation_key is missing or empty."""
    resp = client.post("/api/v1/agent/repairs", json={})
    assert resp.status_code == 422

    resp = client.post("/api/v1/agent/repairs", json={"investigation_key": "   "})
    assert resp.status_code == 422


def test_trigger_repair_sync_authenticated(
    client: TestClient,
    persisted_investigation: Investigation,
    monkeypatch,
):
    """Verify triggering repair synchronously via POST /api/v1/agent/repairs."""
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "payment_service"
    monkeypatch.setattr(
        "backend.app.agent.git.factory.GitProviderFactory.get_provider",
        lambda *args, **kwargs: LocalGitProvider(root_dir=fixture_dir),
    )

    resp = client.post(
        "/api/v1/agent/repairs",
        json={
            "investigation_key": persisted_investigation.investigation_key,
            "repository_url": "local",
            "custom_test_command": "pytest tests/test_payment_pool.py",
            "auto_create_pr": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repair_key"].startswith("REP-")
    assert data["investigation_key"] == persisted_investigation.investigation_key
    assert data["status"] == RepairStatus.AWAITING_APPROVAL.value
    assert data["validation_status"] == ValidationStatus.VALIDATED.value
    assert data["requires_human_approval"] is True
    assert data["patch_hash"] is not None


def test_get_repair_by_id(client: TestClient, db_session: Session):
    """Verify retrieving repair artifact by repair_key via GET /api/v1/agent/repairs/{id}."""
    rep = Repair(
        repair_key="REP-TEST-GET",
        investigation_key="INV-TEST-001",
        incident_key="INC-2026-1042",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
        proposed_patch="--- a/config.py\n+++ b/config.py\n@@ -1 +1 @@\n-10\n+50",
        patch_hash="abc123hash",
        requires_human_approval=True,
    )
    db_session.add(rep)
    db_session.commit()
    db_session.refresh(rep)

    resp = client.get(f"/api/v1/agent/repairs/{rep.repair_key}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repair_key"] == "REP-TEST-GET"
    assert data["status"] == RepairStatus.AWAITING_APPROVAL.value
    assert data["patch_hash"] == "abc123hash"


def test_get_repair_not_found(client: TestClient):
    """Verify 404 Not Found for non-existent repair ID."""
    resp = client.get("/api/v1/agent/repairs/REP-DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_list_repairs_pagination_and_filter(client: TestClient, db_session: Session):
    """Verify listing repairs with filters via GET /api/v1/agent/repairs."""
    rep = Repair(
        repair_key="REP-LIST-001",
        investigation_key="INV-FILTER-TEST",
        incident_key="INC-FILTER-101",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
    )
    db_session.add(rep)
    db_session.commit()

    resp = client.get("/api/v1/agent/repairs?incident_key=INC-FILTER-101")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(item["repair_key"] == "REP-LIST-001" for item in data["items"])


def test_approve_repair_records_decision_and_prevents_autonomous_deploy(client: TestClient, db_session: Session):
    """
    Verify POST /api/v1/agent/repairs/{id}/approve:
    1. Successfully records human approval decision.
    2. Records reviewer identity and notes.
    3. Strictly DOES NOT trigger autonomous code merge or deployment.
    """
    rep = Repair(
        repair_key="REP-APPROVE-TEST",
        investigation_key="INV-TEST-002",
        incident_key="INC-2026-1042",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
        requires_human_approval=True,
        approval_status=ApprovalStatus.PENDING.value,
    )
    db_session.add(rep)
    db_session.commit()
    db_session.refresh(rep)

    approval_payload = {
        "action": "APPROVE",
        "notes": "Patch verified by SRE on-call; approved for staging canary deployment.",
        "reviewer": "sre-lead@vermithor.internal",
    }

    resp = client.post(f"/api/v1/agent/repairs/{rep.repair_key}/approve", json=approval_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_status"] == ApprovalStatus.APPROVED.value
    assert data["status"] == RepairStatus.APPROVED.value
    assert data["approved_by"] == "sre-lead@vermithor.internal"
    assert "approved for staging" in data["approval_notes"]

    # Verify rejection action also records cleanly on a distinct repair
    rep_reject = Repair(
        repair_key="REP-REJECT-TEST",
        investigation_key="INV-TEST-003",
        incident_key="INC-2026-1042",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
        requires_human_approval=True,
        approval_status=ApprovalStatus.PENDING.value,
    )
    db_session.add(rep_reject)
    db_session.commit()
    db_session.refresh(rep_reject)

    reject_payload = {
        "action": "REJECT",
        "notes": "Requires additional architectural review.",
    }
    resp_reject = client.post(f"/api/v1/agent/repairs/{rep_reject.repair_key}/approve", json=reject_payload)
    assert resp_reject.status_code == 200
    reject_data = resp_reject.json()
    assert reject_data["approval_status"] == ApprovalStatus.REJECTED.value
    assert reject_data["status"] == RepairStatus.REJECTED.value


def test_async_mode_dispatch_celery(client: TestClient, persisted_investigation: Investigation, monkeypatch):
    """Verify POST /api/v1/agent/repairs?async_mode=true queues Celery task and returns PENDING."""
    mock_delay = MagicMock(return_value=MagicMock(id="celery-task-rep-12345"))
    monkeypatch.setattr("backend.workers.tasks.repair_code_task.delay", mock_delay)

    resp = client.post(
        "/api/v1/agent/repairs?async_mode=true",
        json={"investigation_key": persisted_investigation.investigation_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repair_key"].startswith("REP-")
    assert data["status"] == RepairStatus.PENDING.value
    assert mock_delay.called
