import os
import time
from typing import Callable, Dict, Optional
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def _get_or_create_metric(metric_cls, name, documentation, labelnames=(), **kwargs):
    """Safely get existing metric from registry or instantiate new one without DuplicatedTimeseries errors."""
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

SUMMARIES_GENERATED_TOTAL = _get_or_create_metric(
    Counter,
    "vermithor_summaries_generated_total",
    "Total number of incident summaries synthesized",
    ["model", "status"],
)

LOGS_CLUSTERED_TOTAL = _get_or_create_metric(
    Counter,
    "logs_clustered_total",
    "Total number of log messages processed by clustering",
    ["service", "environment"],
)

LOG_CLUSTERS_CREATED_TOTAL = _get_or_create_metric(
    Counter,
    "log_clusters_created_total",
    "Total number of non-noise log clusters discovered",
    ["category"],
)

LOG_CLUSTER_NOISE_TOTAL = _get_or_create_metric(
    Counter,
    "log_cluster_noise_total",
    "Total number of outlier/noise logs identified by HDBSCAN",
    ["service"],
)

LOG_CLUSTERING_DURATION_SECONDS = _get_or_create_metric(
    Histogram,
    "log_clustering_duration_seconds",
    "Time spent running HDBSCAN log clustering in seconds",
    ["status"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

RCA_ANALYSIS_TOTAL = _get_or_create_metric(
    Counter,
    "rca_analysis_total",
    "Total number of Root Cause Analyses executed",
    ["status"],
)

RCA_ANALYSIS_DURATION_SECONDS = _get_or_create_metric(
    Histogram,
    "rca_analysis_duration_seconds",
    "Time spent computing RCA analysis in seconds",
    ["status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

RCA_CANDIDATE_COUNT = _get_or_create_metric(
    Histogram,
    "rca_candidate_count",
    "Number of RCA candidates generated per analysis",
    buckets=(1.0, 2.0, 3.0, 5.0, 10.0, 20.0),
)

RCA_UNKNOWN_TOTAL = _get_or_create_metric(
    Counter,
    "rca_unknown_total",
    "Total number of RCA analyses resulting in UNKNOWN or insufficient evidence",
)

RAG_RETRIEVAL_TOTAL = _get_or_create_metric(
    Counter,
    "rag_retrieval_total",
    "Total number of RAG knowledge retrieval queries executed",
    ["source_type", "status"],
)

RAG_RETRIEVAL_DURATION_SECONDS = _get_or_create_metric(
    Histogram,
    "rag_retrieval_duration_seconds",
    "Time spent executing RAG retrieval in seconds",
    ["status"],
    buckets=(0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

SUMMARY_GENERATION_TOTAL = _get_or_create_metric(
    Counter,
    "summary_generation_total",
    "Total number of incident summary generation requests",
    ["provider", "status"],
)

SUMMARY_GENERATION_DURATION_SECONDS = _get_or_create_metric(
    Histogram,
    "summary_generation_duration_seconds",
    "Time spent synthesizing incident summaries in seconds",
    ["provider", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

SUMMARY_VALIDATION_FAILURES_TOTAL = _get_or_create_metric(
    Counter,
    "summary_validation_failures_total",
    "Total number of summary generation evidence validation failures",
    ["reason"],
)


def init_tracer(service_name: str) -> trace.Tracer:
    """Initializes OpenTelemetry Tracer with OTLP HTTP exporter."""
    provider = TracerProvider()
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception:
            pass

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def inject_trace_context(headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Injects current W3C TraceContext into outbound request headers."""
    carrier = headers.copy() if headers else {}
    propagator = TraceContextTextMapPropagator()
    propagator.inject(carrier)
    return carrier


def setup_telemetry(app: FastAPI, service_name: str = "vermithor-backend") -> None:
    """Attaches Prometheus metrics middleware, OpenTelemetry tracing, and /metrics endpoint."""
    tracer = init_tracer(service_name)
    propagator = TraceContextTextMapPropagator()

    @app.middleware("http")
    async def telemetry_middleware(request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        endpoint = request.url.path
        method = request.method
        ACTIVE_REQUESTS.labels(service=service_name).inc()
        start_time = time.perf_counter()
        status_code = 500

        # Extract incoming W3C trace context if present
        carrier = {k: v for k, v in request.headers.items()}
        context = propagator.extract(carrier=carrier)

        span_name = f"{request.method} {request.url.path}"
        try:
            with tracer.start_as_current_span(span_name, context=context) as span:
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.url", str(request.url))
                span.set_attribute("service.name", service_name)

                req_id = request.headers.get("x-request-id")
                if req_id:
                    span.set_attribute("http.request_id", req_id)

                response = await call_next(request)
                status_code = response.status_code
                span.set_attribute("http.status_code", status_code)

                # Traceparent & Trace ID echo in response
                traceparent = request.headers.get("traceparent")
                if traceparent:
                    response.headers["X-Trace-Parent"] = traceparent

                span_ctx = span.get_span_context()
                if span_ctx.is_valid:
                    trace_id = format(span_ctx.trace_id, "032x")
                    response.headers["X-Trace-ID"] = trace_id

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


setup_tracing = setup_telemetry
