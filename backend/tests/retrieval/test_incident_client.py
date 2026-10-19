from backend.app.retrieval.clients.incident_client import IncidentServiceClient


def test_incident_client_search_success(monkeypatch):
    """Verify IncidentServiceClient maps incidents to RetrievalResultItem."""
    client = IncidentServiceClient()

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "items": [
                    {
                        "incident_key": "INC-000001",
                        "title": "Booking API Outage",
                        "description": "Database pool saturated causing HTTP 500",
                        "service": "booking-api",
                        "environment": "production",
                        "severity": "CRITICAL",
                        "status": "DETECTED",
                        "started_at": "2026-08-29T12:00:00Z",
                    }
                ],
                "total": 1,
            }

    monkeypatch.setattr("backend.app.incidents.services.incident_service.IncidentService.list_incidents", lambda **kwargs: ([], 0))
    monkeypatch.setattr("httpx.Client.get", lambda self, url, params=None: MockResponse())

    items, warn = client.search_incidents(service="booking-api", top_k=5)
    assert warn is None
    assert len(items) == 1
    assert items[0].source_id == "INC-000001"
    assert items[0].citation == "[INCIDENT:INC-000001]"


def test_incident_client_single_get(monkeypatch):
    """Verify IncidentServiceClient fetches single incident."""
    client = IncidentServiceClient()

    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "incident_key": "INC-000001",
                "title": "Booking API Outage",
                "service": "booking-api",
            }

    monkeypatch.setattr("backend.app.incidents.services.incident_service.IncidentService.get_incident_by_key", lambda db, key: None)
    monkeypatch.setattr("httpx.Client.get", lambda self, url, params=None: MockResponse())

    inc = client.get_incident("INC-000001")
    assert inc is not None
    assert inc["incident_key"] == "INC-000001"
