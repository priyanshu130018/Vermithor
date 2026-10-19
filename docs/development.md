# Vermithor Developer Guide

This document details the local setup, developer workflows, testing strategies, configuration management, and troubleshooting steps for the **Vermithor** AI Production Incident Intelligence Platform.

---

## 1. Prerequisites & Tooling

Ensure the following tools are installed before setting up Vermithor:

| Tool | Minimum Version | Purpose |
|---|---|---|
| **Python** | `3.10+` (verified on `3.10` and `3.12`) | Backend Modular Monolith, Celery workers, and test runner. |
| **Node.js & npm** | Node `18.0+`, npm `9.0+` | React Vite dashboard development and frontend test suite. |
| **Git** | `2.30+` | Source control and version management. |
| **Docker & Docker Compose** | Docker `24.0+`, Compose `v2.20+` | Containerized development and supporting services (Redis, Jaeger, Prometheus, Grafana). |
| **Neon Account** | Neon Serverless PostgreSQL | Cloud PostgreSQL with pgvector extension (no local PostgreSQL container needed). |
| **Hugging Face Account (Optional)** | HF Inference API Token | Required for live LLM synthesis (`HF_TOKEN`). Fallback operates without a token. |

---

## 2. Repository Layout

```text
Vermithor/
├── .env.example               # Documented environment configuration template
├── docker-compose.yml         # Container stack orchestration (Gateway, Redis, Observability)
├── alembic.ini                # Root Alembic configuration for local workflows
│
├── backend/                   # FastAPI Modular Monolith
│   ├── alembic/               # Database migration environment and version revisions
│   │   ├── env.py             # SQLAlchemy URL resolver & migration engine
│   │   └── versions/          # DDL schema revisions (001_initial_schema.py)
│   ├── app/                   # Domain modules
│   │   ├── common/            # Config, database engine, base models, telemetry
│   │   ├── anomaly/           # Z-score & Isolation Forest metric detectors
│   │   ├── correlation/       # Temporal window and topology correlation
│   │   ├── incidents/         # Incident state machine & event linking
│   │   ├── ingestion/         # Telemetry intake & schema validation
│   │   ├── log_intelligence/  # Secret redaction, Drain templates, MiniLM embeddings, HDBSCAN
│   │   ├── rca/               # Causal DAG builder & root cause candidate scoring
│   │   ├── retrieval/         # Multi-source RAG context & pgvector search
│   │   ├── summary/           # Hugging Face LLM synthesis & evidence validation
│   │   └── topology/          # Service dependency topology DAG
│   ├── workers/               # Celery asynchronous task application (celery_app.py)
│   ├── tests/                 # Unit and domain integration test suite
│   ├── Dockerfile             # Multi-stage production container build
│   └── requirements.txt       # Production Python dependencies
│
├── frontend/                  # React 18 Single Page Application
│   ├── src/                   # React components, pages, custom hooks, and API clients
│   ├── vite.config.ts         # Vite build and Vitest configuration
│   ├── package.json           # Node.js dependencies
│   └── Dockerfile             # Multi-stage Nginx SPA container build
│
├── gateway/                   # Nginx Perimeter API Gateway & Reverse Proxy
│   ├── nginx.conf             # Upstream reverse proxy, tiered rate limiting, and security headers
│   └── Dockerfile             # Standard Nginx (nginx:alpine) container build
│
├── infrastructure/            # Deployment & Observability Configuration
│   ├── prometheus/            # Prometheus scrape configuration (prometheus.yml)
│   ├── grafana/               # Provisioned datasources and dashboards
│   └── helm/                  # Production Kubernetes Helm chart
│
├── evaluation/                # Quantitative benchmark evaluation framework
│   ├── evaluator.py           # Evaluation runner
│   └── scenarios/             # 7 deterministic incident YAML scenarios
│
└── tests/                     # System-level test suites (resilience, e2e)
```

---

## 3. Local Development Setup

### 3.1 Clone & Environment File Preparation
```bash
git clone https://github.com/vermithor/vermithor.git
cd Vermithor

# Create .env from template
cp .env.example .env
```

### 3.2 Python Environment Setup (Windows PowerShell)
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install backend dependencies
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

*(On Linux / macOS, activate via `source .venv/bin/activate`).*

### 3.3 Frontend Setup
```powershell
cd frontend
npm install
cd ..
```

---

## 4. Configuration & Environment Variables

Configure settings in `.env`. **Never commit `.env` or real passwords to version control.**

