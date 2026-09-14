# Vermithor Domain Modules Reference

This document describes the domain modules comprising the **Vermithor** FastAPI Modular Monolith.

---

## 1. Ingestion Module (`/api/v1/events`)

- **Domain Path**: `backend/app/ingestion/`
- **Purpose**: High-throughput validation and intake of raw telemetry events, logs, and metric observations. Dispatches background processing tasks via Celery.
- **Key Endpoints**:
  - `POST /api/v1/events`: Ingests an event payload (validates format, deduplicates, queues Celery job).
  - `GET /api/v1/events`: Paginated search and filtering of stored events.
  - `GET /api/v1/events/{id}`: Fetch single event by internal ID or `event_id`.
- **Dependencies**: PostgreSQL, Redis, Celery worker.

---

## 2. Incident Module (`/api/v1/incidents`)

- **Domain Path**: `backend/app/incidents/`
- **Purpose**: Manages the authoritative lifecycle of incidents, severity tracking, event-to-incident associations, and state transitions.
- **Key Endpoints**:
  - `POST /api/v1/incidents`: Creates a new incident entity (`DETECTED`).
  - `GET /api/v1/incidents`: Lists incidents with filtering by severity, status, and environment.
  - `GET /api/v1/incidents/{incident_key}`: Fetches full incident details, timeline events, and linked signals.
  - `PATCH /api/v1/incidents/{incident_key}/status`: Transitions status (`DETECTED` -> `INVESTIGATING` -> `IDENTIFIED` -> `MONITORING` -> `RESOLVED`).

---

## 3. Anomaly Detection Module (`/api/v1/anomalies`, `/api/v1/observations`)

- **Domain Path**: `backend/app/anomaly/`
- **Purpose**: Ingests metric time-series observations and performs real-time outlier detection using rolling statistical z-score evaluation and scikit-learn Isolation Forest algorithms.
- **Key Endpoints**:
  - `POST /api/v1/observations`: Ingests metric observations (CPU, memory, request latency, error rates).
  - `POST /api/v1/anomalies/evaluate`: Triggers anomaly evaluation across recent observation windows.
  - `GET /api/v1/anomalies`: Lists detected anomaly records with severity ratings and anomaly scores.

---

## 4. Correlation Module (`/api/v1/correlation`)

- **Domain Path**: `backend/app/correlation/`
- **Purpose**: Groups temporally and topologically related anomalies, logs, and deployment events into correlation candidates.

---

## 5. RCA Engine Module (`/api/v1/rca`)

- **Domain Path**: `backend/app/rca/`
- **Purpose**: Executes multi-dimensional root cause analysis over correlation groups using temporal precedence, NetworkX service topology DAGs, and deployment evidence.

---

## 6. Log Intelligence Module (`/api/v1/logs`)

- **Domain Path**: `backend/app/log_intelligence/`
- **Purpose**: Performs log masking, template extraction, 384-D sentence-transformer embeddings, and HDBSCAN density clustering.

---

## 7. Multi-Source Retrieval Module (`/api/v1/retrieval`, `/api/v1/runbooks`)

- **Domain Path**: `backend/app/retrieval/`
- **Purpose**: Retrieves vector-indexed runbooks and historical incidents via cosine similarity over pgvector.

---

## 8. Structured Summary Module (`/api/v1/summaries`)

- **Domain Path**: `backend/app/summary/`
- **Purpose**: Assembles bounded context prompts for Ollama (`llama3.2:3b`) and validates synthesized claims against ingested telemetry.
