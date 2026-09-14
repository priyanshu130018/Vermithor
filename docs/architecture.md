# Vermithor Architecture

Vermithor is a modular, AI-assisted Production Incident Intelligence Platform designed to ingest distributed application telemetry, detect anomalous patterns, group co-occurring signals into incidents, pinpoint root causes through causal topology graphs, retrieve relevant runbooks and historical postmortems, and synthesize grounded, evidence-backed natural language incident summaries.

---

## 1. System Topology

```text
                                  Client Browser
                                        │
                                        ▼ (HTTP: 5173 / Ingress)
                              ┌───────────────────┐
                              │  React Dashboard  │
                              └─────────┬─────────┘
                                        │ (JWT / REST)
                                        ▼
                              ┌───────────────────┐
                              │    API Gateway    │ (Port 8080: Nginx / OpenResty)
                              └─────────┬─────────┘
                                        │ (Reverse Proxy / Auth Boundary)
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │       FastAPI Modular Monolith (:8000)       │
                 │                                              │
                 │  ├── Ingestion Domain (/api/v1/events)       │
                 │  ├── Anomaly Detection (/api/v1/anomalies)   │
                 │  ├── Log Intelligence (/api/v1/logs)         │
                 │  ├── Incident Correlation (/api/v1/incidents)│
                 │  ├── Service Topology (/api/v1/topology)     │
                 │  ├── RCA Engine (/api/v1/rca)                │
                 │  ├── Multi-Source RAG (/api/v1/retrieval)    │
                 │  └── LLM Synthesis (/api/v1/summaries)       │
                 └──────┬───────────────────────┬───────────────┘
                        │                       │
               (Celery) │                       │ (SQLAlchemy 2.0 / pgvector)
                        ▼                       ▼
                ┌──────────────┐        ┌──────────────────────────────┐
                │ Celery Worker│        │ PostgreSQL 16 + pgvector DB  │
                └───────┬──────┘        └──────────────────────────────┘
                        │ (Redis Queue)                 ▲
                        ▼                               │
                ┌──────────────┐                        │
                │ Redis 7      │                        │ (Context Assembly)
                └──────────────┘                        │
                                           ┌────────────┴────────────┐
                                           │ Local Ollama (llama3.2) │
                                           └─────────────────────────┘
```

---

## 2. Component Directory

| Component | Port | Primary Tech | Role |
|---|---|---|---|
| **API Gateway** | `8080` | Nginx / Lua | Single entrypoint, JWT authentication boundary (HS256), rate limiting, upstream reverse proxy |
| **Frontend** | `5173` | React 18, TypeScript, Vite, Tailwind | SRE operator dashboard, real-time incident review, RCA graph explorer, RAG runbooks, AI summaries |
| **Modular Monolith API** | `8000` | FastAPI, SQLAlchemy 2.0, Pydantic v2 | Unified API server hosting all domain routers under `/api/v1/` |
| **Ingestion Module** | `/api/v1/events` | FastAPI, Pydantic | Event & log ingestion, schema validation, task dispatching |
| **Celery Worker** | Background | Celery | Background event processor & asynchronous job execution worker |
| **Anomaly Module** | `/api/v1/anomalies` | Scikit-Learn, NumPy | Statistical z-score evaluation & Isolation Forest metric anomaly detection |
| **Correlation Module**| `/api/v1/correlations` | NetworkX, SQLAlchemy | Multi-signal temporal windowing, cross-service correlation grouping |
| **Incident Module** | `/api/v1/incidents` | FastAPI, SQLAlchemy | Incident lifecycle state machine (`DETECTED` -> `ANALYZING` -> `RESOLVED`), timeline tracking |
| **Topology Module** | Internal DAG | NetworkX, SQLAlchemy | Causal service graph construction & microservice dependency DAG mapping |
| **RCA Module** | `/api/v1/rca` | FastAPI, SQLAlchemy, NetworkX | Root cause candidate scoring, temporal precedence ranking, blast radius computation |
| **Log Intelligence** | `/api/v1/logs` | Sentence-Transformers, HDBSCAN | Log template extraction, secret masking, 384-D vector embeddings, density clustering |
| **Retrieval (RAG)** | `/api/v1/retrieval` | SQLAlchemy, pgvector | Semantic similarity search, historical incident retrieval, runbook matching |
| **Summary & Validation** | `/api/v1/summaries` | FastAPI, Pydantic, HTTP Client | Prompt construction, local Ollama (llama3.2) invocation, multi-point evidence verification |
| **PostgreSQL** | `5432` | PostgreSQL 16 + pgvector | Relational state and vector similarity storage |
| **Redis** | `6379` | Redis 7 | Celery message broker and caching layer |
| **Prometheus** | `9090` | Prometheus | Metrics scraping across API and backend subsystems |
| **Grafana** | `3000` | Grafana | Golden signals dashboard & telemetry visualization |
| **Jaeger** | `16686` / `4318` | Jaeger All-in-One | OpenTelemetry distributed trace collector and search UI |

---

## 3. Communication & Data Patterns

- **Synchronous Edge & Domain APIs**: REST JSON over HTTP routed through `/api/v1/`.
- **Asynchronous Task Queue**: Celery distributed task queue using Redis broker (`backend.workers.celery_app`).
- **Vector Search Engine**: PostgreSQL `pgvector` extension calculating cosine distance over 384-D log and runbook embeddings.
- **Observability Data**: OpenTelemetry distributed tracing via W3C headers and Prometheus metric scraping endpoints (`/metrics`).
