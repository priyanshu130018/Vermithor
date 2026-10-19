import pytest
from opentelemetry.sdk.resources import SERVICE_NAME as OTEL_SERVICE_NAME
from backend.app.common.telemetry import (
    init_tracer,
    sanitize_url,
    sanitize_metric_endpoint,
)


def test_init_tracer_resource_service_name():
    """Verify that init_tracer configures the OpenTelemetry Resource with the correct service name."""
    tracer = init_tracer("vermithor-backend")
    assert tracer._instrumentation_scope.name == "vermithor-backend"
    assert getattr(tracer, "resource", None).attributes.get("service.name") == "vermithor-backend"

    worker_tracer = init_tracer("vermithor-worker")
    assert worker_tracer._instrumentation_scope.name == "vermithor-worker"


def test_sanitize_url_redacts_sensitive_query_parameters():
    """Verify that sensitive query parameter values are redacted."""
    raw_url = "https://vermithor.local/api/v1/search?token=my-secret-jwt-12345&query=database&password=admin_pass&key=secret_api_key"
    sanitized = sanitize_url(raw_url)

    assert "my-secret-jwt-12345" not in sanitized
    assert "admin_pass" not in sanitized
    assert "secret_api_key" not in sanitized
    assert "token=%5BREDACTED%5D" in sanitized or "token=[REDACTED]" in sanitized
    assert "password=%5BREDACTED%5D" in sanitized or "password=[REDACTED]" in sanitized
    assert "key=%5BREDACTED%5D" in sanitized or "key=[REDACTED]" in sanitized
    assert "query=database" in sanitized


def test_sanitize_url_handles_clean_urls_and_edge_cases():
    """Verify that clean URLs without query parameters remain unchanged."""
    url = "https://vermithor.local/health"
    assert sanitize_url(url) == url

    assert sanitize_url("") == ""


def test_sanitize_metric_endpoint_bounds_cardinality():
    """Verify that high-cardinality tokens (UUIDs, incident keys, IDs) are collapsed."""
    # UUIDs
    assert sanitize_metric_endpoint("/api/v1/observations/123e4567-e89b-12d3-a456-426614174000") == "/api/v1/observations/{id}"

    # Entity Keys
    assert sanitize_metric_endpoint("/api/v1/incidents/INC-2026-1042") == "/api/v1/incidents/{inc_key}"
    assert sanitize_metric_endpoint("/api/v1/correlations/groups/GRP-000001") == "/api/v1/correlations/groups/{grp_key}"
    assert sanitize_metric_endpoint("/api/v1/rca/RCA-000042") == "/api/v1/rca/{rca_key}"
    assert sanitize_metric_endpoint("/api/v1/runbooks/RB-000006") == "/api/v1/runbooks/{rb_key}"

    # Numeric IDs
    assert sanitize_metric_endpoint("/api/v1/items/98765/details") == "/api/v1/items/{id}/details"

    # Static routes
    assert sanitize_metric_endpoint("/health") == "/health"
    assert sanitize_metric_endpoint("/api/v1/incidents") == "/api/v1/incidents"

    # Fast-path with route template
    assert sanitize_metric_endpoint("/api/v1/incidents/INC-123", "/api/v1/incidents/{incident_key}") == "/api/v1/incidents/{incident_key}"
