import httpx
import pytest
from fastapi.testclient import TestClient

_orig_client = httpx.Client


def test_observability_endpoints_require_jwt_auth(unauthenticated_client: TestClient):
    """Verify that all observability endpoints enforce JWT authentication and return 401."""
    assert unauthenticated_client.get("/api/v1/observability/health").status_code == 401
    assert unauthenticated_client.get("/api/v1/observability/metrics/summary").status_code == 401
    assert unauthenticated_client.get("/api/v1/observability/traces").status_code == 401
    assert unauthenticated_client.post("/api/v1/observability/collect", json={"service": "test"}).status_code == 401


def test_observability_health_authenticated(client: TestClient, monkeypatch):
    """Verify authenticated health check returns Prometheus and Jaeger statuses."""
    def mock_handler(request: httpx.Request):
        if "/api/v1/targets" in request.url.path:
            return httpx.Response(status_code=200, json={"data": {"activeTargets": []}})
        if "/api/services" in request.url.path:
            return httpx.Response(status_code=200, json={"data": ["vermithor-backend"]})
        return httpx.Response(status_code=404)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    resp = client.get("/api/v1/observability/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "prometheus" in data
    assert "jaeger" in data
    assert data["prometheus"]["status"] == "healthy"
    assert data["jaeger"]["status"] == "healthy"


def test_observability_metrics_summary_authenticated(client: TestClient, monkeypatch):
    """Verify authenticated metrics summary endpoint."""
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {}, "value": [1792312200.0, "15.4"]}],
                },
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    resp = client.get("/api/v1/observability/metrics/summary?service=vermithor-backend&window_minutes=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "vermithor-backend"
    assert data["window_minutes"] == 10
    assert "metrics" in data
    assert data["metrics"]["request_rate_per_sec"]["value"] == 15.4


def test_observability_traces_authenticated(client: TestClient, monkeypatch):
    """Verify authenticated traces query endpoint."""
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            json={
                "data": [
                    {
                        "traceID": "trace-101",
                        "spans": [
                            {
                                "traceID": "trace-101",
                                "spanID": "span-1",
                                "operationName": "GET /api/v1/incidents",
                                "duration": 12000,
                                "tags": [{"key": "http.status_code", "type": "int64", "value": 200}],
                                "processID": "p1",
                            }
                        ],
                        "processes": {"p1": {"serviceName": "vermithor-backend"}},
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    resp = client.get("/api/v1/observability/traces?service=vermithor-backend&lookback_seconds=600")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "vermithor-backend"
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == "trace-101"
    assert data["traces"][0]["duration_ms"] == 12.0


def test_observability_collect_dry_run_and_persist(client: TestClient, monkeypatch):
    """Verify collecting live telemetry and converting to signals, both dry-run and persisted."""
    def mock_handler(request: httpx.Request):
        if "query" in request.url.path:
            return httpx.Response(
                status_code=200,
                json={
                    "status": "success",
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {}, "value": [1792312200.0, "0.08"]}],
                    },
                },
            )
        if "traces" in request.url.path:
            return httpx.Response(
                status_code=200,
                json={
                    "data": [
                        {
                            "traceID": "4bf92f3577b34da6a3ce929d0e0e1111",
                            "spans": [
                                {
                                    "traceID": "4bf92f3577b34da6a3ce929d0e0e1111",
                                    "spanID": "sp-1",
                                    "operationName": "POST /charge",
                                    "duration": 550000,
                                    "tags": [{"key": "http.status_code", "type": "int64", "value": 500}],
                                    "processID": "p1",
                                }
                            ],
                            "processes": {"p1": {"serviceName": "payment-api"}},
                        }
                    ]
                },
            )
        return httpx.Response(status_code=404)

    from backend.app.ingestion.services.task_publisher import TaskPublisher
    monkeypatch.setattr(TaskPublisher, "publish_event_processing", lambda *args, **kwargs: True)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: _orig_client(transport=httpx.MockTransport(mock_handler)),
    )

    # 1. Dry run (persist=False)
    payload_dry = {
        "service": "payment-api",
        "lookback_minutes": 15,
        "environment": "production",
        "persist": False,
    }
    resp = client.post("/api/v1/observability/collect", json=payload_dry)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["service"] == "payment-api"
    assert data["observations_count"] > 0
    assert data["events_count"] > 0
    assert len(data["signals"]) > 0

    # 2. Persisted (persist=True)
    payload_persist = {
        "service": "payment-api",
        "lookback_minutes": 15,
        "environment": "production",
        "persist": True,
    }
    resp_persist = client.post("/api/v1/observability/collect", json=payload_persist)
    assert resp_persist.status_code == 200
    data_persist = resp_persist.json()
    assert data_persist["status"] == "success"
    assert len(data_persist["persisted_observations"]) > 0
    assert len(data_persist["persisted_events"]) > 0
