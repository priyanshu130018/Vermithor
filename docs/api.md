# Vermithor API Documentation

The Vermithor backend exposes RESTful HTTP API endpoints under the `/api/v1` namespace. Interactive OpenAPI (Swagger) documentation is available at `/docs` and ReDoc format at `/redoc`.

---

## 1. Base URL & Interactive Specs

- **Base API URL**: `http://localhost:8000` (Direct Monolith) or `http://localhost:8080` (Gateway Boundary)
- **Swagger Documentation**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **OpenAPI JSON Spec**: `http://localhost:8000/openapi.json`

---

## 2. Health & System Probes

### Liveness Probe (`GET /health`)
- **Method**: `GET`
- **Path**: `/health`
- **Response**: `200 OK`
  ```json
  {
    "service": "vermithor-backend",
    "status": "healthy"
  }
  ```

### Readiness Probe (`GET /ready`)
- **Method**: `GET`
- **Path**: `/ready`
- **Response**: `200 OK` (or `200` with status `degraded` if database connection fails)
  ```json
  {
    "service": "vermithor-backend",
    "status": "ready",
    "database": "connected",
    "environment": "development",
    "embedding_model_loaded": true,
    "provider_available": true,
    "llm_provider": "ollama",
    "dimension": 384
  }
  ```

---

## 3. Core Domain APIs (`/api/v1`)

### 3.1 Telemetry Ingestion (`POST /api/v1/events`)
- **Method**: `POST`
- **Path**: `/api/v1/events`
- **Purpose**: Ingest raw telemetry events (log entries, metric points, trace spans, or deployment markers).
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
- **Response**: `201 Created`
  ```json
  {
    "id": "evt_9f8d1a2b3c4d",
    "status": "accepted",
    "task_id": "celery-task-12345"
  }
  ```

---

### 3.2 Incidents API (`/api/v1/incidents`)

#### List Incidents (`GET /api/v1/incidents`)
- **Method**: `GET`
- **Path**: `/api/v1/incidents`
- **Query Parameters**: `status` (optional), `service` (optional), `limit` (default: 50)
- **Response**: `200 OK`
  ```json
  [
    {
      "id": "inc_7f8a9b0c",
      "title": "PostgreSQL Connection Pool Exhaustion on checkout-service",
      "status": "DETECTED",
      "severity": "CRITICAL",
      "created_at": "2026-09-15T01:05:00Z",
      "root_cause_service": "postgres-db"
    }
  ]
  ```

#### Get Incident Details (`GET /api/v1/incidents/{id}`)
- **Method**: `GET`
- **Path**: `/api/v1/incidents/{id}`
- **Response**: `200 OK`

---

### 3.3 Anomaly Detection (`/api/v1/anomalies`)

#### Detect Anomalies (`POST /api/v1/anomalies/detect`)
- **Method**: `POST`
- **Path**: `/api/v1/anomalies/detect`
- **Purpose**: Evaluate metric observations against Z-score statistical thresholds and Isolation Forest models.

---

### 3.4 Incident Correlation (`/api/v1/correlations`)

#### Evaluate Signal Correlation (`POST /api/v1/correlations/evaluate`)
- **Method**: `POST`
- **Path**: `/api/v1/correlations/evaluate`
- **Purpose**: Run sliding time-window signal correlation across topology boundaries.

---

### 3.5 Root Cause Analysis (`POST /api/v1/rca/analyze`)
- **Method**: `POST`
- **Path**: `/api/v1/rca/analyze`
- **Request Body**:
  ```json
  {
    "incident_id": "inc_7f8a9b0c"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "incident_id": "inc_7f8a9b0c",
    "root_cause_service": "postgres-db",
    "confidence_score": 0.94,
    "top_candidates": [
      {
        "service_name": "postgres-db",
        "score": 0.94,
        "primary_factor": "temporal_precedence_and_pool_exhaustion"
      }
    ],
    "causal_graph_nodes": ["checkout-service", "cart-service", "postgres-db"]
  }
  ```

---

### 3.6 Log Intelligence & HDBSCAN (`POST /api/v1/logs/cluster`)
- **Method**: `POST`
- **Path**: `/api/v1/logs/cluster`
- **Purpose**: Perform log template masking, dense vector embedding (`MiniLM-L6-v2`), and HDBSCAN density clustering.

---

### 3.7 Multi-Source RAG Retrieval (`POST /api/v1/retrieval/search`)
- **Method**: `POST`
- **Path**: `/api/v1/retrieval/search`
- **Request Body**:
  ```json
  {
    "query": "PostgreSQL connection pool exhaustion",
    "service_name": "checkout-service",
    "top_k": 5
  }
  ```
- **Response**: `200 OK`

---

### 3.8 LLM Synthesis & Evidence Validation (`POST /api/v1/summaries/generate`)
- **Method**: `POST`
- **Path**: `/api/v1/summaries/generate`
- **Request Body**:
  ```json
  {
    "incident_id": "inc_7f8a9b0c"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "incident_id": "inc_7f8a9b0c",
    "summary": "PostgreSQL database connection pool exhausted due to unindexed queries.",
    "root_cause": "postgres-db",
    "blast_radius": ["checkout-service", "payment-service"],
    "mitigation_steps": [
      "Scale database connection pool size",
      "Restart checkout-service pods"
    ],
    "is_fallback": false,
    "evidence_validated": true
  }
  ```
