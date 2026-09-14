from backend.app.retrieval.clients.rca_client import RCAServiceClient


def test_rca_client_search_success(monkeypatch):
    """Verify RCAServiceClient maps reports into RetrievalResultItem."""
    client = RCAServiceClient()

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "items": [
                    {
                        "analysis_key": "RCA-000001",
                        "group_key": "GRP-000001",
                        "primary_root_cause": "PostgreSQL Connection Pool Exhaustion",
                        "primary_confidence": 0.94,
                        "status": "COMPLETED",
                        "started_at": "2026-08-29T12:00:00Z",
                        "candidates": [
                            {"candidate_name": "PostgreSQL Connection Pool Exhaustion", "score": 0.94}
                        ],
                    }
                ],
                "total": 1,
            }

    monkeypatch.setattr("httpx.Client.get", lambda self, url, params=None: MockResponse())

    items, warn = client.search_rca_reports(top_k=5)
    assert warn is None
    assert len(items) == 1
    assert items[0].source_id == "RCA-000001"
    assert items[0].citation == "[RCA:RCA-000001]"
    assert "PostgreSQL Connection Pool Exhaustion" in items[0].title
