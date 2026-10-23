from typing import Any, Dict
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from backend.app.agent.schemas.investigation import InvestigationResponse, InvestigationStatus
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory


def test_agent_health_endpoint(client: TestClient):
    """Verify GET /api/v1/agent/health reports LangGraph version and orchestration status."""
    resp = client.get("/api/v1/agent/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["orchestration_engine"] == "langgraph"
    assert "langgraph_version" in data
    assert "telemetry_evidence_gathering" in data["capabilities"]


def test_investigation_endpoints_require_jwt_auth(unauthenticated_client: TestClient):
    """Verify that all investigation endpoints enforce JWT authentication and return 401."""
    # POST trigger
    resp = unauthenticated_client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-2026-1042"},
    )
    assert resp.status_code == 401

    # GET by ID
    resp = unauthenticated_client.get("/api/v1/agent/investigations/INV-000001")
    assert resp.status_code == 401

    # GET by incident key
    resp = unauthenticated_client.get("/api/v1/agent/investigations/incident/INC-2026-1042")
    assert resp.status_code == 401

    # GET list
    resp = unauthenticated_client.get("/api/v1/agent/investigations")
    assert resp.status_code == 401


def test_investigation_validation_error(client: TestClient):
    """Verify that invalid inputs return 422 Unprocessable Entity."""
    # Empty body
    resp = client.post("/api/v1/agent/investigations", json={})
    assert resp.status_code == 422

    # Empty string incident_key
    resp = client.post("/api/v1/agent/investigations", json={"incident_key": "   "})
    assert resp.status_code == 422


def test_trigger_investigation_authenticated_sync(
    client: TestClient,
    test_payment_incident,
    mock_telemetry_service,
    mock_valid_llm,
    monkeypatch,
):
    """
    Verify full authenticated POST /api/v1/agent/investigations execution:
    1. Returns 200 OK with valid InvestigationResponse schema.
    2. Preserves evidence citations, RCA candidate scores, and diagnostic steps.
    3. Persists result in DB and is retrievable via GET.
    """
    # Monkeypatch TelemetryEvidenceService and ProviderFactory to use deterministic mocks
    monkeypatch.setattr(
        TelemetryEvidenceService,
        "get_telemetry_snapshot",
        mock_telemetry_service.get_telemetry_snapshot,
    )
    monkeypatch.setattr(
        ProviderFactory,
        "get_provider",
        lambda cfg=None: mock_valid_llm,
    )

    resp = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-2026-1042", "force_refresh": True},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_key"] == "INC-2026-1042"
    assert data["status"] in ["COMPLETED", "INSUFFICIENT_EVIDENCE"]
    assert data["investigation_key"].startswith("INV-")
    assert data["confidence"] > 0.0

    rep = data["report"]
    assert rep is not None
    assert len(rep["observed_facts"]) > 0
    assert len(rep["hypotheses_evaluated"]) > 0
    assert len(rep["recommended_diagnostic_steps"]) > 0

    inv_key = data["investigation_key"]

    # 4. Retrieve by investigation key
    get_resp = client.get(f"/api/v1/agent/investigations/{inv_key}")
    assert get_resp.status_code == 200
    assert get_resp.json()["investigation_key"] == inv_key

    # 5. Retrieve by incident key
    inc_resp = client.get("/api/v1/agent/investigations/incident/INC-2026-1042")
    assert inc_resp.status_code == 200
    assert inc_resp.json()["investigation_key"] == inv_key

    # 6. List investigations
    list_resp = client.get("/api/v1/agent/investigations?incident_key=INC-2026-1042")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(item["investigation_key"] == inv_key for item in list_data["items"])


def test_investigation_idempotency(
    client: TestClient,
    test_payment_incident,
    mock_telemetry_service,
    mock_valid_llm,
    monkeypatch,
):
    """
    Verify idempotency: retrying investigation with force_refresh=False
    returns cached investigation and does not create duplicate runs.
    """
    monkeypatch.setattr(
        TelemetryEvidenceService,
        "get_telemetry_snapshot",
        mock_telemetry_service.get_telemetry_snapshot,
    )
    monkeypatch.setattr(
        ProviderFactory,
        "get_provider",
        lambda cfg=None: mock_valid_llm,
    )

    # First request
    resp1 = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-2026-1042", "force_refresh": True},
    )
    assert resp1.status_code == 200
    inv_key1 = resp1.json()["investigation_key"]

    # Second request with force_refresh=False
    resp2 = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-2026-1042", "force_refresh": False},
    )
    assert resp2.status_code == 200
    inv_key2 = resp2.json()["investigation_key"]

    # Must return identical cached investigation
    assert inv_key1 == inv_key2


def test_investigation_not_found(client: TestClient):
    """Verify 404 response for nonexistent investigation key."""
    resp = client.get("/api/v1/agent/investigations/INV-NONEXISTENT")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_investigation_endpoints_enforce_org_boundary(unauthenticated_client: TestClient):
    """
    Verify that tokens from unauthorized organizations receive 403 Forbidden
    when attempting to trigger or access investigations.
    """
    from backend.app.common.security import create_access_token

    unauthorized_token = create_access_token({
        "sub": "attacker_user",
        "role": "engineer",
        "org_id": "unauthorized_external_corp",
    })
    headers = {"Authorization": f"Bearer {unauthorized_token}"}

    # Trigger investigation
    resp = unauthenticated_client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-2026-1042"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()

    # Get by ID
    resp_get = unauthenticated_client.get(
        "/api/v1/agent/investigations/INV-000001",
        headers=headers,
    )
    assert resp_get.status_code == 403

    # List investigations
    resp_list = unauthenticated_client.get(
        "/api/v1/agent/investigations",
        headers=headers,
    )
    assert resp_list.status_code == 403

