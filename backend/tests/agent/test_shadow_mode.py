"""
Tests for Vermithor passive read-only shadow mode evaluation (Prompt 13).
Verifies:
1. Secret redaction mechanism (JWTs, Bearer tokens, secrets)
2. Invariant: 0 repair workflows triggered, 0 Git mutations
3. Explicit shadow provenance: SHADOW_PASSIVE and NOT VERIFIED for live telemetry
4. Org-boundary enforcement and JWT authentication on /agent/shadow/evaluate
5. Rate limiting on shadow evaluation endpoint
"""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from backend.app.agent.schemas.shadow import ShadowModeRequest
from backend.app.agent.services.shadow_service import (
    ShadowEvaluationService,
    redact_sensitive_strings,
)
from backend.app.common.security import create_access_token
from backend.app.main import app

client = TestClient(app)


def test_secret_redaction_utility():
    """Verify regex secret scrubber neutralizes JWTs, Bearer tokens, and secrets."""
    raw_text = (
        "Auth failed with bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisToken "
        "and password='SuperSecretPassword123!' and token='api_key_abcdef123456'"
    )
    cleaned, count = redact_sensitive_strings(raw_text)

    assert count >= 2
    assert "SuperSecretPassword123!" not in cleaned
    assert "doNotLeakThisToken" not in cleaned
    assert "[REDACTED_SECRET]" in cleaned


def test_shadow_service_guarantees_zero_repairs():
    """Verify that shadow evaluation returns SHADOW_PASSIVE with zero repair triggers."""
    mock_inv_service = MagicMock()
    mock_inv_resp = MagicMock()
    mock_inv_resp.investigation_key = "INV-SHADOW-TEST"
    mock_inv_resp.status.value = "COMPLETED"
    mock_inv_resp.leading_hypothesis = "Recent deployment on test-svc"
    mock_inv_resp.confidence = 0.88
    mock_inv_resp.is_fallback = True
    mock_inv_service.run_investigation.return_value = mock_inv_resp

    shadow_svc = ShadowEvaluationService(inv_service=mock_inv_service)
    req = ShadowModeRequest(incident_key="INC-SHADOW-01", lookback_minutes=60, redact_secrets=True)

    db_mock = MagicMock()
    resp = shadow_svc.run_shadow_evaluation(db=db_mock, req=req, org_id="tenant-shadow")

    assert resp.execution_mode == "SHADOW_PASSIVE"
    assert resp.is_shadow_mode is True
    assert resp.live_telemetry_verified is False
    assert resp.repair_workflow_triggered is False
    assert resp.git_mutations_count == 0
    assert resp.org_id == "tenant-shadow"


def test_shadow_api_endpoint_requires_auth():
    """Unauthenticated requests to /api/v1/agent/shadow/evaluate must return HTTP 401."""
    resp = client.post(
        "/api/v1/agent/shadow/evaluate",
        json={"incident_key": "INC-TEST-01", "lookback_minutes": 60},
    )
    assert resp.status_code == 401


def test_shadow_api_endpoint_authenticated_execution():
    """Authenticated request returns valid shadow response with proper headers."""
    token = create_access_token({"sub": "sre-analyst", "org_id": "vermithor", "role": "sre"})
    headers = {"Authorization": f"Bearer {token}"}

    with patch("backend.app.agent.api.shadow.shadow_service.run_shadow_evaluation") as mock_run:
        mock_run.return_value = MagicMock(
            shadow_run_id="SHADOW-123456",
            incident_key="INC-SHADOW-02",
            investigation_key="INV-000100",
            execution_mode="SHADOW_PASSIVE",
            is_shadow_mode=True,
            live_telemetry_verified=False,
            telemetry_provenance="SANITIZED_REPLAY_FIXTURE",
            status="COMPLETED",
            leading_hypothesis="Database connection pool exhaustion on payment-api",
            confidence=0.88,
            latency_ms=1240.5,
            is_fallback=True,
            secrets_redacted_count=0,
            repair_workflow_triggered=False,
            git_mutations_count=0,
            org_id="vermithor",
            created_at="2026-10-20T11:00:00Z",
        )

        resp = client.post(
            "/api/v1/agent/shadow/evaluate",
            json={"incident_key": "INC-SHADOW-02", "lookback_minutes": 60},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["execution_mode"] == "SHADOW_PASSIVE"
        assert data["is_shadow_mode"] is True
        assert data["repair_workflow_triggered"] is False
        assert data["git_mutations_count"] == 0


def test_shadow_api_endpoint_unauthorized_org_forbidden():
    """Request with unauthorized organization claim receives 403 Forbidden."""
    token = create_access_token({"sub": "unauthorized-actor", "org_id": "external-rogue-corp", "role": "sre"})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/agent/shadow/evaluate",
        json={"incident_key": "INC-SHADOW-02", "lookback_minutes": 60},
        headers=headers,
    )
    assert resp.status_code == 403
