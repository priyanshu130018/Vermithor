from fastapi.testclient import TestClient
from backend.app.summary.clients.incident_client import IncidentClient
from backend.app.summary.clients.rca_client import RCAClient
from backend.app.summary.clients.retrieval_client import RetrievalClient


def test_summary_idempotency_and_regeneration(client: TestClient, monkeypatch):
    """Test idempotent retrieval on duplicate requests and forced regeneration when requested."""
    mock_incident = {"incident_key": "INC-IDEM-01", "service": "booking-api"}
    mock_rca = {"analysis_key": "RCA-001", "primary_confidence": 0.90}
    mock_rag = {"context": [{"source_id": "evt-01"}], "context_text": "### [LOG:evt-01] Error"}

    monkeypatch.setattr(IncidentClient, "get_incident", lambda self, key: mock_incident)
    monkeypatch.setattr(RCAClient, "get_rca_reports", lambda self, **kwargs: [mock_rca])
    monkeypatch.setattr(RetrievalClient, "get_rag_context", lambda self, **kwargs: mock_rag)

    # 1. First call generates summary
    res1 = client.post("/api/v1/summaries/incident/INC-IDEM-01")
    assert res1.status_code == 200
    key1 = res1.json()["summary_key"]

    # 2. Second call without regenerate returns same key
    res2 = client.post("/api/v1/summaries/incident/INC-IDEM-01")
    assert res2.status_code == 200
    assert res2.json()["summary_key"] == key1

    # 3. Third call with regenerate=True updates the summary
    res3 = client.post("/api/v1/summaries/incident/INC-IDEM-01?regenerate=true")
    assert res3.status_code == 200
    assert res3.json()["summary_key"] == key1
