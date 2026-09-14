# Vermithor Testing Guide

This document outlines the testing strategy, test suites, and commands for verifying the Vermithor platform.

---

## 1. Test Architecture & Directory Layout

The repository contains multi-layered test suites:

```text
Vermithor/
├── backend/tests/        # Backend unit, integration, & domain module tests
│   ├── anomaly/          # Tests for z-score & Isolation Forest detectors
│   ├── correlation/      # Tests for temporal & topology incident correlation
│   ├── evaluation/       # Tests for evaluation runner framework
│   ├── incidents/        # Tests for incident state machine & CRUD APIs
│   ├── ingestion/        # Tests for telemetry intake & Celery tasks
│   ├── log_intelligence/ # Tests for MiniLM vector embeddings & HDBSCAN
│   ├── rca/              # Tests for NetworkX causal graph RCA scoring
│   ├── retrieval/        # Tests for RAG vector pgvector search
│   └── summary/          # Tests for LLM synthesis & evidence validation
├── gateway/tests/        # Nginx & Lua JWT authentication boundary tests
└── tests/                # System-level test suites
    ├── e2e/              # End-to-end integration workflows
    ├── observability/    # Prometheus & OpenTelemetry tracing tests
    └── resilience/       # Chaos & fault tolerance verification scripts
```

---

## 2. Test Execution Commands

### Running Backend Unit & Domain Tests
```bash
python -m pytest backend/tests/ -v
```

### Running Gateway JWT Security Tests
```bash
python -m pytest gateway/tests/ -v
```

### Running System Resilience Tests
```bash
python -m pytest tests/resilience/ -v
```

### Running Evaluation Benchmark Suite
```bash
python evaluation/evaluator.py
```

---

## 3. Test Fixtures & In-Memory Databases

Backend tests utilize SQLite in-memory databases (`sqlite:///:memory:`) via SQLAlchemy fixtures configured in `backend/tests/conftest.py`. This ensures fast execution without requiring a live PostgreSQL instance.

---

## 4. CI/CD Automated Verification

Automated GitHub Actions workflows in `.github/workflows/` execute `pytest` across all pull requests to enforce regression prevention.
