import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.common.security import require_jwt_auth
from backend.app.observability.clients.jaeger_client import JaegerClient
from backend.app.observability.clients.prometheus_client import PrometheusClient
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observability", tags=["observability"])


class TelemetryCollectRequest(BaseModel):
    service: str = Field(..., min_length=1, max_length=128, description="Target service name")
    lookback_minutes: int = Field(15, ge=1, le=1440, description="Time window in minutes")
    environment: str = Field("production", min_length=1, max_length=64, description="Environment name")
    persist: bool = Field(True, description="Whether to persist collected evidence in database")


@router.get(
    "/health",
    summary="Check Prometheus and Jaeger connectivity",
    description="Validates that internal observability backends are reachable from Vermithor.",
)
def get_observability_health(
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> Dict[str, Any]:
    """Check connectivity to Prometheus and Jaeger endpoints."""
    prom = PrometheusClient()
    jaeger = JaegerClient()

    prom_health = prom.check_health()
    jaeger_health = jaeger.check_health()

    overall_healthy = prom_health.get("status") in ["healthy", "degraded"] and jaeger_health.get("status") in ["healthy", "degraded"]

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "prometheus": prom_health,
        "jaeger": jaeger_health,
    }


@router.get(
    "/metrics/summary",
    summary="Query Prometheus service metric indicators",
    description="Retrieves request rate, 5xx error rate, p95 latency, and active in-flight requests for a service.",
)
def get_metrics_summary(
    service: str = Query("vermithor-backend", description="Target service name"),
    window_minutes: int = Query(15, ge=1, le=1440, description="Sliding window in minutes"),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> Dict[str, Any]:
    """Retrieve summarized Prometheus metrics for a service."""
    prom = PrometheusClient()
    return prom.get_service_metrics(service=service, window_minutes=window_minutes)


@router.get(
    "/traces",
    summary="Query Jaeger trace summaries",
    description="Retrieves recent traces and detects errors and latency bottlenecks for a service.",
)
def get_traces_summary(
    service: str = Query("vermithor-backend", description="Target service name"),
    lookback_seconds: int = Query(900, ge=30, le=86400, description="Lookback window in seconds"),
    limit: int = Query(20, ge=1, le=100, description="Maximum traces to retrieve"),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> Dict[str, Any]:
    """Retrieve trace summaries from Jaeger."""
    jaeger = JaegerClient()
    raw_traces = jaeger.get_traces(service=service, lookback_seconds=lookback_seconds, limit=limit)
    summaries = jaeger.summarize_traces(raw_traces)
    return {
        "service": service,
        "total_traces": len(raw_traces),
        "traces": summaries,
    }


@router.get(
    "/traces/{trace_id}",
    summary="Get single trace details by trace_id",
    description="Retrieves full trace details from Jaeger by hexadecimal trace ID.",
)
def get_trace_by_id(
    trace_id: str,
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> Dict[str, Any]:
    """Retrieve specific trace by ID."""
    jaeger = JaegerClient()
    trace = jaeger.get_trace(trace_id=trace_id)
    if not trace:
        return {"status": "not_found", "trace_id": trace_id}
    summaries = jaeger.summarize_traces([trace])
    return {
        "status": "found",
        "trace_id": trace_id,
        "summary": summaries[0] if summaries else None,
        "raw_trace": trace,
    }


@router.post(
    "/collect",
    status_code=status.HTTP_200_OK,
    summary="Collect and normalize live telemetry as incident evidence",
    description="Aggregates Prometheus metrics and Jaeger traces, converts them to observations and events, and optionally persists them.",
)
def collect_telemetry_evidence(
    payload: TelemetryCollectRequest,
    db: Session = Depends(get_db),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> Dict[str, Any]:
    """Collect telemetry and ingest as Vermithor evidence."""
    service = TelemetryEvidenceService()
    if payload.persist:
        return service.ingest_telemetry_as_evidence(
            db=db,
            service=payload.service,
            lookback_minutes=payload.lookback_minutes,
            environment=payload.environment,
        )
    snapshot = service.get_telemetry_snapshot(
        service=payload.service,
        lookback_minutes=payload.lookback_minutes,
    )
    evidence = service.convert_telemetry_to_evidence(
        snapshot=snapshot,
        environment=payload.environment,
    )
    return {
        "status": "success",
        "service": payload.service,
        "environment": payload.environment,
        "observations_count": evidence["observations_count"],
        "events_count": evidence["events_count"],
        "signals_count": evidence["signals_count"],
        "signals": [s.model_dump(mode="json") for s in evidence["signals"]],
    }