| Variable | Required | Default / Placeholder | Description |
|---|---|---|---|
| `APP_ENV` | No | `development` | Runtime environment (`development`, `production`). |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `DATABASE_URL` | **Yes** | `postgresql+psycopg://neondb_owner:<PWD>@ep-...-pooler.neon.tech/neondb?sslmode=require` | Neon pooled connection string for backend and workers. |
| `DATABASE_URL_UNPOOLED` | No | `postgresql+psycopg://neondb_owner:<PWD>@ep-....neon.tech/neondb?sslmode=require` | Optional direct unpooled Neon URI for Alembic DDL migrations. |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection URL for Celery broker and caching. |
| `CELERY_BROKER_URL` | No | `redis://localhost:6379/0` | Celery broker URL. |
| `CELERY_RESULT_BACKEND` | No | `redis://localhost:6379/0` | Celery result backend URL. |
| `JWT_SECRET` | **Yes** | `vermithor-dev-secret-key-32-chars-min` | HMAC-SHA256 secret for Gateway JWT validation. |
| `JWT_ISSUER` | No | `vermithor` | Expected token issuer (`iss`). |
| `JWT_AUDIENCE` | No | `vermithor-api` | Expected token audience (`aud`). |
| `VITE_API_BASE_URL` | No | `http://localhost:8080` | Gateway URL targeted by frontend client. |
| `EMBEDDING_PROVIDER` | No | `huggingface` | Vector embedding provider (`huggingface` for cloud, `mock` for offline testing). |
| `EMBEDDING_MODEL_NAME` | No | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model identifier (384-dimensional dense vectors). |
| `EMBEDDING_DIMENSION` | No | `384` | Vector dimension matching `pgvector` column. |
| `HF_EMBEDDING_BASE_URL` | No | `https://router.huggingface.co/hf-inference` | Hugging Face feature-extraction pipeline base URL. |
| `LLM_PROVIDER` | No | `huggingface` | LLM synthesis provider (`huggingface` or `ollama`). |
| `HF_TOKEN` | Optional | *(Empty)* | Hugging Face Bearer token (when `LLM_PROVIDER=huggingface`). |
| `HF_MODEL` | No | `meta-llama/Llama-3.1-8B-Instruct` | Model identifier for Hugging Face Inference Providers. |
| `HF_BASE_URL` | No | `https://router.huggingface.co/v1` | OpenAI-compatible router endpoint for Hugging Face. |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama endpoint (`http://host.docker.internal:11434` for Docker Compose). |
| `OLLAMA_MODEL` | No | `llama3.2` | Ollama model identifier (e.g., `llama3.2`, `llama3.1`, `mistral`). |
| `LLM_FALLBACK_ENABLED` | No | `true` | Enable deterministic grounded fallback when LLM is offline or credits exhausted. |
| `OTEL_EXPORTER_OTLP_ENDPOINT`| No | `http://localhost:4318` | Jaeger OTLP HTTP receiver endpoint. |

---

## 5. Neon PostgreSQL Configuration & Migrations

Vermithor uses Neon Serverless PostgreSQL with the `pgvector` extension. **A local PostgreSQL container is not required.**

