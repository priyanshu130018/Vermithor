from datetime import datetime, timezone
from fastapi.testclient import TestClient
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.correlation.db.models import CorrelationGroup, CorrelationSignal

_orig_client = httpx.Client


def test_evaluate_correlations_api(client: TestClient):
    """Test POST /api/v1/correlations/evaluate dry-run evaluation."""
    payload = {
        "signals": [
            {
                "signal_id": "evt-001",
                "signal_type": "EVENT",
                "timestamp": "2026-08-29T12:00:00Z",
                "service": "booking-api",
                "environment": "production",
                "severity": "ERROR",
                "source_reference": "evt-001",
                "metadata": {"trace_id": "tr-100"},
            },
            {
                "signal_id": "anom-001",
                "signal_type": "ANOMALY",
                "timestamp": "2026-08-29T12:00:15Z",
                "service": "booking-api",
                "environment": "production",
                "severity": "HIGH",
                "source_reference": "metric-001",
                "metadata": {"metric_name": "request_latency"},
            },
        ]
    }

    response = client.post("/api/v1/correlations/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["correlation_score"] >= 0.60
    assert data["is_correlated"] is True
    assert len(data["reasons"]) > 0
    assert any("same service: booking-api" in r for r in data["reasons"])


def test_create_and_fetch_correlation_group(client: TestClient, monkeypatch):
    """Test creating a persisted correlation group via POST /api/v1/correlations/groups."""
    # Mock IncidentServiceClient to simulate successful auto-incident creation
    def mock_handler(request: httpx.Request):
        if request.url.path == "/api/v1/incidents":
            return httpx.Response(status_code=201, json={"incident_key": "INC-000123"})
        if "/events" in request.url.path:
            return httpx.Response(status_code=201, json={"status": "attached"})
        return httpx.Response(status_code=404)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    # 2 signals sharing trace_id, error severity, same service within 5s
    payload = {
        "signals": [
            {
                "signal_id": "anom-101",
                "signal_type": "ANOMALY",
                "timestamp": "2026-08-29T12:01:30Z",
                "service": "booking-api",
                "environment": "production",
                "severity": "CRITICAL",
                "source_reference": "obs-999",
                "metadata": {"trace_id": "tr-shared-555", "metric_name": "request_latency"},
            },
            {
                "signal_id": "evt-101",
                "signal_type": "EVENT",
                "timestamp": "2026-08-29T12:01:35Z",
                "service": "booking-api",
                "environment": "production",
                "severity": "ERROR",
                "source_reference": "evt-555",
                "metadata": {"trace_id": "tr-shared-555"},
            },
        ]
    }

    create_res = client.post("/api/v1/correlations/groups", json=payload)
    assert create_res.status_code == 201
    group_data = create_res.json()

    group_key = group_data["group_key"]
    assert group_key.startswith("GRP-")
    assert group_data["primary_service"] == "booking-api"
    assert group_data["environment"] == "production"
    assert group_data["correlation_score"] >= 0.85
    assert len(group_data["signals"]) == 2
    assert group_data["incident_key"] == "INC-000123"

    # Fetch group by key
    fetch_res = client.get(f"/api/v1/correlations/groups/{group_key}")
    assert fetch_res.status_code == 200
    fetched = fetch_res.json()
    assert fetched["group_key"] == group_key
    assert len(fetched["signals"]) == 2


def test_list_correlation_groups_pagination_and_filters(client: TestClient):
    """Test listing correlation groups with pagination and filters."""
    for i in range(5):
        client.post(
            "/api/v1/correlations/groups",
            json={
                "signals": [
                    {
                        "signal_id": f"s1-{i}",
                        "signal_type": "EVENT",
                        "timestamp": f"2026-08-29T12:{i:02d}:00Z",
                        "service": "orders-service" if i % 2 == 0 else "users-service",
                        "environment": "production" if i < 3 else "staging",
                        "severity": "ERROR",
                    },
                    {
                        "signal_id": f"s2-{i}",
                        "signal_type": "ANOMALY",
                        "timestamp": f"2026-08-29T12:{i:02d}:10Z",
                        "service": "orders-service" if i % 2 == 0 else "users-service",
                        "environment": "production" if i < 3 else "staging",
                        "severity": "HIGH",
                    },
                ]
            },
        )

    # 1. Pagination
    res_p1 = client.get("/api/v1/correlations/groups?page=1&page_size=2")
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert p1_data["total"] == 5
    assert len(p1_data["items"]) == 2

    # 2. Filter by service
    res_srv = client.get("/api/v1/correlations/groups?service=orders-service")
    assert res_srv.status_code == 200
    assert res_srv.json()["total"] == 3

    # 3. Filter by environment
    res_env = client.get("/api/v1/correlations/groups?environment=staging")
    assert res_env.status_code == 200
    assert res_env.json()["total"] == 2


def test_get_nonexistent_group_404(client: TestClient):
    """Test retrieving non-existent group key returns 404."""
    response = client.get("/api/v1/correlations/groups/GRP-999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_validation_insufficient_signals(client: TestClient):
    """Test submitting less than 2 signals returns HTTP 422."""
    payload = {
        "signals": [
            {
                "signal_id": "solo-signal",
                "signal_type": "EVENT",
                "timestamp": "2026-08-29T12:00:00Z",
                "service": "solo-api",
                "environment": "production",
                "severity": "ERROR",
            }
        ]
    }
    res_eval = client.post("/api/v1/correlations/evaluate", json=payload)
    assert res_eval.status_code == 422

    res_grp = client.post("/api/v1/correlations/groups", json=payload)
    assert res_grp.status_code == 422
