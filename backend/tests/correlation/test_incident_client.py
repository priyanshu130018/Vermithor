from datetime import datetime, timezone
import httpx
from backend.app.correlation.services.incident_client import IncidentServiceClient

_orig_client = httpx.Client


def test_incident_client_create_incident_success(monkeypatch):
    """Test successful incident creation via IncidentServiceClient."""
    def mock_handler(request: httpx.Request):
        assert request.url.path == "/api/v1/incidents"
        return httpx.Response(
            status_code=201,
            json={
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "incident_key": "INC-000042",
                "title": "Correlated Incident",
                "status": "DETECTED",
            },
        )

    client = IncidentServiceClient(base_url="http://test-incident-service:8002")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    incident_key = client.create_incident(
        title="Correlated Incident",
        description="Auto-generated incident from correlation group",
        severity="CRITICAL",
        environment="production",
        started_at=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        confidence=0.92,
    )

    assert incident_key == "INC-000042"


def test_incident_client_attach_event_evidence(monkeypatch):
    """Test attaching event evidence to incident via IncidentServiceClient."""
    def mock_handler(request: httpx.Request):
        assert request.url.path == "/api/v1/incidents/INC-000042/events"
        return httpx.Response(
            status_code=201,
            json={
                "event_id": "evt-001",
                "relation_type": "PRIMARY_SIGNAL",
                "score": 0.95,
            },
        )

    client = IncidentServiceClient(base_url="http://test-incident-service:8002")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    success = client.attach_event_evidence(
        incident_key="INC-000042",
        event_id="evt-001",
        relation_type="PRIMARY_SIGNAL",
        score=0.95,
    )

    assert success is True


def test_incident_client_network_error_resilience(monkeypatch):
    """Test graceful handling when Incident Service is unavailable."""
    def mock_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection refused")

    client = IncidentServiceClient(base_url="http://unavailable-host:8002")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    incident_key = client.create_incident(
        title="Correlated Incident",
        description="Auto-generated incident from correlation group",
        severity="HIGH",
        environment="production",
        started_at=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        confidence=0.88,
    )

    assert incident_key is None
