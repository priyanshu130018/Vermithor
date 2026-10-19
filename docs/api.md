# Vermithor API Reference

This document provides the authoritative API specification for the **Vermithor** FastAPI Modular Monolith and Nginx API Gateway.

---

## 1. Gateway Routing, Authentication & Base URLs

### 1.1 Base URLs & Interactive Documentation
- **Direct Backend API (Internal)**: `http://localhost:8000`
- **API Gateway (Public / Perimeter)**: `http://localhost:8080`
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc API Explorer**: `http://localhost:8000/redoc`
- **OpenAPI Schema (JSON)**: `http://localhost:8000/openapi.json`

### 1.2 API Authentication (FastAPI Native JWT)
All requests to protected API endpoints (`/api/v1/*`) must include an HTTP `Authorization` header containing an HMAC-SHA256 (HS256) JSON Web Token (JWT), forwarded by the Nginx reverse proxy and validated natively by FastAPI:

```text
Authorization: Bearer <JWT_TOKEN>
```

#### Token Validation Contract (`backend/app/common/security.py`)
- **Algorithm**: Strictly `HS256` (requests with `none` or asymmetric algorithms are rejected).
- **Signing Secret**: Validated against `JWT_SECRET`.
- **Subject (`sub`)**: Required, non-empty identity string.
- **Issuer (`iss`)**: Must equal `JWT_ISSUER` (default: `vermithor`).
- **Audience (`aud`)**: Must equal `JWT_AUDIENCE` (default: `vermithor-api`).
- **Expiration (`exp`)**: Required numeric timestamp; must be in the future (tolerates up to 30s clock skew).
- **Not Before (`nbf`) & Issued At (`iat`)**: If present, validated with 30s clock skew tolerance.

#### Request Tracing & Identity Propagation
The Nginx gateway forwards:
- `X-Request-ID`: Generated or preserved from inbound requests.
- `Authorization`: Forwarded untouched to FastAPI for cryptographic verification.
When authentication succeeds, FastAPI attaches the validated identity to `request.state.user_id`.
- `X-Request-ID`: Client-provided `X-Request-ID` or gateway-generated unique request UUID.

#### Authentication Failure Response (HTTP 401)
```json
{
  "error": "unauthorized",
  "message": "Invalid authentication token",
  "request_id": "c1f7a08b-64a2-4a7b-99f1-0ecdae9185a0"
}
```

### 1.3 Gateway Rate Limiting & Method Filters
The gateway enforces rate limiting using shared in-memory zones:
- **General API (`/api/v1/*`)**: 30 req/s, burst 20 (`nodelay`).
- **Incident Summaries (`/api/v1/summaries/*`)**: 2 req/s, burst 5 (`nodelay`).
- **Log Search & Processing (`/api/v1/logs/*`)**: 10 req/s, burst 20 (`nodelay`).
- **Rate Limit Response (HTTP 429)**: Returns `Retry-After: 5` header and JSON body:
  ```json
  {
    "error": "too_many_requests",
    "message": "Rate limit exceeded. Please retry later.",
    "request_id": "req-12345"
  }
  ```
- **Allowed HTTP Methods**: `GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`. All other verbs return `HTTP 405 Method Not Allowed`.

---

## 2. Health & System Probes

Public endpoints available without authentication:

### 2.1 Gateway Liveness Probe (`GET /health`)
- **URL**: `http://localhost:8080/health`
- **Method**: `GET`
- **Response**: `200 OK`
```json
{
  "service": "vermithor-gateway",
  "status": "healthy"
}
```

### 2.2 Backend Liveness Probe (`GET /health`)
- **URL**: `http://localhost:8000/health`
- **Method**: `GET`
- **Response**: `200 OK`
```json
{
  "service": "vermithor-backend",
  "status": "healthy"
}
```

