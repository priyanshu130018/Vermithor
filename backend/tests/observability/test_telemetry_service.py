from datetime import datetime, timezone
import pytest

from backend.app.correlation.schemas.correlation import SignalType
from backend.app.ingestion.schemas.event import EventType, Severity
from backend.app.observability.clients.jaeger_client import JaegerClient
from backend.app.observability.clients.prometheus_client import PrometheusClient
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService


def test_convert_telemetry_to_evidence():
    """Verify that Prometheus metrics and Jaeger traces normalize into Vermithor observations, events, and signals."""
    service = TelemetryEvidenceService(
        prometheus_client=PrometheusClient(),
        jaeger_client=JaegerClient(),
    )

    mock_snapshot = {
        "service": "payment-api",
        "lookback_minutes": 15,
        "collected_at": "2026-10-18T10:00:00Z",
        "sources": {
            "prometheus": {
                "base_url": "http://prometheus:9090",
                "metrics": {
                    "request_rate_per_sec": {"value": 85.0, "query": "rate(...)"},
                    "error_rate_5xx": {"value": 0.15, "query": "error_rate(...)"},
                    "latency_p95_seconds": {"value": 3.8, "query": "histogram_quantile(...)"},
                },
            },
            "jaeger": {
                "base_url": "http://jaeger:16686",
                "total_traces": 1,
                "summaries": [
                    {
                        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                        "root_service": "payment-api",
                        "root_operation": "POST /api/v1/payments",
                        "start_time": "2026-10-18T09:58:00+00:00",
                        "duration_ms": 3800.0,
                        "span_count": 8,
                        "services_involved": ["payment-api", "postgres"],
                        "has_error": True,
                        "error_spans": [{"span_id": "sp1", "error_message": "Pool timeout"}],
                        "bottleneck_spans": [{"span_id": "sp1", "duration_ms": 3800.0}],
                    }
                ],
            },
        },
    }

    evidence = service.convert_telemetry_to_evidence(mock_snapshot, environment="production")

    assert evidence["service"] == "payment-api"
    assert evidence["observations_count"] == 3
    assert evidence["events_count"] == 1
    assert evidence["signals_count"] == 4  # 3 metric signals + 1 trace signal

    # Verify Metric Observations
    obs_names = [o.metric_name for o in evidence["observations"]]
    assert "error_rate_5xx" in obs_names
    assert "latency_p95_seconds" in obs_names
    assert "request_rate_per_sec" in obs_names

    # Verify Trace Event
    evt = evidence["events"][0]
    assert evt.event_type == EventType.TRACE
    assert evt.severity == Severity.ERROR
    assert evt.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert "Pool timeout" in str(evt.metadata)

    # Verify Correlation Signals
    signal_types = [s.signal_type for s in evidence["signals"]]
    assert SignalType.METRIC in signal_types
    assert SignalType.TRACE in signal_types
    trace_sig = next(s for s in evidence["signals"] if s.signal_type == SignalType.TRACE)
    assert trace_sig.metadata["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert trace_sig.severity == "ERROR"
