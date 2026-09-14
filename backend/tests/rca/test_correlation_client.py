import httpx
from backend.app.rca.clients.correlation_client import CorrelationServiceClient

_orig_client = httpx.Client


def test_correlation_client_get_group_success(monkeypatch):
    """Test retrieving correlation group data via CorrelationServiceClient."""
    def mock_handler(request: httpx.Request):
        assert request.url.path == "/api/v1/correlations/groups/GRP-000001"
        return httpx.Response(
            status_code=200,
            json={
                "group_key": "GRP-000001",
                "primary_service": "booking-api",
                "environment": "production",
                "correlation_score": 0.88,
                "signals": [
                    {
                        "signal_id": "anom-001",
                        "signal_type": "ANOMALY",
                        "service": "booking-api",
                        "timestamp": "2026-08-29T12:00:00Z",
                    }
                ],
            },
        )

    client = CorrelationServiceClient(base_url="http://test-correlation-service:8004")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    data = client.get_correlation_group("GRP-000001")
    assert data is not None
    assert data["group_key"] == "GRP-000001"
    assert len(data["signals"]) == 1


def test_correlation_client_not_found(monkeypatch):
    """Test 404 handling in CorrelationServiceClient."""
    def mock_handler(request: httpx.Request):
        return httpx.Response(status_code=404, json={"detail": "Not found"})

    client = CorrelationServiceClient(base_url="http://test-correlation-service:8004")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    data = client.get_correlation_group("GRP-999999")
    assert data is None


def test_correlation_client_network_failure(monkeypatch):
    """Test network connection failure in CorrelationServiceClient."""
    def mock_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection refused")

    client = CorrelationServiceClient(base_url="http://unavailable-service:8004")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    data = client.get_correlation_group("GRP-000001")
    assert data is None
