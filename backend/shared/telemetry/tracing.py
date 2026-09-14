import os
from typing import Callable, Dict, Optional
from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def init_tracer(service_name: str) -> trace.Tracer:
    """Initializes OpenTelemetry Tracer with OTLP or fallback exporter."""
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


def setup_tracing(app: FastAPI, service_name: str) -> None:
    """Attaches OpenTelemetry tracing middleware to FastAPI app."""
    tracer = init_tracer(service_name)
    propagator = TraceContextTextMapPropagator()

    @app.middleware("http")
    async def tracing_middleware(request: Request, call_next: Callable) -> Response:
        if request.url.path in ("/metrics", "/health", "/docs", "/openapi.json"):
            return await call_next(request)

        # Extract incoming context
        carrier = {k: v for k, v in request.headers.items()}
        context = propagator.extract(carrier=carrier)

        span_name = f"{request.method} {request.url.path}"
        with tracer.start_as_current_span(span_name, context=context) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("service.name", service_name)

            req_id = request.headers.get("x-request-id")
            if req_id:
                span.set_attribute("http.request_id", req_id)

            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)

            # Echo trace ID in response
            span_ctx = span.get_span_context()
            if span_ctx.is_valid:
                trace_id = format(span_ctx.trace_id, "032x")
                response.headers["X-Trace-ID"] = trace_id

            return response
