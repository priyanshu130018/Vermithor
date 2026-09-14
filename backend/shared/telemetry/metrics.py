import time
from typing import Callable
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
)


def _get_or_create_metric(metric_cls, name, documentation, labelnames=(), **kwargs):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return metric_cls(name, documentation, labelnames=labelnames, **kwargs)
    except Exception:
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]
        raise


HTTP_REQUESTS_TOTAL = _get_or_create_metric(
    Counter,
    "http_requests_total",
    "Total number of HTTP requests processed",
    ["service", "method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = _get_or_create_metric(
    Histogram,
    "http_request_duration_seconds",
    "HTTP request latency histogram in seconds",
    ["service", "method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
)

ACTIVE_REQUESTS = _get_or_create_metric(
    Gauge,
    "active_requests",
    "Number of active in-flight HTTP requests",
    ["service"],
)


def setup_telemetry(app: FastAPI, service_name: str) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        endpoint = request.url.path
        method = request.method
        ACTIVE_REQUESTS.labels(service=service_name).inc()
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            traceparent = request.headers.get("traceparent")
            if traceparent:
                response.headers["X-Trace-Parent"] = traceparent
            return response
        finally:
            duration = time.perf_counter() - start_time
            ACTIVE_REQUESTS.labels(service=service_name).dec()
            HTTP_REQUESTS_TOTAL.labels(
                service=service_name,
                method=method,
                endpoint=endpoint,
                status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                service=service_name,
                method=method,
                endpoint=endpoint,
            ).observe(duration)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