### 2.3 Backend Readiness Probe (`GET /ready`)
- **URL**: `http://localhost:8000/ready`
- **Method**: `GET`
- **Response**: `200 OK` (checks live database connection via `SELECT 1`)
```json
{
  "service": "vermithor-backend",
  "status": "ready",
  "database": "connected",
  "environment": "development",
  "embedding_model_loaded": true,
  "embedding_provider": "huggingface",
  "provider_available": true,
  "llm_provider": "huggingface",
  "dimension": 384
}
```

### 2.4 Metrics Probe (`GET /metrics`)
- **URL**: `http://localhost:8000/metrics`
- **Method**: `GET`
- **Format**: Prometheus text exposition format (`text/plain`).

---

## 3. Core Domain APIs (`/api/v1`)

### 3.1 Telemetry Ingestion (`/api/v1/events`)

#### Ingest Telemetry Event (`POST /api/v1/events`)
Ingests raw events (logs, metric points, trace spans, or deployment markers) and enqueues Celery background tasks.

- **Request Body**:
```json
{
  "event_type": "log",
  "service_name": "checkout-service",
  "environment": "production",
  "timestamp": "2026-09-15T01:00:00Z",
  "payload": {
    "level": "ERROR",
    "message": "ConnectionPoolTimeoutException: Timeout waiting for database connection"
  }
}
```
- **Response (`201 Created`)**:
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "event_id": "evt-000001",
  "event_type": "log",
  "service_name": "checkout-service",
  "environment": "production",
  "timestamp": "2026-09-15T01:00:00Z",
  "status": "accepted"
}
```

#### List Events (`GET /api/v1/events`)
- **Parameters**: `page` (int, default 1), `page_size` (int, default 20), `service_name` (optional), `event_type` (optional).
- **Response (`200 OK`)**: Paginated list of ingested telemetry records.

---

### 3.2 Incident Management (`/api/v1/incidents`)

#### Create Incident (`POST /api/v1/incidents`)
- **Request Body**:
```json
{
  "title": "PostgreSQL DB Connection Saturation on Booking API",
  "severity": "CRITICAL",
  "primary_service": "booking-api",
  "environment": "production",
  "description": "Connection pool exhausted across 12 pods.",
  "labels": { "team": "checkout", "cluster": "us-east-2" }
}
```
- **Response (`201 Created`)**:
```json
{
  "id": "e9c20a81-9b1b-4d7a-b51c-4b5d27b9c9f4",
  "incident_key": "INC-000001",
  "title": "PostgreSQL DB Connection Saturation on Booking API",
  "status": "DETECTED",
  "severity": "CRITICAL",
  "primary_service": "booking-api",
  "environment": "production",
  "detected_at": "2026-09-15T01:02:00Z",
  "created_at": "2026-09-15T01:02:05Z"
}
```

#### Get Incident by Key (`GET /api/v1/incidents/{incident_key}`)
- **Path Parameter**: `incident_key` (e.g. `INC-000001`).
- **Response (`200 OK`)**: Detailed incident record with timeline milestones and linked event IDs.

#### List Incidents (`GET /api/v1/incidents`)
- **Parameters**: `page` (default 1), `page_size` (default 20), `status` (`DETECTED`, `INVESTIGATING`, `IDENTIFIED`, `MONITORING`, `RESOLVED`, `CLOSED`), `severity` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), `environment` (string).

#### State Transition Actions
- `POST /api/v1/incidents/{incident_key}/investigate` -> Transitions to `INVESTIGATING`.
- `POST /api/v1/incidents/{incident_key}/mitigate` -> Transitions to `IDENTIFIED` or `MONITORING`.
- `POST /api/v1/incidents/{incident_key}/resolve` -> Transitions to `RESOLVED`.
- `POST /api/v1/incidents/{incident_key}/close` -> Transitions to `CLOSED`.
- `POST /api/v1/incidents/{incident_key}/link-events` -> Associates event UUID array `{"event_ids": [...]}`.
- `GET /api/v1/incidents/{incident_key}/timeline` -> Fetches ordered event timeline.

---

### 3.3 Metric Observations & Anomalies (`/api/v1/observations`, `/api/v1/anomalies`)

#### Submit Observations (`POST /api/v1/observations`)
- **Request Body**:
```json
{
  "service": "booking-api",
  "environment": "production",
  "metric_name": "http_request_duration_seconds",
  "metric_value": 4.82,
  "unit": "seconds",
  "timestamp": "2026-09-15T01:01:00Z",
  "labels": { "endpoint": "/checkout" }
}
```
- **Response (`201 Created`)**: Stored metric observation record.

#### List Anomalies (`GET /api/v1/anomalies`)
- **Parameters**: `page`, `page_size`, `service`, `severity` (`WARNING`, `CRITICAL`), `detector` (`statistical`, `isolation_forest`).
- **Response (`200 OK`)**: Detected metric anomaly records with calculated Z-scores and confidence metrics.

---

### 3.4 Signal Correlation (`/api/v1/correlations`)

#### Evaluate Active Window (`POST /api/v1/correlations/evaluate`)
- **Request Body**:
```json
{
  "window_seconds": 900,
  "environment": "production"
}
```
- **Response (`200 OK`)**: Newly grouped correlation candidates, linkage scores, and auto-created incidents.

#### Get Correlation Group (`GET /api/v1/correlations/groups/{group_key}`)
- **Path Parameter**: `group_key` (e.g. `GRP-000001`).
- **Response (`200 OK`)**: List of grouped anomaly IDs, log alert signals, and aggregate correlation confidence score.

---

### 3.5 Root Cause Analysis (`/api/v1/rca`)

#### Analyze Correlation Group (`POST /api/v1/rca/analyze/{group_key}`)
Executes graph-based causal evaluation on a correlation group.
- **Path Parameter**: `group_key` (e.g. `GRP-000001`).
- **Response (`201 Created`)**:
```json
{
  "analysis_key": "RCA-000001",
  "group_key": "GRP-000001",
  "primary_root_cause": "Database connection saturation on postgres",
  "confidence": 0.88,
  "causal_graph": {
    "nodes": [
      { "id": "postgres", "role": "database", "anomaly_score": 0.95 },
      { "id": "booking-api", "role": "api", "anomaly_score": 0.78 }
    ],
    "edges": [
      { "source": "postgres", "target": "booking-api", "relation": "connection_timeout" }
    ]
  },
  "candidates": [
    {
      "rank": 1,
      "candidate_name": "Database connection saturation on postgres",
      "service": "postgres",
      "confidence": 0.88,
      "factors": { "temporal": 0.92, "topology": 0.85, "severity": 0.90 }
    }
  ]
}
```

#### Get RCA by Analysis Key (`GET /api/v1/rca/{analysis_key}`)
- **Path Parameter**: `analysis_key` (e.g. `RCA-000001`).

#### Get RCA by Incident Key (`GET /api/v1/rca/incident/{incident_key}`)
- **Path Parameter**: `incident_key` (e.g. `INC-000001`).

---

### 3.6 Log Intelligence (`/api/v1/logs`)

#### Ingest & Process Log (`POST /api/v1/logs/process`)
- **Request Body**:
```json
{
  "service": "booking-api",
  "environment": "production",
  "timestamp": "2026-09-15T01:00:00Z",
  "raw_message": "2026-09-15 01:00:00 ERROR [booking-api] Database connection failed for user 4912"
}
```
- **Response (`200 OK`)**: Sanitized log record, extracted Drain template ID (`tpl_db_conn_err`), domain category (`DATABASE`), and 384-dimensional embedding confirmation.

#### Semantic Vector Log Search (`POST /api/v1/logs/search`)
- **Request Body**:
```json
{
  "query": "database connection pool timeout",
  "limit": 5,
  "service": "booking-api"
}
```
- **Response (`200 OK`)**: Ranked log matches ordered by pgvector cosine similarity.

---

### 3.7 Knowledge Retrieval & Runbooks (`/api/v1/retrieval`, `/api/v1/runbooks`)

#### Multi-Source Retrieval (`POST /api/v1/retrieval/search`)
- **Request Body**:
```json
{
  "query": "PostgreSQL connection pool exhausted",
  "top_k": 5
}
```
- **Response (`200 OK`)**: Ranked results across runbooks, previous incidents, and log clusters with citation IDs.

#### Assemble Bounded RAG Context (`POST /api/v1/rag/context`)
- **Request Body**:
```json
{
  "incident_key": "INC-000001",
  "max_context_chars": 20000
}
```
- **Response (`200 OK`)**: Citation-tagged prompt string (`context_text`), loaded sources (`valid_source_ids`), and token budgeting metrics.

#### Create Runbook (`POST /api/v1/runbooks`)
- **Request Body**:
```json
{
  "runbook_key": "RBK-PG-POOL",
  "title": "PostgreSQL Connection Saturation SOP",
  "service": "postgres-db",
  "content": "### Mitigation Steps\n1. Increase max_connections in postgresql.conf\n2. Scale PgBouncer pooler replicas",
  "tags": ["database", "postgres", "connection-pool"]
}
```
- **Response (`201 Created`)**: Stored runbook with calculated 384-D vector embedding.

---

### 3.8 AI Incident Summaries (`/api/v1/summaries`)

#### Generate Incident Summary (`POST /api/v1/summaries/incident/{incident_key}`)
Assembles RAG context, invokes the Hugging Face LLM provider, validates evidence citations, and persists the postmortem summary.
- **Parameters**: `regenerate` (bool, default `false`).
- **Response (`200 OK`)**:
```json
{
  "id": "8f3b2e1a-4c5d-6e7f-8a9b-0c1d2e3f4a5b",
  "summary_key": "SUM-000001",
  "incident_key": "INC-000001",
  "probable_root_cause": "PostgreSQL Connection Pool Exhaustion on postgres",
  "confidence": 0.88,
  "summary_text": "At 01:00:00 UTC, the booking-api experienced a cascade of HTTP 500 errors caused by connection saturation on the primary PostgreSQL database.",
  "impact_scope": "Booking API and downstream checkout processing",
  "affected_services": ["postgres", "booking-api"],
  "evidence": [
    {
      "source_id": "LOG:evt-db-01",
      "claim": "FATAL: remaining connection slots are reserved for superusers",
      "verified": true
    },
    {
      "source_id": "RUNBOOK:RBK-PG-POOL",
      "claim": "SOP recommends connection pool expansion",
      "verified": true
    }
  ],
  "recommended_actions": [
    "Increase PgBouncer client pool size",
    "Restart stalled booking-api worker instances"
  ],
  "limitations": [],
  "is_fallback": false,
  "model_used": "meta-llama/Llama-3.1-8B-Instruct",
  "created_at": "2026-09-15T01:05:00Z"
}
```

#### Get Summary by Key (`GET /api/v1/summaries/{summary_key}`)
- **Path Parameter**: `summary_key` (e.g. `SUM-000001`).

#### List Summaries (`GET /api/v1/summaries`)
- **Parameters**: `page`, `page_size`, `incident_key`, `status`, `min_confidence`.

---

## 4. API Request Examples

### 4.1 Ingest Event with Curl
```bash
curl -X POST http://localhost:8080/api/v1/events \
  -H "Authorization: Bearer <YOUR_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "log",
    "service_name": "checkout-service",
    "environment": "production",
    "timestamp": "2026-09-15T01:00:00Z",
    "payload": {
      "level": "ERROR",
      "message": "Connection pool timeout"
    }
  }'
```

### 4.2 Ingest Event with Windows PowerShell
```powershell
$Headers = @{
    "Authorization" = "Bearer <YOUR_JWT_TOKEN>"
    "Content-Type"  = "application/json"
}

$Body = @{
    event_type   = "log"
    service_name = "checkout-service"
    environment  = "production"
    timestamp    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    payload      = @{
        level   = "ERROR"
        message = "Connection pool timeout"
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8080/api/v1/events" -Method POST -Headers $Headers -Body $Body
```

### 4.3 Trigger AI Summary Generation
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/api/v1/summaries/incident/INC-000001" -Method POST -Headers $Headers
```
