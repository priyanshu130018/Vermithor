# Vermithor Developer Guide

This document provides developer guidelines for extending, modifying, and contributing to the Vermithor AI Production Incident Intelligence Platform.

---

## 1. Codebase Architecture & Conventions

Vermithor follows a **FastAPI Modular Monolith** pattern. Each functional domain resides in `backend/app/<domain_name>/`.

### Standard Domain Directory Structure
```text
backend/app/<domain>/
├── __init__.py
├── api/          # FastAPI APIRouter endpoints & HTTP controllers
├── db/           # SQLAlchemy ORM models & database queries
├── schemas/      # Pydantic request/response validation models
└── services/     # Core domain business logic, algorithms, & calculators
```

---

## 2. Adding a New Domain Module

To add a new domain module to the Vermithor backend:

1. **Create Module Directory**:
   Create `backend/app/new_domain/` with `api/`, `db/`, `schemas/`, and `services/` subdirectories.

2. **Define Database Models**:
   Add SQLAlchemy ORM models in `backend/app/new_domain/db/models.py`. Import them in `backend/app/main.py` so Alembic discovers metadata.

3. **Define Pydantic Schemas**:
   Create request and response schemas in `backend/app/new_domain/schemas/`.

4. **Implement Service Logic**:
   Write reusable business logic in `backend/app/new_domain/services/`.

5. **Expose APIRouter**:
   Define routes in `backend/app/new_domain/api/router.py` and register the router in `backend/app/main.py`:
   ```python
   from backend.app.new_domain.api.router import router as new_domain_router
   app.include_router(new_domain_router, prefix="/api/v1")
   ```

---

## 3. Database Migrations (Alembic)

Database schema changes are tracked via Alembic under `backend/alembic/`.

### Creating a Migration:
```bash
# Generate automatic migration revision
alembic revision --autogenerate -m "Add new domain table"
```

### Applying Migrations:
```bash
# Upgrade database to latest schema revision
alembic upgrade head
```

### Downgrading Migrations:
```bash
# Rollback one migration revision
alembic downgrade -1
```

---

## 4. Running Tests & Quality Verification

Always execute test suites prior to submitting code changes:

```bash
# Run unit and integration tests
python -m pytest backend/tests/ -v

# Run benchmark evaluator tests
python -m pytest backend/tests/evaluation/ -v
```

---

## 5. Adding Runbooks & Evaluation Scenarios

### Adding a Runbook:
Runbooks are stored in the PostgreSQL database with vector embeddings. Insert runbooks via `POST /api/v1/runbooks` or seed scripts.

### Adding an Evaluation Scenario:
Evaluation scenarios are stored as YAML files in `evaluation/scenarios/`. Format:
```yaml
name: "example_failure"
description: "Example service failure scenario"
telemetry:
  logs: [...]
  metrics: [...]
expected:
  root_cause: "target-service"
  min_confidence: 0.80
```
