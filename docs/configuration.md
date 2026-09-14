# Vermithor Configuration Reference

All settings for the Vermithor platform are centrally managed through Pydantic BaseSettings in `backend/app/common/config.py`. Environment variables can be passed via `.env` file or directly set in environment execution contexts.

---

## Environment Variables Directory

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `APP_ENV` | No | `development` | Runtime environment mode (`development`, `production`, `test`). |
| `LOG_LEVEL` | No | `INFO` | Standard logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `SERVICE_NAME` | No | `vermithor-backend` | Telemetry service identifier for tracing and metrics. |
| `PORT` | No | `8000` | Backend API listener port. |
| `HOST` | No | `0.0.0.0` | Backend API listener bind address. |
| `POSTGRES_USER` | Yes | `vermithor` | PostgreSQL database user account. |
| `POSTGRES_PASSWORD` | Yes | `vermithor_password` | PostgreSQL database password. |
| `POSTGRES_DB` | Yes | `vermithor` | PostgreSQL database name. |
| `POSTGRES_HOST` | No | `localhost` | PostgreSQL server hostname or IP. |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL server port. |
| `DATABASE_URL` | No | *Computed* | SQLAlchemy database URI (`postgresql+psycopg://...`). |
| `DB_POOL_SIZE` | No | `10` | SQLAlchemy engine connection pool size. |
| `DB_MAX_OVERFLOW` | No | `20` | SQLAlchemy maximum overflow connection count. |
| `DB_POOL_RECYCLE` | No | `1800` | Connection recycling timeout in seconds. |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection URL for caching and broker. |
| `CELERY_BROKER_URL` | No | `redis://localhost:6379/0` | Celery message broker Redis connection URL. |
| `CELERY_RESULT_BACKEND` | No | `redis://localhost:6379/0` | Celery task result backend Redis URL. |
| `JWT_SECRET` | Yes | `vermithor-dev-secret-key-32-chars-min` | HMAC-SHA256 secret key for Gateway JWT verification. |
| `JWT_ISSUER` | No | `vermithor` | Expected JWT issuer (`iss`) claim. |
| `JWT_AUDIENCE` | No | `vermithor-api` | Expected JWT audience (`aud`) claim. |
| `STATISTICAL_WARNING_Z` | No | `3.0` | Z-score threshold for warning metric anomalies. |
| `STATISTICAL_CRITICAL_Z` | No | `4.0` | Z-score threshold for critical metric anomalies. |
| `STATISTICAL_MIN_SAMPLES` | No | `5` | Minimum sample count required for Z-score calculation. |
| `ISOLATION_FOREST_CONTAMINATION` | No | `auto` | Contamination factor for Isolation Forest metric anomaly detection. |
| `ISOLATION_FOREST_MIN_SAMPLES` | No | `10` | Minimum sample count required to run Isolation Forest. |
| `ISOLATION_FOREST_RANDOM_STATE` | No | `42` | Random seed for Isolation Forest reproducibility. |
| `CORRELATION_WINDOW_SECONDS` | No | `900` | Temporal window (15 minutes) for incident signal correlation. |
| `STRONG_TIME_WINDOW_SECONDS` | No | `60` | High-confidence temporal correlation window (1 minute). |
| `MEDIUM_TIME_WINDOW_SECONDS` | No | `300` | Medium-confidence temporal correlation window (5 minutes). |
| `CORRELATION_THRESHOLD` | No | `0.60` | Minimum threshold score for correlating signals into incidents. |
| `AUTO_INCIDENT_THRESHOLD` | No | `0.85` | Threshold score to trigger auto-creation of incident state. |
| `WEIGHT_TIME` | No | `0.20` | Correlation scoring weight: temporal proximity. |
| `WEIGHT_SERVICE` | No | `0.20` | Correlation scoring weight: service boundary. |
| `WEIGHT_ENVIRONMENT` | No | `0.10` | Correlation scoring weight: deployment environment match. |
| `WEIGHT_TRACE` | No | `0.25` | Correlation scoring weight: distributed trace linkage. |
| `WEIGHT_SEVERITY` | No | `0.05` | Correlation scoring weight: signal severity magnitude. |
| `WEIGHT_METRIC` | No | `0.10` | Correlation scoring weight: metric anomaly overlap. |
| `WEIGHT_DEPLOYMENT` | No | `0.10` | Correlation scoring weight: deployment correlation. |
| `RCA_ANALYSIS_VERSION` | No | `1.0` | Version string for RCA engine scoring logic. |
| `RCA_WEIGHT_TEMPORAL` | No | `0.25` | RCA candidate weight: temporal precedence. |
| `RCA_WEIGHT_ANOMALY` | No | `0.20` | RCA candidate weight: metric anomaly severity. |
| `RCA_WEIGHT_CORRELATION` | No | `0.15` | RCA candidate weight: incident correlation density. |
| `RCA_WEIGHT_DOWNSTREAM_IMPACT` | No | `0.15` | RCA candidate weight: downstream service impact count. |
| `RCA_WEIGHT_DEPLOYMENT` | No | `0.10` | RCA candidate weight: recent deployment marker proximity. |
| `RCA_WEIGHT_SERVICE_ROLE` | No | `0.10` | RCA candidate weight: architectural service tier role. |
| `RCA_WEIGHT_SEVERITY` | No | `0.05` | RCA candidate weight: raw event severity. |
| `EMBEDDING_MODEL_NAME` | No | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model for 384-D dense vector log embeddings. |
| `EMBEDDING_DIMENSION` | No | `384` | Dense vector space embedding size. |
| `EMBEDDING_DEVICE` | No | `cpu` | PyTorch model execution target (`cpu`, `cuda`). |
| `HDBSCAN_MIN_CLUSTER_SIZE` | No | `2` | Minimum cluster size for HDBSCAN density clustering. |
| `HDBSCAN_MIN_SAMPLES` | No | `1` | Neighborhood sample density for HDBSCAN core points. |
| `HDBSCAN_CLUSTER_SELECTION_METHOD` | No | `eom` | Cluster selection algorithm (`eom`, `leaf`). |
| `HDBSCAN_METRIC` | No | `euclidean` | Distance metric for log cluster space evaluation. |
| `CLUSTER_WINDOW_SECONDS` | No | `300` | Log batching temporal window (5 minutes) for clustering. |
| `CLUSTER_MAX_REPRESENTATIVE_LOGS` | No | `3` | Maximum representative log templates extracted per cluster. |
| `MAX_CONTEXT_RESULTS` | No | `20` | Maximum vector RAG search candidate results. |
| `MAX_CONTEXT_CHARS` | No | `20000` | Character limit for RAG prompt context window. |
| `RETRIEVAL_WEIGHT_SEMANTIC` | No | `0.50` | RAG ranking weight: semantic cosine similarity. |
| `RETRIEVAL_WEIGHT_METADATA` | No | `0.20` | RAG ranking weight: service & environment metadata match. |
| `RETRIEVAL_WEIGHT_RECENCY` | No | `0.15` | RAG ranking weight: historical document recency. |
| `RETRIEVAL_WEIGHT_SOURCE` | No | `0.15` | RAG ranking weight: document source authority. |
| `LLM_PROVIDER` | No | `ollama` | LLM provider backend type (`ollama`). |
| `LLM_MODEL` | No | `llama3.2:3b` | Local Ollama model tag. |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Base HTTP REST API URL for Ollama inference. |
| `LLM_TIMEOUT_SECONDS` | No | `120` | Maximum HTTP timeout for LLM synthesis. |
| `LLM_FALLBACK_ENABLED` | No | `false` | Enable rule-grounded summary fallback on LLM failure. |
| `MAX_PROMPT_CHARS` | No | `30000` | Maximum character bound for LLM synthesis prompts. |
| `MAX_OUTPUT_TOKENS` | No | `2000` | Maximum token limit for LLM generation response. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | `http://localhost:4318` | OpenTelemetry OTLP HTTP trace collector endpoint. |
