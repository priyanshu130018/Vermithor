# Vermithor Troubleshooting & Operations Guide

This guide provides practical diagnostic procedures and solutions for common operational issues encountered while running Vermithor.

---

## 1. Diagnostic Matrix

| Symptom / Issue | Likely Root Cause | Solution |
|---|---|---|
| Database connection error (`psycopg.OperationalError`) | PostgreSQL container offline or credentials mismatch in `.env`. | Verify `docker compose ps postgres`. Check `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` in `.env`. |
| `pgvector` extension error (`type "vector" does not exist`) | Database initialized without vector extension. | Ensure PostgreSQL image is `pgvector/pgvector:pg16`. Run `alembic upgrade head`. |
| Celery tasks not processing | Celery worker offline or Redis connection refused. | Ensure Redis container is running (`docker compose up -d redis`). Start worker via `celery -A backend.workers.celery_app worker`. |
| Ollama connection error (`httpx.ConnectError`) | Local Ollama daemon not started or port 11434 blocked. | Start Ollama daemon. Test with `curl http://localhost:11434/api/tags`. Vermithor will fallback to rule-grounded mode (`is_fallback: true`). |
| Missing LLM model error (`model 'llama3.2:3b' not found`) | Ollama model weights not pulled locally. | Run `ollama pull llama3.2:3b`. |
| Embedding model download timeout | Slow network connection during initial `sentence-transformers` download. | Manually pull model or set `EMBEDDING_DEVICE=cpu`. Model is cached locally in `~/.cache/torch/sentence_transformers/`. |
| CORS errors in browser frontend | Mismatched API gateway or backend origin URLs. | Check `VITE_API_URL` in `frontend/.env` and `CORSMiddleware` in `backend/app/main.py`. |
| Alembic migration conflict | Uncommitted schema changes or out-of-sync revision history. | Inspect `alembic current`. Re-sync migrations using `alembic stamp head` or `alembic upgrade head`. |
| Port conflict (`Address already in use`) | Host port 8000, 8080, 5432, or 6379 occupied by another process. | Identify process with `netstat -ano | findstr <port>` (Windows) or `lsof -i :<port>` (Linux/macOS) and terminate it. |

---

## 2. Component Diagnostics Commands

### Database Health Check
```bash
docker exec -it vermithor-postgres pg_isready -U vermithor -d vermithor
```

### Redis Ping Test
```bash
docker exec -it vermithor-redis redis-cli ping
```

### Backend Readiness Check
```bash
curl -s http://localhost:8000/ready | jq
```

### Ollama Model Availability
```bash
curl -s http://localhost:11434/api/tags | jq
```

---

## 3. Recovery Procedures

### Resetting Local State & Re-migrating Database
To completely wipe local state and re-run migrations from scratch:
```bash
docker compose down -v
docker compose up -d postgres redis
alembic upgrade head
```
