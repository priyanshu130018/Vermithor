import os
import yaml
import json
from fastapi.testclient import TestClient

from backend.app.main import app as incident_app


def test_prometheus_config_valid():
    """Verify Prometheus scrape configuration exists and contains Vermithor services."""
    config_path = "infrastructure/prometheus/prometheus.yml"
    assert os.path.exists(config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    job_names = [job["job_name"] for job in config.get("scrape_configs", [])]
    expected_jobs = [
        "vermithor-gateway",
        "vermithor-backend",
    ]
    for expected in expected_jobs:
        assert expected in job_names


def test_grafana_provisioning_valid():
    """Verify Grafana datasource and dashboard provisioning files."""
    ds_path = "infrastructure/grafana/provisioning/datasources/datasources.yml"
    assert os.path.exists(ds_path)
    with open(ds_path, "r", encoding="utf-8") as f:
        ds_config = yaml.safe_load(f)
    ds_names = [ds["name"] for ds in ds_config.get("datasources", [])]
    assert "Prometheus" in ds_names
    assert "Jaeger" in ds_names

    dashboard_path = "infrastructure/grafana/dashboards/vermithor-overview.json"
    assert os.path.exists(dashboard_path)
    with open(dashboard_path, "r", encoding="utf-8") as f:
        dashboard = json.load(f)
    assert "Vermithor" in dashboard["title"]


def test_service_metrics_endpoint_exposition():
    """Verify /metrics endpoint returns standard Prometheus metrics format."""
    client = TestClient(incident_app)
    # Trigger an API request to increment counter
    client.get("/health")

    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    metrics_text = metrics_res.text
    assert "http_requests_total" in metrics_text
    assert "http_request_duration_seconds" in metrics_text
    assert "active_requests" in metrics_text


def test_trace_context_propagation():
    """Verify W3C traceparent header is received and propagated."""
    client = TestClient(incident_app)
    fake_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    response = client.get("/health", headers={"traceparent": fake_traceparent})
    assert response.status_code == 200
    assert response.headers.get("X-Trace-Parent") == fake_traceparent
