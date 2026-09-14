# Vermithor Backend Architecture

The backend is engineered as a high-performance **FastAPI Modular Monolith** with separated domain modules under `backend/app/`, backed by SQLAlchemy 2.0, Pydantic v2, Alembic migrations, PostgreSQL (`pgvector`), Redis, and Celery task workers.

---

## 1. Directory Structure

```text
backend/
├── app/
│   ├── main.py                # FastAPI application entry point, lifespan, & router registration
│   ├── common/                # Unified config, database engine, telemetry, and base models
│   ├── anomaly/               # Metric anomaly detection domain (z-score + Isolation Forest)
│   ├── correlation/           # Signal correlation engine (temporal windows & topology weighting)
│   ├── incidents/              # Correlated incident state management & event linking
│   ├── ingestion/             # Telemetry intake, event schema validation, & async processing
│   ├── log_intelligence/      # Log masking, template extraction, MiniLM embeddings & HDBSCAN
│   ├── rca/                   # Multi-dimensional Root Cause Analysis engine (causal graph DAG)
│   ├── retrieval/             # Multi-source RAG knowledge retrieval (runbooks + incidents)
│   ├── summary/               # Ollama LLM synthesis & multi-point evidence validation
│   └── topology/              # Service topology DAG builder & dependency graph
│
├── alembic/                   # Alembic database migration scripts & environment
│   ├── env.py
│   └── versions/              # DDL schema revisions
│
├── workers/                   # Celery asynchronous task execution & background workers
│   ├── celery_app.py
│   └── tasks.py
│
├── tests/                     # Isolated Pytest test suite across all domain modules
│
├── Dockerfile                 # Unified container definition
├── requirements.txt           # Python dependencies
└── alembic.ini                # Alembic migration configuration
```

---

## 2. Standard Domain Module Layout

Every domain module under `backend/app/<domain>/` follows a clean modular design:

```text
backend/app/<domain>/
├── __init__.py
├── api/                       # Domain route controllers (FastAPI APIRouters)
├── db/                        # Domain ORM models & database repositories
├── schemas/                   # Pydantic input/output validation schemas
└── services/ / clients/       # Core domain business logic engines
```

---

## 3. Technology Stack & Runtime Configuration

- **Web Framework**: FastAPI running on Uvicorn (`backend.app.main:app`).
- **Database Engine**: SQLAlchemy 2.0 with PostgreSQL 16 (`pgvector` extension) and Alembic migrations.
- **Task Processing**: Celery asynchronous workers (`backend.workers.celery_app`).
- **AI & Analytics**: Scikit-Learn (HDBSCAN, Isolation Forest), Sentence-Transformers (`all-MiniLM-L6-v2`), NetworkX.
- **LLM Synthesis**: Ollama (`llama3.2:3b`) with deterministic grounded fallback when unavailable (`is_fallback: true`).
