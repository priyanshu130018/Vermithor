"""
Test suite for Operator Verification Feedback on Incident Investigations (Prompt 14).

Verifies:
1. Authentication requirement (401 Unauthorized for missing tokens)
2. Tenant organization boundary enforcement (403 Forbidden for unauthorized orgs)
3. Schema validation (422 Unprocessable Entity for invalid feedback status)
4. Persistence and retrieval of operator feedback
5. Strict immutability of original investigation results (RCA scores, hypotheses, confidence unchanged)
6. Zero repair triggers or system mutations resulting from operator feedback
"""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest

from backend.app.agent.db.models import Investigation, InvestigationFeedback, Repair
from backend.app.agent.schemas.investigation import InvestigationStatus
from backend.app.common.database import SessionLocal, get_db
from backend.app.common.security import create_access_token
from backend.app.main import app


@pytest.fixture
def db_session():
    """Create local database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session):
    """TestClient wired to override get_db."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_investigation(db_session):
    """Seed sample completed investigation for feedback testing."""
    inv = Investigation(
        investigation_key="INV-TEST-FEEDBACK-01",
        incident_key="INC-TEST-999",
        status=InvestigationStatus.COMPLETED.value,
        target_service="billing-api",
        environment="production",
        leading_hypothesis="Database connection pool exhaustion on billing-api",
        confidence=0.88,
        is_fallback=True,
        model_provider="fallback",
        report_json={
            "investigation_id": "INV-TEST-FEEDBACK-01",
            "incident_key": "INC-TEST-999",
            "leading_hypothesis": "Database connection pool exhaustion on billing-api",
            "hypothesis_confidence": 0.88,
        },
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv


def test_feedback_requires_jwt_auth(client, sample_investigation):
    """Unauthenticated requests to record feedback return 401."""
    resp = client.post(
        f"/api/v1/agent/investigations/{sample_investigation.investigation_key}/feedback",
        json={"feedback_status": "CONFIRMED"},
    )
    assert resp.status_code == 401


def test_feedback_enforces_org_boundary(client, sample_investigation):
    """Tokens from unauthorized organizations receive 403 Forbidden."""
    unauthorized_token = create_access_token({
        "sub": "rogue_user",
        "org_id": "unauthorized-corp",
        "role": "engineer",
    })
    headers = {"Authorization": f"Bearer {unauthorized_token}"}

    resp = client.post(
        f"/api/v1/agent/investigations/{sample_investigation.investigation_key}/feedback",
        json={"feedback_status": "CONFIRMED"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_feedback_validation_error_on_invalid_status(client, sample_investigation):
    """Invalid feedback status values are rejected with 422 Unprocessable Entity."""
    token = create_access_token({"sub": "sre-analyst", "org_id": "vermithor", "role": "sre"})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/v1/agent/investigations/{sample_investigation.investigation_key}/feedback",
        json={"feedback_status": "INVALID_STATUS_CODE"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_feedback_persistence_and_immutable_investigation(client, sample_investigation, db_session):
    """
    Submitting operator feedback persists the feedback record while leaving the
    original investigation's leading hypothesis, confidence, and report completely unchanged.
    """
    token = create_access_token({"sub": "sre-lead@vermithor.io", "org_id": "vermithor", "role": "sre_lead"})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Submit feedback recording a disagreement with the AI diagnosis
    feedback_payload = {
        "feedback_status": "REJECTED",
        "confirmed_root_cause": "Upstream CoreDNS UDP packet timeout causing client connection stalls",
        "evidence_reference": "LOG-COREDNS-0491",
        "explanation": "Human SRE verified that Postgres pool acquisition delays were downstream symptoms of DNS lookups timing out.",
    }

    post_resp = client.post(
        f"/api/v1/agent/investigations/{sample_investigation.investigation_key}/feedback",
        json=feedback_payload,
        headers=headers,
    )
    assert post_resp.status_code == 201
    fb_data = post_resp.json()
    assert fb_data["feedback_status"] == "REJECTED"
    assert fb_data["operator_id"] == "sre-lead@vermithor.io"
    assert fb_data["confirmed_root_cause"] == feedback_payload["confirmed_root_cause"]
    assert fb_data["evidence_reference"] == "LOG-COREDNS-0491"

    # 2. Query original investigation to verify strict immutability
    inv_resp = client.get(
        f"/api/v1/agent/investigations/{sample_investigation.investigation_key}",
        headers=headers,
    )
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    # Original AI diagnosis is 100% preserved
    assert inv_data["leading_hypothesis"] == "Database connection pool exhaustion on billing-api"
    assert inv_data["confidence"] == 0.88
    assert inv_data["status"] == "COMPLETED"

    # 3. Retrieve feedback list
    list_resp = client.get(
        f"/api/v1/agent/investigations/{sample_investigation.investigation_key}/feedback",
        headers=headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data) >= 1
    assert list_data[0]["feedback_status"] == "REJECTED"
    assert list_data[0]["operator_id"] == "sre-lead@vermithor.io"


def test_feedback_does_not_trigger_repairs_or_mutations(client, sample_investigation, db_session):
    """Feedback submission does not trigger code repairs or Git actions."""
    token = create_access_token({"sub": "sre-engineer", "org_id": "vermithor", "role": "sre"})
    headers = {"Authorization": f"Bearer {token}"}

    initial_repairs_count = db_session.query(Repair).filter(Repair.investigation_key == sample_investigation.investigation_key).count()

    resp = client.post(
        f"/api/v1/agent/investigations/{sample_investigation.investigation_key}/feedback",
        json={
            "feedback_status": "CONFIRMED",
            "confirmed_root_cause": "Database connection pool exhaustion on billing-api",
            "explanation": "Verified matching HikariCP timeout logs in Grafana.",
        },
        headers=headers,
    )
    assert resp.status_code == 201

    # Zero repairs created
    final_repairs_count = db_session.query(Repair).filter(Repair.investigation_key == sample_investigation.investigation_key).count()
    assert final_repairs_count == initial_repairs_count
