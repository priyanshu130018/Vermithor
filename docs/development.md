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
| LLM_PROVIDER | No | huggingface | Cloud LLM backend provider (huggingface). |
| HF_TOKEN | Optional | *(Empty)* | Hugging Face Bearer token for Inference Providers. |
| HF_BASE_URL | No | https://router.huggingface.co/v1 | OpenAI-compatible router endpoint for Hugging Face Inference Providers. |
| HF_INVESTIGATION_MODEL | No | meta-llama/Llama-3.1-8B-Instruct | Configured cloud model for investigation and root-cause analysis. |
| HF_SUMMARY_MODEL | No | meta-llama/Llama-3.1-8B-Instruct | Configured cloud model for summary and postmortem generation. |
| HF_REVIEW_MODEL | No | meta-llama/Llama-3.1-8B-Instruct | Configured cloud model for report review and citation verification. |
| LLM_FALLBACK_ENABLED | No | 	rue | Enable deterministic grounded fallback when cloud LLM is offline or credits exhausted. |
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

### 7.4 Cloud Multi-Model Routing Configuration (Hugging Face Inference Providers)
Vermithor connects to cloud Hugging Face Inference Providers router (https://router.huggingface.co/v1) with task-specific model routing.

1. **Obtain API Token & Check Credits**:
   - Create an API token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
   - Ensure the account has active credits or a PRO subscription at [huggingface.co/settings/billing](https://huggingface.co/settings/billing).

2. **Configure Multi-Model Routing in .env**:
   `ash
   LLM_PROVIDER=huggingface
   HF_TOKEN=hf_your_actual_token_here
   HF_BASE_URL=https://router.huggingface.co/v1

   # Task-Specific Cloud Model Routing (configurable per intelligence task)
   HF_INVESTIGATION_MODEL=meta-llama/Llama-3.1-8B-Instruct
   HF_SUMMARY_MODEL=meta-llama/Llama-3.1-8B-Instruct
   HF_REVIEW_MODEL=meta-llama/Llama-3.1-8B-Instruct
   LLM_FALLBACK_ENABLED=true
   `

3. **Grounded Deterministic Fallback**:
   When cloud credits are exhausted (HTTP 402) or provider is unreachable, Vermithor automatically routes to deterministic grounded rules without hallucination. All fallback responses are explicitly labeled as deterministic-rules (non-LLM).
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

### 8.5 Frontend Unit & Integration Tests
```powershell
cd frontend
npm test
cd ..
```
Runs Vitest across 9 test suites including `InvestigationPanel.test.tsx` and `CodeRepairPanel.test.tsx` (21 tests).

### 8.6 Frontend TypeScript Type Check & Production Build
```powershell
cd frontend
npm run build
cd ..
```
Compiles TypeScript with 0 errors and generates production bundle via Vite.

### 8.7 LangGraph AI Agent Test Suites
```powershell
# Run all LangGraph AI agent unit and security tests (61 tests)
python -m pytest backend/tests/agent/ -v

# Run the complete end-to-end incident-to-repair user journey test suite (3 tests)
python -m pytest backend/tests/test_end_to_end_journey.py -v
```
Validates investigation evidence gathering, hypothesis evaluation, code repair generation, isolated sandbox validation (4/4 tests pass), patch hashing, stale patch rejection, RBAC authorization, and tenant isolation.

### 8.8 End-to-End Workflow & Demo Verification
```powershell
# Run the synthetic incident INC-2026-1042 pipeline runner
python scripts/demo/synthetic-incidents/run_incident_1042.py

# Run the AI Code Repair interactive demo CLI
python backend/scripts/run_repair_demo.py
```

### 8.9 Docker Compose Syntax Validation
```powershell
docker compose config --quiet
```

### 8.10 Controlled Pilot & Read-Only Repository Testing
```powershell
# Run the complete controlled pilot and repository isolation test suite (15 tests)
python -m pytest backend/tests/agent/test_pilot_repository_isolation.py -v

# Run all 76 LangGraph agent investigation, repair, and pilot isolation tests
python -m pytest backend/tests/agent/ -v
```
Validates repository connection under least privilege (`contents: read`, `metadata: read`), multi-tenant isolation, directory traversal/SSRF prevention, revocation gating, read-only write protection, rate limit resilience, and full traceability.
See [Controlled Pilot & Read-Only Repository Setup Guide](file:///docs/pilot_setup.md) for step-by-step setup details.

### 8.11 Customer Pilot Onboarding, Telemetry Verification & Data Governance Tests
`powershell
# Run the complete pilot onboarding, least-privilege telemetry, and governance test suite (15 tests)
python -m pytest backend/tests/agent/test_pilot_onboarding_and_readiness.py -v

# Run the frontend Pilot Readiness and Onboarding component tests
npm --prefix frontend test -- PilotReadiness
`
Validates:
- Guided 8-milestone onboarding workflow state machine.
- Least-privilege telemetry integration: SSRF protection, loopback/cloud-metadata blocking, and 2MB response size limits.
- The 5 explicit integration states: NOT_CONFIGURED, CONFIGURED_UNVERIFIED, VERIFIED, DEGRADED, REVOKED.
- Truthful provenance labeling: distinguishes LIVE_CUSTOMER_TELEMETRY from SANITIZED_REPLAY_FIXTURE.
- Multi-tenant boundary isolation across all pilot readiness endpoints.
- Role-based administrative gating (viewer rejected with 403).
- Secret masking and credential redaction before persistence.
- Telemetry collection kill-switch (collection_enabled: false) and investigation pause (investigations_paused: true).
- Cascading organization data purge across PostgreSQL, Redis cache, and background task queues.

---


## 9. Troubleshooting Common Issues

| Problem | Root Cause | Solution |
|---|---|---|
| `psycopg.OperationalError: connection failed` | Network block or invalid Neon credentials in `.env`. | Verify `DATABASE_URL` in `.env`. Ensure `?sslmode=require` is present. Verify project status on [console.neon.tech](https://console.neon.tech). |
| `ModuleNotFoundError: No module named 'psycopg2'` | Driver scheme missing `+psycopg`. | Vermithor automatically converts `postgresql://` to `postgresql+psycopg://`. Ensure `backend/app/common/config.py` is up to date. |
| `type "vector" does not exist` | Migration has not been applied to Neon. | Run `alembic upgrade head`. Neon supports `pgvector` natively. |
| `HTTP 401 Unauthorized` on Gateway or Backend | Missing, expired, or invalidly signed JWT. | Ensure client passes `Authorization: Bearer <TOKEN>` signed with `JWT_SECRET`, issuer `vermithor`, and audience `vermithor-api`. |
| `HTTP 403 Forbidden: Organization ... not authorized` | JWT `org_id` claim does not belong to authorized tenants list. | Use an authorized tenant (`vermithor`, `internal`, `local`, `default`, `org_default`) or configure tenant mapping. |
| `HTTP 403 Forbidden: Role ... is not authorized to approve code repairs` | User role lacks approval privileges. | Code repair approval requires `sre`, `sre_lead`, `admin`, or `lead_engineer` role in the JWT claims. |
| `HTTP 409 Conflict: Stale patch hash` | The patch has changed or reviewer specified an outdated patch hash. | Refresh the repair artifact (`GET /api/v1/agent/repairs/{id}`) to obtain the latest `patch_hash` before approving. |
| `HTTP 429 Too Many Requests` on Gateway | Exceeded rate limit ceiling. | Respect the `Retry-After: 5` header. Summary endpoint has a 2 req/s limit. |
| Hugging Face 401 / 402 / 429 / 5xx | Missing/invalid HF_TOKEN, credit exhaustion, or cloud provider offline. | Vermithor automatically activates deterministic grounded fallback (is_fallback: true, model: deterministic-rules (non-LLM)). Synthesis operates without hallucination or network dependencies. |
| Port Conflict (`Address already in use`) | Host ports (8000, 8080, 5173, 6379) bound by other processes. | Terminate process holding port (`netstat -ano \| findstr <PORT>` on Windows; `lsof -i :<PORT>` on Linux). |
| CORS Errors in Browser | Origin mismatch between Vite and Gateway. | Set `VITE_API_BASE_URL=http://localhost:8080` in `frontend/.env`. |

