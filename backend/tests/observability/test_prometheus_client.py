from datetime import datetime, timezone
import httpx
import pytest

from backend.app.observability.clients.prometheus_client import PrometheusClient

_orig_client = httpx.Client


def test_prometheus_check_health_success(monkeypatch):
    """Test successful Prometheus health and scrape target check."""
    def mock_handler(request: httpx.Request):
        assert request.url.path == "/api/v1/targets"
        return httpx.Response(
            status_code=200,
            json={
                "status": "success",
                "data": {
                    "activeTargets": [
                        {
                            "labels": {"job": "vermithor-backend", "instance": "vermithor-backend:8000"},
                            "health": "up",
                            "lastScrape": "2026-10-18T10:00:00Z",
                            "lastError": "",
                        }
                    ]
                },
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = PrometheusClient(base_url="http://mock-prometheus:9090")
    health = client.check_health()

    assert health["status"] == "healthy"
    assert health["total_targets"] == 1
    assert health["healthy_targets"] == 1
    assert health["targets"][0]["health"] == "up"


def test_prometheus_check_health_connection_error(monkeypatch):
    """Test graceful handling when Prometheus server is down."""
    def mock_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = PrometheusClient(base_url="http://unavailable-prometheus:9090")
    health = client.check_health()

    assert health["status"] == "unavailable"
    assert "Connection refused" in health["error"]


def test_prometheus_query_instant_success(monkeypatch):
    """Test successful instant query execution and vector response parsing."""
    def mock_handler(request: httpx.Request):
        assert request.url.path == "/api/v1/query"
        assert "query=http_requests_total" in str(request.url)
        return httpx.Response(
            status_code=200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"service": "vermithor-backend", "status": "200"},
                            "value": [1792312200.0, "42.0"],
                        }
                    ],
                },
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = PrometheusClient(base_url="http://mock-prometheus:9090")
    res = client.query_instant("http_requests_total")

    assert res["status"] == "success"
    assert len(res["result"]) == 1
    assert res["result"][0]["value"][1] == "42.0"


def test_prometheus_query_timeout(monkeypatch):
    """Test timeout handling in Prometheus instant query."""
    def mock_handler(request: httpx.Request):
        raise httpx.TimeoutException("Query timed out")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = PrometheusClient(base_url="http://mock-prometheus:9090")
    res = client.query_instant("sum(rate(huge_query[1h]))")

    assert res["status"] == "timeout"
    assert res["result"] == []


def test_prometheus_get_service_metrics(monkeypatch):
    """Test retrieving key service performance metrics."""
    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "error_rate" in url_str or "5.." in url_str:
            val = "0.02"
        elif "latency" in url_str or "histogram_quantile" in url_str:
            val = "0.145"
        elif "active_requests" in url_str:
            val = "3"
        else:
            val = "12.5"

        return httpx.Response(
            status_code=200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"service": "vermithor-backend"},
                            "value": [1792312200.0, val],
                        }
                    ],
                },
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    client = PrometheusClient(base_url="http://mock-prometheus:9090")
    metrics = client.get_service_metrics("vermithor-backend")

    assert metrics["service"] == "vermithor-backend"
    assert "metrics" in metrics
    assert metrics["metrics"]["request_rate_per_sec"]["value"] == 12.5
    assert metrics["metrics"]["error_rate_5xx"]["value"] == 0.02
    assert metrics["metrics"]["latency_p95_seconds"]["value"] == 0.145
    assert metrics["metrics"]["active_requests"]["value"] == 3.0
