from backend.app.summary.clients.retrieval_client import RetrievalClient


def test_retrieval_client_fetch_rag_context(monkeypatch):
    """Verify RetrievalClient fetches grounded RAG context."""
    client = RetrievalClient()

    class MockRes:
        status_code = 200
        def json(self):
            return {
                "incident_key": "INC-000001",
                "context_text": "### [LOG:evt-001] Postgres error",
                "context": [{"source_id": "evt-001"}],
            }

    monkeypatch.setattr("httpx.Client.post", lambda self, url, json=None: MockRes())

    res = client.get_rag_context("INC-000001")
    assert res is not None
    assert res["incident_key"] == "INC-000001"
    assert "evt-001" in res["context_text"]
