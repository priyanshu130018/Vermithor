from backend.app.retrieval.clients.log_intelligence_client import LogIntelligenceClient


def test_log_client_success_mapping(monkeypatch):
    """Verify LogIntelligenceClient maps API results into RetrievalResultItem."""
    client = LogIntelligenceClient()

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "query": "database timeout",
                "total_results": 1,
                "results": [
                    {
                        "log_id": "123e4567-e89b-12d3-a456-426614174000",
                        "source_event_id": "evt-101",
                        "timestamp": "2026-08-29T12:00:00Z",
                        "service": "booking-api",
                        "environment": "production",
                        "severity": "ERROR",
                        "category": "DATABASE",
                        "message": "Connection refused to PostgreSQL",
                        "template": "Connection refused to PostgreSQL",
                        "similarity_score": 0.88,
                    }
                ],
            }

    monkeypatch.setattr("httpx.Client.post", lambda self, url, json: MockResponse())

    items, warn = client.search_logs("database timeout", top_k=5)
    assert warn is None
    assert len(items) == 1
    assert items[0].source_id == "evt-101"
    assert items[0].citation == "[LOG:evt-101]"
    assert items[0].similarity_score == 0.88


def test_log_client_network_error_resilience(monkeypatch):
    """Verify LogIntelligenceClient captures network exception as warning without crashing."""
    client = LogIntelligenceClient()

    def mock_post(self, url, json):
        raise ConnectionError("Connection refused to port 8006")

    monkeypatch.setattr("httpx.Client.post", mock_post)

    items, warn = client.search_logs("database timeout", top_k=5)
    assert items == []
    assert warn is not None
    assert "Log Intelligence Service unavailable" in warn
