# Vermithor Observability & SRE Telemetry

Vermithor integrates the three pillars of modern observability: **Metrics**, **Distributed Tracing**, and **Structured Logs**.

---

## 1. Metrics & Monitoring Architecture

```text
FastAPI Modular Monolith (:8000) & API Gateway (:8080)
         │
         ▼ (HTTP GET /metrics)
┌───────────────────────┐
│  Prometheus (:9090)   │ (Scrapes backend and gateway metrics every 15s)
└───────────┬───────────┘
            │
            ▼ (PromQL Queries)
┌───────────────────────┐
│   Grafana (:3000)     │ (Pre-provisioned Golden Signals & SRE Dashboards)
└───────────────────────┘
```

### Standard Golden Signals Exposed

Every microservice exposes standardized Prometheus metrics via `backend.shared.telemetry.metrics`:

1. **Traffic (Throughput)**:
   `http_requests_total{service="...", method="POST", endpoint="/api/v1/events", status="201"}`
2. **Latency (Duration)**:
   `http_request_duration_seconds_bucket{service="...", le="0.05"}` (Histogram buckets: `5ms`, `10ms`, `25ms`, `50ms`, `100ms`, `250ms`, `500ms`, `1s`, `2.5s`, `5s`, `10s`)
3. **Concurrency (Saturation)**:
   `active_requests{service="..."}` (Gauge tracking concurrent active socket requests)
4. **Domain Metrics**:
   `vermithor_summaries_generated_total{model="llama3.2:3b", status="completed"}`

### Pre-configured Grafana Dashboard

The repository includes a ready-to-use Grafana dashboard located at `infrastructure/grafana/dashboards/vermithor-overview.json`:
- Real-time RPS per microservice.
- P50, P95, and P99 latency panels.
- HTTP 4xx vs 5xx error rate gauges.
- Active in-flight requests per service.

---

## 2. Distributed Tracing with OpenTelemetry & Jaeger

All inter-service HTTP requests propagate distributed trace context using the W3C TraceContext standard:

```text
Client Request
      │ (Headers: traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01)
      ▼
┌──────────────┐
│  API Gateway │ (Injects/Propagates x-request-id & W3C traceparent)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Summary Svc  │ (Generates child span: 'POST /api/v1/summaries/incident/INC-01')
└──────┬───────┘
       │
       ├──► [ RCA Service Span ]
       │        └──► [ Correlation Service Span ]
       └──► [ Retrieval Service Span ]
                └──► [ Log Intelligence Span (pgvector cosine search) ]
```

- **OpenTelemetry SDK**: Configured with `OTLPSpanExporter` pushing spans to Jaeger via HTTP endpoint `http://jaeger:4318/v1/traces`.
- **Trace Header Echoing**: Services automatically echo `X-Trace-ID` and `X-Trace-Parent` in HTTP response headers for end-to-end debugging.
- **Jaeger UI (`http://localhost:16686`)**: Search traces by `service.name`, operation, tag (`http.status_code=500`), or duration.