### 5.1 Setting Connection Strings
Obtain connection strings from the [Neon Console](https://console.neon.tech) or using `npx neon connection-string`:
1. Copy the **Pooled connection** string into `DATABASE_URL` in `.env`.
2. Copy the **Direct / Unpooled connection** string into `DATABASE_URL_UNPOOLED` in `.env`.
3. Ensure `?sslmode=require` is present in the query string.

### 5.2 Verifying Database Connectivity
Verify direct connectivity to your Neon database using PowerShell:
```powershell
python -c "from backend.app.common.database import engine; from sqlalchemy import text; conn = engine.connect(); print('Connected to:', conn.execute(text('SELECT current_database(), version();')).fetchone()); conn.close()"
```

### 5.3 Applying Alembic Schema Migrations
Alembic manages DDL schemas and enables the `vector` extension:
```powershell
# Check current migration revision
alembic current

# Apply migrations to head
alembic upgrade head
```

### 5.4 Creating New Migrations
When modifying SQLAlchemy domain models under `backend/app/*/db/models.py`:
```powershell
# Generate automatic migration revision
alembic revision --autogenerate -m "Add new domain table"

# Review the generated file in backend/alembic/versions/
# Apply the revision
alembic upgrade head
```

---

## 6. Running Supporting Services (Docker)

Start the supporting Redis cache and observability stack locally:
```powershell
# Start Redis and Observability tools
docker compose up -d redis jaeger prometheus grafana
```

Verify service status:
```powershell
docker compose ps
```

---

## 7. Running Applications Locally

### 7.1 Start Backend (FastAPI)
```powershell
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
API docs available at `http://localhost:8000/docs`.

### 7.2 Start Celery Background Worker
```powershell
celery -A backend.workers.celery_app worker --loglevel=info --concurrency=2
```

### 7.3 Start Frontend Dashboard
```powershell
cd frontend
npm run dev
```
Dashboard available at `http://localhost:5173`.

### 7.4 Running Local Ollama for RCA Summaries
Ollama provides local, offline LLM synthesis without cloud API rate limits or credit quotas.

1. **Install Ollama**: Download from [ollama.com](https://ollama.com/download) for Windows/macOS/Linux.
2. **Pull the Model**:
   ```powershell
   ollama pull llama3.2
   ```
3. **Start Ollama Service**:
   ```powershell
   ollama serve
   ```
   *(Listens on `http://localhost:11434` by default)*.
4. **Configure Vermithor**:
   Set in `.env`:
   ```bash
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.2
   ```
   *Note for Docker Compose:* When running Vermithor in Docker, set `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

---

## 8. Testing & Static Validation

Execute tests and validation commands from the repository root:

### 8.1 Backend Test Suite (Pytest)
```powershell
# Run database config and migration tests
python -m pytest backend/tests/test_database_config.py backend/tests/test_migrations.py -v

# Run all backend unit and integration tests
python -m pytest backend/tests/ -v

# Run summary and RAG tests specifically
python -m pytest backend/tests/summary/ -v
```
*(Tests utilize SQLite in-memory databases configured in `backend/tests/conftest.py`, running without touching live remote databases).*

### 8.2 Gateway Security Tests
```powershell
python -m pytest gateway/tests/ -v
```
Validates JWT expiration, signature mismatch, missing claims, and clock skew tolerance.

### 8.3 System Resilience Tests
```powershell
python -m pytest tests/resilience/ -v
```

### 8.4 Evaluation Benchmark Framework
```powershell
python evaluation/evaluator.py
```
Evaluates RCA accuracy, anomaly F1, and schema validity across 7 deterministic incident scenarios. Generates report at `evaluation/report.md`.

### 8.5 Frontend Unit Tests
```powershell
cd frontend
npm run test
cd ..
```

### 8.6 Docker Compose Syntax Validation
```powershell
docker compose config --quiet
```

---

## 9. Troubleshooting Common Issues

| Problem | Root Cause | Solution |
|---|---|---|
| `psycopg.OperationalError: connection failed` | Network block or invalid Neon credentials in `.env`. | Verify `DATABASE_URL` in `.env`. Ensure `?sslmode=require` is present. Verify project status on [console.neon.tech](https://console.neon.tech). |
| `ModuleNotFoundError: No module named 'psycopg2'` | Driver scheme missing `+psycopg`. | Vermithor automatically converts `postgresql://` to `postgresql+psycopg://`. Ensure `backend/app/common/config.py` is up to date. |
| `type "vector" does not exist` | Migration has not been applied to Neon. | Run `alembic upgrade head`. Neon supports `pgvector` natively. |
| `HTTP 401 Unauthorized` on Gateway | Missing, expired, or invalidly signed JWT. | Ensure client passes `Authorization: Bearer <TOKEN>` signed with `JWT_SECRET`, issuer `vermithor`, and audience `vermithor-api`. |
| `HTTP 429 Too Many Requests` on Gateway | Exceeded rate limit ceiling. | Respect the `Retry-After: 5` header. Summary endpoint has a 2 req/s limit. |
| Hugging Face 401 / 429 Errors | Missing/invalid `HF_TOKEN` or free-tier rate limits. | Verify `HF_TOKEN` in `.env`. If exhausted, Vermithor automatically activates deterministic fallback (`is_fallback: true`). |
| Port Conflict (`Address already in use`) | Host ports (8000, 8080, 5173, 6379) bound by other processes. | Terminate process holding port (`netstat -ano \| findstr <PORT>` on Windows; `lsof -i :<PORT>` on Linux). |
| CORS Errors in Browser | Origin mismatch between Vite and Gateway. | Set `VITE_API_BASE_URL=http://localhost:8080` in `frontend/.env`. |
