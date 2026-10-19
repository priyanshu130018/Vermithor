import httpx
import pytest

from backend.app.observability.clients.jaeger_client import JaegerClient

_orig_client = httpx.Client


def test_jaeger_check_health_and_services(monkeypatch):
    """Test successful health check and services listing from Jaeger."""
    def mock_handler(request: httpx.Request):
        assert request.url.path == "/api/services"
        return httpx.Response(
            status_code=200,
            json={"data": ["vermithor-backend", "vermithor-worker"], "total": 2},
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = JaegerClient(base_url="http://mock-jaeger:16686")
    health = client.check_health()

    assert health["status"] == "healthy"
    assert health["services_count"] == 2
    assert "vermithor-backend" in health["services"]


def test_jaeger_check_health_connection_error(monkeypatch):
    """Test graceful handling when Jaeger query service is unreachable."""
    def mock_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = JaegerClient(base_url="http://unavailable-jaeger:16686")
    health = client.check_health()

    assert health["status"] == "unavailable"
    assert "Connection refused" in health["error"]


def test_jaeger_get_traces_and_summarize(monkeypatch):
    """Test trace querying and summary extraction including errors and bottlenecks."""
    raw_trace_payload = {
        "data": [
            {
                "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
                "spans": [
                    {
                        "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
                        "spanID": "00f067aa0ba902b7",
                        "operationName": "POST /api/v1/payments",
                        "startTime": 1792312200000000,
                        "duration": 650000,  # 650 ms (bottleneck)
                        "tags": [
                            {"key": "http.status_code", "type": "int64", "value": 500},
                            {"key": "error", "type": "bool", "value": True},
                            {"key": "error.message", "type": "string", "value": "Database connection timeout"},
                        ],
                        "processID": "p1",
                    },
                    {
                        "traceID": "4bf92f3577b34da6a3ce929d0e0e4736",
                        "spanID": "5fb397be34d23b0f",
                        "operationName": "db.query",
                        "startTime": 1792312200100000,
                        "duration": 520000,  # 520 ms
                        "references": [{"refType": "CHILD_OF", "spanID": "00f067aa0ba902b7"}],
                        "tags": [
                            {"key": "db.system", "type": "string", "value": "postgresql"},
                        ],
                        "processID": "p1",
                    },
                ],
                "processes": {
                    "p1": {"serviceName": "vermithor-backend"},
                },
            }
        ]
    }

    def mock_handler(request: httpx.Request):
        assert request.url.path == "/api/traces"
        return httpx.Response(status_code=200, json=raw_trace_payload)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = JaegerClient(base_url="http://mock-jaeger:16686")
    traces = client.get_traces("vermithor-backend")
    assert len(traces) == 1

    summaries = client.summarize_traces(traces, bottleneck_threshold_ms=500.0)
    assert len(summaries) == 1
    s = summaries[0]
    assert s["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert s["root_service"] == "vermithor-backend"
    assert s["duration_ms"] == 650.0
    assert s["has_error"] is True
    assert len(s["error_spans"]) == 1
    assert s["error_spans"][0]["error_message"] == "Database connection timeout"
    assert len(s["bottleneck_spans"]) == 2  # Both root (650ms) and child (520ms) exceed 500ms
