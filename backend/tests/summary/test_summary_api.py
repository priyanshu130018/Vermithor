from fastapi.testclient import TestClient
from backend.app.summary.clients.incident_client import IncidentClient
from backend.app.summary.clients.rca_client import RCAClient
from backend.app.summary.clients.retrieval_client import RetrievalClient


def test_generate_and_get_incident_summary(client: TestClient, monkeypatch):
    """Test full incident summary generation workflow and retrieval."""
    # 1. Mock upstream clients
    mock_incident = {
        "incident_key": "INC-000001",
        "title": "Booking API Outage",
        "service": "booking-api",
        "environment": "production",
        "severity": "CRITICAL",
        "started_at": "2026-08-29T12:00:00Z",
    }
    mock_rca = {
        "analysis_key": "RCA-000001",
        "primary_root_cause": "PostgreSQL Connection Pool Exhaustion",
        "primary_confidence": 0.89,
        "candidates": [],
    }
    mock_rag = {
        "context_text": "### [LOG:evt-db-01] Connection pool saturated\n### [RCA:RCA-000001] RCA Root Cause",
        "context": [{"source_id": "evt-db-01"}, {"source_id": "RCA-000001"}],
    }

    monkeypatch.setattr(IncidentClient, "get_incident", lambda self, key: mock_incident)
    monkeypatch.setattr(RCAClient, "get_rca_reports", lambda self, **kwargs: [mock_rca])
    monkeypatch.setattr(RetrievalClient, "get_rag_context", lambda self, **kwargs: mock_rag)

    # 2. Call POST generate summary
    res = client.post("/api/v1/summaries/incident/INC-000001")
    assert res.status_code == 200
    data = res.json()

    assert data["incident_key"] == "INC-000001"
    assert data["summary_key"].startswith("SUM-")
    assert data["status"] == "COMPLETED"
    assert data["confidence"] == 0.89  # RCA structured confidence preserved!
    assert "PostgreSQL Connection Pool Exhaustion" in data["probable_root_cause"]
    assert len(data["evidence"]) >= 1
    assert data["evidence"][0]["source_id"] in ["evt-db-01", "RCA-000001"]

    summary_key = data["summary_key"]

    # 3. Call GET summary by key
    get_res = client.get(f"/api/v1/summaries/{summary_key}")
    assert get_res.status_code == 200
    assert get_res.json()["summary_key"] == summary_key

    # 4. Call GET list summaries
    list_res = client.get("/api/v1/summaries?incident_key=INC-000001")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1
