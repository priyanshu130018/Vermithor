from fastapi.testclient import TestClient
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.rca.db.models import RCAAnalysis

_orig_client = httpx.Client


def test_analyze_correlation_group_api(client: TestClient, monkeypatch):
    """Test full RCA analysis pipeline via POST /api/v1/rca/analyze/{group_key}."""
    def mock_handler(request: httpx.Request):
        if request.url.path == "/api/v1/correlations/groups/GRP-000001":
            return httpx.Response(
                status_code=200,
                json={
                    "group_key": "GRP-000001",
                    "primary_service": "booking-api",
                    "environment": "production",
                    "correlation_score": 0.89,
                    "signals": [
                        {
                            "signal_id": "dep-001",
                            "signal_type": "DEPLOYMENT",
                            "service": "booking-api",
                            "timestamp": "2026-08-29T12:00:00Z",
                            "severity": "INFO",
                            "relationship_score": 0.75,
                        },
                        {
                            "signal_id": "anom-db-001",
                            "signal_type": "ANOMALY",
                            "service": "booking-api",
                            "timestamp": "2026-08-29T12:01:30Z",
                            "severity": "HIGH",
                            "metadata": {"metric_name": "db_query_latency"},
                            "relationship_score": 0.92,
                        },
                        {
                            "signal_id": "err-500-001",
                            "signal_type": "EVENT",
                            "service": "booking-api",
                            "timestamp": "2026-08-29T12:02:30Z",
                            "severity": "ERROR",
                            "message": "HTTP 500 Server Error",
                            "relationship_score": 0.80,
                        },
                    ],
                },
            )
        return httpx.Response(status_code=404)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    # 1. Analyze group
    response = client.post("/api/v1/rca/analyze/GRP-000001")
    assert response.status_code == 201
    data = response.json()

    analysis_key = data["analysis_key"]
    assert analysis_key.startswith("RCA-")
    assert data["group_key"] == "GRP-000001"
    assert data["status"] == "COMPLETED"
    assert "Database" in data["primary_root_cause"] or "Recent deployment" in data["primary_root_cause"]
    assert data["primary_confidence"] >= 0.70
    assert len(data["candidates"]) >= 2
    assert len(data["causal_chain"]) == 3
    assert len(data["edges"]) == 3

    # 2. Idempotency test: calling analyze again returns existing analysis
    dup_res = client.post("/api/v1/rca/analyze/GRP-000001")
    assert dup_res.status_code == 201 or dup_res.status_code == 200
    assert dup_res.json()["analysis_key"] == analysis_key

    # 3. Retrieve analysis by key
    fetch_res = client.get(f"/api/v1/rca/{analysis_key}")
    assert fetch_res.status_code == 200
    assert fetch_res.json()["analysis_key"] == analysis_key


def test_analyze_nonexistent_group_404(client: TestClient, monkeypatch):
    """Test analyzing non-existent correlation group returns 404."""
    def mock_handler(request: httpx.Request):
        return httpx.Response(status_code=404)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    response = client.post("/api/v1/rca/analyze/GRP-999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_rca_analyses_pagination_and_filters(client: TestClient, monkeypatch):
    """Test listing RCA analyses with pagination and filters."""
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            json={
                "group_key": "GRP-001",
                "primary_service": "booking-api",
                "environment": "production",
                "signals": [
                    {
                        "signal_id": "anom-1",
                        "signal_type": "ANOMALY",
                        "service": "booking-api",
                        "timestamp": "2026-08-29T12:00:00Z",
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client.post("/api/v1/rca/analyze/GRP-001")

    res = client.get("/api/v1/rca?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


def test_get_nonexistent_rca_analysis_404(client: TestClient):
    """Test retrieving non-existent RCA key returns 404."""
    response = client.get("/api/v1/rca/RCA-999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
