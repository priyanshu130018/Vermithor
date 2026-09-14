# Vermithor Local Setup Guide

This guide details the step-by-step installation and configuration process for setting up a local development environment for the Vermithor AI Production Incident Intelligence Platform.

---

## 1. Prerequisites

Before installing Vermithor, ensure the following software dependencies are installed on your machine:

- **Docker Desktop / Engine**: Version 24.0+ with Docker Compose v2.
- **Python**: Version 3.10 or higher.
- **Node.js**: Version 18.0 or higher with `npm` (v9+).
- **Git**: Latest release.
- **Ollama** (Optional for local LLM synthesis): Install from [ollama.com](https://ollama.com) and pull `llama3.2:3b`.

---

## 2. Clone Repository & Setup Environment

```bash
git clone https://github.com/vermithor/vermithor.git
cd Vermithor

# Create local environment configuration file from template
cp .env.example .env
```

---

## 3. Infrastructure Setup (Docker Compose)

Start the supporting database, cache, task queue, and observability containers:

```bash
docker compose up -d postgres redis prometheus grafana jaeger
```

Verify that all services are running and healthy:
```bash
docker compose ps
```

---

## 4. Python Environment & Dependencies

Create and activate a Python virtual environment:

### Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install backend dependencies:
```bash
pip install -r backend/requirements.txt
```

---

## 5. Database Schema & Vector Extension Setup

Run Alembic migrations to apply PostgreSQL schema definitions and enable the `pgvector` extension:

```bash
alembic upgrade head
```

---

## 6. Local LLM Setup (Ollama)

If you wish to run local AI incident synthesis and evidence validation:

1. Install and start Ollama on your machine.
2. Pull the default model (`llama3.2:3b`):
   ```bash
   ollama pull llama3.2:3b
   ```
3. Ensure Ollama is running on `http://localhost:11434`.

> **Note**: If Ollama is not running, Vermithor automatically falls back to deterministic rule-grounded summaries with `is_fallback: true`.

---

## 7. Running Backend Services

Start the Uvicorn FastAPI server and Celery background task worker in separate terminal windows:

### Terminal 1: FastAPI Modular Monolith
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2: Celery Worker
```bash
celery -A backend.workers.celery_app worker --loglevel=info --concurrency=2
```

---

## 8. Frontend Setup

In a third terminal window, install and launch the React dashboard:

```bash
cd frontend
npm install
npm run dev
```

Navigate to `http://localhost:5173` in your browser.
