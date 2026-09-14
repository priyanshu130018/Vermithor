from backend.app.summary.clients.incident_client import IncidentClient


def test_incident_client_fetch(monkeypatch):
    """Verify IncidentClient fetches incident payload."""
    client = IncidentClient()

    class MockRes:
        status_code = 200
        def json(self):
            return {
                "incident_key": "INC-000001",
                "title": "Booking Outage",
                "service": "booking-api",
            }

    monkeypatch.setattr("httpx.Client.get", lambda self, url: MockRes())

    inc = client.get_incident("INC-000001")
    assert inc is not None
    assert inc["incident_key"] == "INC-000001"
    assert inc["service"] == "booking-api"


def test_incident_client_not_found(monkeypatch):
    """Verify IncidentClient returns None on 404."""
    client = IncidentClient()

    class MockRes:
        status_code = 404

    monkeypatch.setattr("httpx.Client.get", lambda self, url: MockRes())
    assert client.get_incident("INC-NONEXISTENT") is None
