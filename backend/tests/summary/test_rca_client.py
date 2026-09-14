from backend.app.summary.clients.rca_client import RCAClient


def test_rca_client_fetch_reports(monkeypatch):
    """Verify RCAClient fetches list of RCA reports."""
    client = RCAClient()

    class MockRes:
        status_code = 200
        def json(self):
            return {
                "items": [
                    {
                        "analysis_key": "RCA-000001",
                        "primary_root_cause": "Database connection exhaustion",
                        "primary_confidence": 0.93,
                    }
                ]
            }

    monkeypatch.setattr("httpx.Client.get", lambda self, url, params=None: MockRes())

    reports = client.get_rca_reports()
    assert len(reports) == 1
    assert reports[0]["analysis_key"] == "RCA-000001"
    assert reports[0]["primary_confidence"] == 0.93
