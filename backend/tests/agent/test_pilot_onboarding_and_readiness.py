import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.agent.db.models import (
    Investigation,
    InvestigationFeedback,
    PilotAuditLog,
    PilotGovernancePolicy,
    Repair,
    TelemetryIntegration,
)
from backend.app.agent.schemas.pilot import (
    IntegrationStatus,
    IntegrationType,
    OnboardingStep,
    TelemetryProvenance,
)
from backend.app.common.database import get_db
from backend.app.common.security import create_access_token
from backend.app.main import app
from backend.app.observability.security.safe_client import (
    SafeTelemetryHttpClient,
    mask_secret,
    redact_sensitive_text,
    validate_telemetry_endpoint,
)


@pytest.fixture
def auth_headers_admin_a():
    """Admin token for Org A."""
    token = create_access_token({
        "sub": "admin_user_a",
        "org_id": "org_alpha",
        "role": "admin",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_viewer_a():
    """Non-admin viewer token for Org A."""
    token = create_access_token({
        "sub": "viewer_user_a",
        "org_id": "org_alpha",
        "role": "viewer",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_admin_b():
    """Admin token for Org B (different tenant)."""
    token = create_access_token({
        "sub": "admin_user_b",
        "org_id": "org_beta",
        "role": "admin",
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_client(db_session: Session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ============================================================================
# 1. Authentication & Role-Based Authorization
# ============================================================================

def test_missing_or_invalid_credentials(test_client):
    """Missing, empty, or invalid bearer token must be rejected with HTTP 401."""
    # No auth header
    res = test_client.get("/api/v1/agent/pilot/readiness")
    assert res.status_code == 401

    # Malformed token
    res = test_client.get(
        "/api/v1/agent/pilot/readiness",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert res.status_code == 401


def test_unauthorized_administrators_rejected(test_client, auth_headers_viewer_a):
    """Non-admin role attempting administrative actions must receive HTTP 403."""
    # Attempting to configure integration
    cfg_payload = {
        "integration_type": "PROMETHEUS",
        "name": "Viewer Prometheus Attempt",
        "endpoint_url": "https://prometheus.internal:9090",
        "auth_type": "NONE",
    }
    res = test_client.post(
        "/api/v1/agent/pilot/integrations/configure",
        json=cfg_payload,
        headers=auth_headers_viewer_a,
    )
    assert res.status_code == 403
    assert "Administrator privileges required" in res.json()["detail"]

    # Attempting to purge data
    purge_payload = {
        "confirm_organization_id": "org_alpha",
        "purge_all_pilot_data": True,
    }
    res = test_client.post(
        "/api/v1/agent/pilot/governance/purge",
        json=purge_payload,
        headers=auth_headers_viewer_a,
    )
    assert res.status_code == 403


# ============================================================================
# 2. SSRF Protection, Dangerous Endpoints & Redirects
# ============================================================================

def test_unsafe_endpoints_and_ssrf_protection():
    """Endpoints targeting cloud metadata, loopback, non-HTTP schemes, or userinfo must be rejected."""
    # Cloud metadata IP (AWS/GCP/Azure)
    with pytest.raises(ValueError, match="SSRF violation"):
        validate_telemetry_endpoint("http://169.254.169.254/latest/meta-data")

    # Cloud metadata hostname
    with pytest.raises(ValueError, match="SSRF violation"):
        validate_telemetry_endpoint("http://metadata.google.internal/computeMetadata/v1")

    # Loopback address rejected in pilot mode
    with pytest.raises(ValueError, match="SSRF violation"):
        validate_telemetry_endpoint("http://127.0.0.1:9090", allow_localhost=False)

    # Disallowed protocols (e.g. file, ftp, gopher)
    with pytest.raises(ValueError, match="Prohibited protocol scheme"):
        validate_telemetry_endpoint("file:///etc/passwd")

    with pytest.raises(ValueError, match="Prohibited protocol scheme"):
        validate_telemetry_endpoint("ftp://telemetry.corp/data")

    # Userinfo in URL
    with pytest.raises(ValueError, match="Credentials in URL authority"):
        validate_telemetry_endpoint("https://admin:secret@metrics.example.com")


def test_safe_http_client_rejects_redirects():
    """SafeTelemetryHttpClient must reject HTTP redirects (301/302) to prevent redirect SSRF."""
    client = SafeTelemetryHttpClient()
    with patch("httpx.Client.request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.is_redirect = True
        mock_resp.status_code = 302
        mock_resp.headers = {"location": "http://169.254.169.254/latest/meta-data"}
        mock_req.return_value = mock_resp

        code, body = client.execute_query(
            method="GET",
            url="https://metrics.example.com/api/v1/query",
            allow_localhost=True,
        )
        assert code == 302
        assert body["status"] == "error"
        assert "Redirects from telemetry endpoints are strictly rejected" in body["error"]


def test_malformed_or_oversized_telemetry_responses():
    """SafeTelemetryHttpClient must enforce response body size limits (max 2 MB)."""
    client = SafeTelemetryHttpClient(max_response_bytes=1024)  # 1 KB limit for testing
    with patch("httpx.Client.request") as mock_req:
        mock_resp = MagicMock()
        mock_resp.is_redirect = False
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": "2048"}
        mock_req.return_value = mock_resp

        code, body = client.execute_query(
            method="GET",
            url="https://metrics.example.com/api/v1/query",
            allow_localhost=True,
        )
        assert code == 413
        assert "exceeds limit" in body["error"]


# ============================================================================
# 3. Secret Redaction & Masking
# ============================================================================

def test_secret_redaction_and_masking():
    """Secrets must be masked in persistence and redacted from error strings."""
    assert mask_secret("Bearer secret-token-12345") == "Bearer ***2345"
    assert mask_secret("supersecretkey999") == "***y999"
    assert mask_secret("short") == "******"

    text_with_secrets = "Error connecting with Authorization: Bearer eyJhbGciOi.eyJzdWI.secret and password='my_db_password'"
    redacted = redact_sensitive_text(text_with_secrets)
    assert "Bearer [REDACTED_TOKEN]" in redacted
    assert "password=[REDACTED]" in redacted
    assert "my_db_password" not in redacted


def test_configure_integration_masks_credentials(test_client, auth_headers_admin_a):
    """Configuring an integration with credentials must never store or return plaintext secrets."""
    payload = {
        "integration_type": "PROMETHEUS",
        "name": "Production Cluster Prometheus",
        "endpoint_url": "https://prometheus.internal:9090",
        "auth_type": "BEARER",
        "auth_credential": "Bearer secret-prom-token-998877",
        "allow_internal_hosts": True,
    }
    res = test_client.post(
        "/api/v1/agent/pilot/integrations/configure",
        json=payload,
        headers=auth_headers_admin_a,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["auth_credentials_masked"] == "Bearer ***8877"
    assert "secret-prom-token" not in json.dumps(data)
    assert data["status"] == IntegrationStatus.CONFIGURED_UNVERIFIED.value
    assert data["is_verified"] is False
    assert data["telemetry_provenance"] == TelemetryProvenance.NOT_VERIFIED.value


# ============================================================================
# 4. Multi-Tenant Isolation & Cross-Tenant Access Controls
# ============================================================================

def test_cross_tenant_access_blocked(test_client, auth_headers_admin_a, auth_headers_admin_b):
    """Tenant B must not be able to view, verify, disconnect, or purge Tenant A's resources."""
    # Tenant A configures an integration
    payload = {
        "integration_type": "PROMETHEUS",
        "name": "Org A Prometheus",
        "endpoint_url": "https://prometheus-a.internal:9090",
        "auth_type": "NONE",
        "allow_internal_hosts": True,
    }
    create_res = test_client.post(
        "/api/v1/agent/pilot/integrations/configure",
        json=payload,
        headers=auth_headers_admin_a,
    )
    assert create_res.status_code == 201
    int_id = create_res.json()["id"]

    # Tenant B tries to verify Tenant A's integration
    verify_res = test_client.post(
        f"/api/v1/agent/pilot/integrations/{int_id}/verify",
        headers=auth_headers_admin_b,
    )
    assert verify_res.status_code == 404

    # Tenant B tries to disconnect Tenant A's integration
    disc_res = test_client.post(
        f"/api/v1/agent/pilot/integrations/{int_id}/disconnect",
        headers=auth_headers_admin_b,
    )
    assert disc_res.status_code == 404

    # Tenant B lists integrations; Tenant A's integration must NOT appear
    list_res = test_client.get("/api/v1/agent/pilot/integrations", headers=auth_headers_admin_b)
    assert list_res.status_code == 200
    b_ids = [i["id"] for i in list_res.json()]
    assert int_id not in b_ids

    # Tenant B attempts to purge Tenant A's data
    purge_attempt = {
        "confirm_organization_id": "org_alpha",  # Tenant B specifying Org A
        "purge_all_pilot_data": True,
    }
    purge_res = test_client.post(
        "/api/v1/agent/pilot/governance/purge",
        json=purge_attempt,
        headers=auth_headers_admin_b,
    )
    assert purge_res.status_code == 400
    assert "does not match authenticated organization" in purge_res.json()["detail"]


# ============================================================================
# 5. Integration Verification & Truthful Provenance
# ============================================================================

def test_replay_mode_verification_and_provenance(test_client, auth_headers_admin_a):
    """Replay mode integration must explicitly report SANITIZED_REPLAY_FIXTURE and live NOT VERIFIED."""
    payload = {
        "integration_type": "REPLAY_MODE",
        "name": "Sanitized Incident Postmortem Replays",
        "auth_type": "NONE",
    }
    cfg_res = test_client.post(
        "/api/v1/agent/pilot/integrations/configure",
        json=payload,
        headers=auth_headers_admin_a,
    )
    assert cfg_res.status_code == 201
    int_id = cfg_res.json()["id"]

    verify_res = test_client.post(
        f"/api/v1/agent/pilot/integrations/{int_id}/verify",
        headers=auth_headers_admin_a,
    )
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["status"] == IntegrationStatus.VERIFIED.value
    assert v_data["is_verified"] is True
    assert v_data["telemetry_provenance"] == TelemetryProvenance.SANITIZED_REPLAY_FIXTURE.value
    assert "Live connectivity remains NOT VERIFIED" in v_data["message"]


def test_provider_timeouts_and_unavailable_endpoints(test_client, auth_headers_admin_a):
    """Unreachable telemetry endpoints must transition to DEGRADED and never mark VERIFIED."""
    payload = {
        "integration_type": "PROMETHEUS",
        "name": "Offline Prometheus",
        "endpoint_url": "https://unreachable-prom.internal:9090",
        "auth_type": "NONE",
        "allow_internal_hosts": True,
    }
    cfg_res = test_client.post(
        "/api/v1/agent/pilot/integrations/configure",
        json=payload,
        headers=auth_headers_admin_a,
    )
    int_id = cfg_res.json()["id"]

    # Verify endpoint: Safe client encounters timeout / unreachable host
    with patch("backend.app.observability.security.safe_client.SafeTelemetryHttpClient.execute_query") as mock_q:
        mock_q.return_value = (504, {"status": "timeout", "error": "Query read timed out"})

        verify_res = test_client.post(
            f"/api/v1/agent/pilot/integrations/{int_id}/verify",
            headers=auth_headers_admin_a,
        )
        assert verify_res.status_code == 200
        data = verify_res.json()
        assert data["status"] == IntegrationStatus.DEGRADED.value
        assert data["is_verified"] is False
        assert data["telemetry_provenance"] == TelemetryProvenance.NOT_VERIFIED.value
        assert "Query read timed out" in data["error"]


def test_revoked_or_disconnected_integration(test_client, auth_headers_admin_a):
    """Disconnecting an integration transitions it to REVOKED and prevents queries."""
    payload = {
        "integration_type": "PROMETHEUS",
        "name": "Active Prometheus",
        "endpoint_url": "https://prom.internal:9090",
        "auth_type": "NONE",
        "allow_internal_hosts": True,
    }
    cfg_res = test_client.post(
        "/api/v1/agent/pilot/integrations/configure",
        json=payload,
        headers=auth_headers_admin_a,
    )
    int_id = cfg_res.json()["id"]

    # Disconnect
    disc_res = test_client.post(
        f"/api/v1/agent/pilot/integrations/{int_id}/disconnect",
        headers=auth_headers_admin_a,
    )
    assert disc_res.status_code == 200
    assert disc_res.json()["status"] == IntegrationStatus.REVOKED.value

    # Subsequent verification attempts report REVOKED
    verify_res = test_client.post(
        f"/api/v1/agent/pilot/integrations/{int_id}/verify",
        headers=auth_headers_admin_a,
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == IntegrationStatus.REVOKED.value
    assert verify_res.json()["reachable"] is False


# ============================================================================
# 6. Guided Onboarding Workflow & Milestones
# ============================================================================

def test_guided_onboarding_step_progression(test_client, auth_headers_admin_a):
    """Admin can record progress through all 8 guided onboarding steps."""
    steps = [
        OnboardingStep.CONFIRM_IDENTITY,
        OnboardingStep.REVIEW_POLICY,
        OnboardingStep.SELECT_TELEMETRY,
        OnboardingStep.VALIDATE_CONFIG,
        OnboardingStep.CONNECTIVITY_CHECK,
        OnboardingStep.SAMPLE_INVESTIGATION,
        OnboardingStep.RECORD_FEEDBACK,
        OnboardingStep.VIEW_READINESS,
    ]

    for step in steps:
        req = {
            "step": step.value,
            "notes": f"Completed {step.value}",
            "acknowledged_read_only": True if step == OnboardingStep.REVIEW_POLICY else None,
        }
        res = test_client.post(
            "/api/v1/agent/pilot/onboarding/step",
            json=req,
            headers=auth_headers_admin_a,
        )
        assert res.status_code == 200
        data = res.json()
        assert step.value in data["completed_steps"]

    # After step 8, onboarding is completed
    status_res = test_client.get("/api/v1/agent/pilot/status", headers=auth_headers_admin_a)
    assert status_res.status_code == 200
    assert status_res.json()["onboarding_completed"] is True
    assert status_res.json()["acknowledged_read_only"] is True


# ============================================================================
# 7. Incident Data Governance, Kill Switch & Purge
# ============================================================================

def test_kill_switch_pauses_investigations_and_collection(test_client, auth_headers_admin_a):
    """Governance policy kill switches must immediately halt new collection and investigations."""
    # Update policy to pause investigations
    update_res = test_client.post(
        "/api/v1/agent/pilot/governance/policy",
        json={"investigations_paused": True, "collection_enabled": False},
        headers=auth_headers_admin_a,
    )
    assert update_res.status_code == 200
    assert update_res.json()["investigations_paused"] is True
    assert update_res.json()["collection_enabled"] is False

    # Attempting to trigger investigation must fail closed with HTTP 403
    inv_payload = {
        "incident_key": "INC-TEST-999",
        "lookback_minutes": 30,
    }
    inv_res = test_client.post(
        "/api/v1/agent/investigations",
        json=inv_payload,
        headers=auth_headers_admin_a,
    )
    assert inv_res.status_code == 403
    assert "Incident investigations are currently paused" in inv_res.json()["detail"]

    # Restore policy
    test_client.post(
        "/api/v1/agent/pilot/governance/policy",
        json={"investigations_paused": False, "collection_enabled": True},
        headers=auth_headers_admin_a,
    )


def test_organization_data_purge(test_client, auth_headers_admin_a, db_session: Session):
    """Purge must delete persisted investigations, feedback, and audit the deletion."""
    org_id = "org_alpha"

    # Seed feedback record
    fb = InvestigationFeedback(
        investigation_key="INV-PURGE-01",
        incident_key="INC-PURGE-01",
        org_id=org_id,
        feedback_status="CONFIRMED",
        operator_id="sre_purge@org.com",
    )
    db_session.add(fb)
    db_session.commit()

    # Verify seeded
    assert db_session.query(InvestigationFeedback).filter_by(org_id=org_id).count() >= 1

    # Execute purge
    purge_req = {
        "confirm_organization_id": org_id,
        "purge_all_pilot_data": True,
    }
    purge_res = test_client.post(
        "/api/v1/agent/pilot/governance/purge",
        json=purge_req,
        headers=auth_headers_admin_a,
    )
    assert purge_res.status_code == 200
    p_data = purge_res.json()
    assert p_data["deleted_feedback_count"] >= 1
    assert p_data["status"] == "SUCCESS"

    # Verify database records deleted
    assert db_session.query(InvestigationFeedback).filter_by(org_id=org_id).count() == 0

    # Audit log entry must exist
    audit_res = test_client.get("/api/v1/agent/pilot/audit-log", headers=auth_headers_admin_a)
    assert audit_res.status_code == 200
    actions = [a["action"] for a in audit_res.json()]
    assert "DATA_PURGED" in actions


# ============================================================================
# 8. Pilot Readiness Dashboard
# ============================================================================

def test_pilot_readiness_dashboard_verdict(test_client, auth_headers_admin_a):
    """Pilot readiness dashboard must report accurate blockers and honest status labels."""
    res = test_client.get("/api/v1/agent/pilot/readiness", headers=auth_headers_admin_a)
    assert res.status_code == 200
    data = res.json()
    assert data["org_id"] == "org_alpha"
    assert "blockers" in data
    assert "readiness_verdict" in data
    assert data["provenance_breakdown"]["live_production_incidents_count"] == 0
    assert data["provenance_breakdown"]["live_telemetry_verified"] is False
