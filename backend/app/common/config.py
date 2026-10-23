from functools import lru_cache
from typing import Optional, Union, Dict, Any, List
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


def normalize_database_url(url: Optional[str]) -> Optional[str]:
    """Normalize database connection string for SQLAlchemy 2.0 and psycopg v3.

    Translates legacy schemes ('postgres://', 'postgresql://', 'postgresql+psycopg2://')
    to 'postgresql+psycopg://' so that the installed psycopg v3 driver is loaded,
    while preserving all credentials, hostnames, ports, and SSL query parameters.
    """
    if not url:
        return url
    cleaned = url.strip().strip("'\"")
    if cleaned.startswith("postgres://"):
        return "postgresql+psycopg://" + cleaned[len("postgres://"):]
    elif cleaned.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql+psycopg2://"):]
    elif cleaned.startswith("postgresql://") and not cleaned.startswith("postgresql+"):
        return "postgresql+psycopg://" + cleaned[len("postgresql://"):]
    return cleaned


def get_safe_db_diagnostic(url: Optional[str]) -> Dict[str, Any]:
    """Extract safe database connection diagnostics without exposing credentials.

    Reports only the URL hostname, username, database name, pooled/unpooled mode,
    and whether a password is present. Never prints or returns the password,
    full URL, or query parameters.
    """
    if not url:
        return {
            "hostname": None,
            "username": None,
            "database": None,
            "mode": "unknown",
            "password_present": False,
        }
    try:
        norm = normalize_database_url(url)
        parsed = make_url(norm)
        hostname = parsed.host
        username = parsed.username
        database = parsed.database
        password_present = bool(parsed.password)
        is_pooled = bool(hostname and ("-pooler" in hostname or parsed.port == 6543))
        mode = "pooled" if is_pooled else "unpooled"
        return {
            "hostname": hostname,
            "username": username,
            "database": database,
            "mode": mode,
            "password_present": password_present,
        }
    except Exception:
        return {
            "hostname": "unparseable",
            "username": "unparseable",
            "database": "unparseable",
            "mode": "unknown",
            "password_present": False,
        }



class Settings(BaseSettings):
    """Unified application settings for the Vermithor Modular Monolith."""

    # Application & Environment
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "vermithor-backend"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Neon Serverless PostgreSQL & pgvector Database Settings
    DATABASE_URL: Optional[str] = None
    DATABASE_URL_UNPOOLED: Optional[str] = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_TIMEOUT: int = 15

    # Redis Cache & Celery Task Queue
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Inbound API Rate Limiting Configuration
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_INVESTIGATIONS_PER_MIN: int = 15
    RATE_LIMIT_REPAIRS_PER_MIN: int = 15
    RATE_LIMIT_REPOSITORIES_PER_MIN: int = 20
    RATE_LIMIT_DEFAULT_PER_MIN: int = 60

    # Gateway JWT Security Boundary
    JWT_SECRET: str = "vermithor-dev-secret-key-32-chars-min"
    JWT_ISSUER: str = "vermithor"
    JWT_AUDIENCE: str = "vermithor-api"
    ENABLE_DEV_AUTH: bool = True
    ALLOWED_ORGS: Optional[Union[List[str], str]] = Field(
        default=None,
        description="Explicit allowlist of authorized organization IDs. If None, defaults to environment-specific allowlist (strictly internal/vermithor in production; test fixtures allowed in dev/test).",
    )

    # Anomaly Detection Parameters
    STATISTICAL_WARNING_Z: float = 3.0
    STATISTICAL_CRITICAL_Z: float = 4.0
    STATISTICAL_MIN_SAMPLES: int = 5
    ISOLATION_FOREST_CONTAMINATION: Union[float, str] = "auto"
    ISOLATION_FOREST_MIN_SAMPLES: int = 10
    ISOLATION_FOREST_RANDOM_STATE: int = 42

    # Correlation Parameters & Weights
    CORRELATION_WINDOW_SECONDS: int = 900
    STRONG_TIME_WINDOW_SECONDS: int = 60
    MEDIUM_TIME_WINDOW_SECONDS: int = 300
    CORRELATION_THRESHOLD: float = 0.60
    AUTO_INCIDENT_THRESHOLD: float = 0.85
    WEIGHT_TIME: float = 0.20
    WEIGHT_SERVICE: float = 0.20
    WEIGHT_ENVIRONMENT: float = 0.10
    WEIGHT_TRACE: float = 0.25
    WEIGHT_SEVERITY: float = 0.05
    WEIGHT_METRIC: float = 0.10
    WEIGHT_DEPLOYMENT: float = 0.10

    # RCA Parameters & Weights
    RCA_ANALYSIS_VERSION: str = "1.0"
    RCA_WEIGHT_TEMPORAL: float = 0.25
    RCA_WEIGHT_ANOMALY: float = 0.20
    RCA_WEIGHT_CORRELATION: float = 0.15
    RCA_WEIGHT_DOWNSTREAM_IMPACT: float = 0.15
    RCA_WEIGHT_DEPLOYMENT: float = 0.10
    RCA_WEIGHT_SERVICE_ROLE: float = 0.10
    RCA_WEIGHT_SEVERITY: float = 0.05

    # Log Intelligence & Cloud Vector Embeddings
    EMBEDDING_PROVIDER: str = "huggingface"
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_MODEL: Optional[str] = None
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_DEVICE: str = "cpu"
    HF_EMBEDDING_BASE_URL: str = "https://router.huggingface.co/hf-inference"
    HF_EMBEDDING_URL: Optional[str] = None
    EMBEDDING_TIMEOUT_SECONDS: int = Field(30, ge=1)
    EMBEDDING_MAX_RETRIES: int = Field(2, ge=0)
    EMBEDDING_BATCH_SIZE: int = Field(32, ge=1)
    MODEL_VERSION: str = "1.0"
    DEFAULT_TOP_K: int = Field(5, ge=1)
    MAX_TOP_K: int = Field(50, ge=1)
    MIN_SIMILARITY: float = Field(0.0, ge=-1.0, le=1.0)

    # Log Clustering & HDBSCAN Parameters
    HDBSCAN_MIN_CLUSTER_SIZE: int = Field(2, ge=2, description="Minimum size of clusters for HDBSCAN")
    HDBSCAN_MIN_SAMPLES: Optional[int] = Field(1, ge=1, description="Number of samples in a neighborhood for a core point")
    HDBSCAN_CLUSTER_SELECTION_METHOD: str = Field("eom", description="Cluster selection method ('eom' or 'leaf')")
    HDBSCAN_METRIC: str = Field("euclidean", description="Distance metric for HDBSCAN clustering")
    CLUSTER_WINDOW_SECONDS: int = Field(300, ge=10, description="Time window in seconds for log clustering batches")
    CLUSTER_MAX_REPRESENTATIVE_LOGS: int = Field(3, ge=1, description="Number of representative logs per cluster")

    # Retrieval / RAG Parameters
    MAX_CONTEXT_RESULTS: int = Field(20, ge=1)
    MAX_CONTEXT_CHARS: int = Field(20000, ge=100)
    RETRIEVAL_WEIGHT_SEMANTIC: float = 0.50
    RETRIEVAL_WEIGHT_METADATA: float = 0.20
    RETRIEVAL_WEIGHT_RECENCY: float = 0.15
    RETRIEVAL_WEIGHT_SOURCE: float = 0.15

    # Summary & LLM Synthesis (Cloud-Only Hugging Face Inference Providers Backend)
    LLM_PROVIDER: str = "huggingface"
    HF_TOKEN: Optional[str] = None
    HF_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"
    HF_BASE_URL: str = "https://router.huggingface.co/v1"

    # Multi-Model Task-Specific Cloud Routing
    HF_INVESTIGATION_MODEL: str = Field(
        "meta-llama/Llama-3.1-8B-Instruct",
        description="Configurable cloud model ID for investigation and root-cause analysis",
    )
    HF_SUMMARY_MODEL: str = Field(
        "meta-llama/Llama-3.1-8B-Instruct",
        description="Configurable cloud model ID for incident summary and postmortem generation",
    )
    HF_REVIEW_MODEL: str = Field(
        "meta-llama/Llama-3.1-8B-Instruct",
        description="Configurable cloud model ID for report review and citation verification",
    )

    # Deprecated legacy local options (retained for backward compatibility only)
    OLLAMA_BASE_URL: Optional[str] = Field("http://localhost:11434", description="[Deprecated] Legacy Ollama base URL")
    OLLAMA_MODEL: Optional[str] = Field("llama3.2", description="[Deprecated] Legacy Ollama model name")

    SUMMARY_VERSION: str = "1.0"
    LLM_TIMEOUT_SECONDS: int = Field(120, ge=5)
    LLM_FALLBACK_ENABLED: bool = Field(True, description="Enable deterministic grounded fallback when cloud LLM is unavailable or credits exhausted")
    MAX_PROMPT_CHARS: int = Field(30000, ge=1000)
    MAX_OUTPUT_TOKENS: int = Field(2000, ge=100)

    def get_model_for_task(self, task: Optional[str] = None) -> str:
        """Resolve the configured cloud model identifier for a specific intelligence task."""
        if not task:
            return self.HF_MODEL
        t = str(task).lower().strip()
        if t in ("investigation", "rca", "hypothesis_evaluation", "root_cause", "hypotheses"):
            return self.HF_INVESTIGATION_MODEL or self.HF_MODEL
        if t in ("summary", "postmortem", "incident_summary", "summaries"):
            return self.HF_SUMMARY_MODEL or self.HF_MODEL
        if t in ("review", "report_review", "evaluation_review", "patch_review"):
            return self.HF_REVIEW_MODEL or self.HF_MODEL
        return self.HF_MODEL

    # Observability & Distributed Tracing
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = "http://localhost:4318"
    PROMETHEUS_URL: str = Field("http://localhost:9090", description="Prometheus server base URL")
    JAEGER_QUERY_URL: str = Field("http://localhost:16686", description="Jaeger Query API base URL")
    OBSERVABILITY_REQUEST_TIMEOUT: float = Field(5.0, ge=0.5, le=30.0, description="Timeout in seconds for external observability queries")

    # Code Repair Agent & Sandbox Parameters
    AGENT_REPAIR_CONFIDENCE_THRESHOLD: float = Field(
        0.50,
        ge=0.0,
        le=1.0,
        description="Minimum investigation confidence score required to justify inspecting code and proposing repairs",
    )
    AGENT_REPAIR_MAX_PATCH_LINES: int = Field(
        150,
        ge=10,
        le=1000,
        description="Maximum lines of unified diff allowed in an AI-generated repair patch",
    )
    AGENT_REPAIR_MAX_CHANGED_FILES: int = Field(
        3,
        ge=1,
        le=10,
        description="Maximum number of files allowed to be altered by an AI repair patch",
    )
    AGENT_REPAIR_SANDBOX_TIMEOUT_SECONDS: float = Field(
        30.0,
        ge=5.0,
        le=120.0,
        description="Maximum execution timeout in seconds for isolated test execution in sandbox",
    )
    AGENT_REPAIR_ALLOWED_ROLES: List[str] = Field(
        default_factory=lambda: ["sre", "sre_lead", "admin", "lead_engineer", "maintainer"],
        description="Authorized roles permitted to review and approve code repairs",
    )
    # Rate Limiting Configuration
    RATE_LIMIT_ENABLED: bool = Field(True, description="Enable sliding-window ingress rate limiting")
    RATE_LIMIT_WORKER_PROCESS_COUNT: int = Field(1, ge=1, description="Estimated Uvicorn worker process count for degraded-mode quota partitioning")
    RATE_LIMIT_DEGRADED_QUOTA_BOUNDED: bool = Field(True, description="When Redis is unavailable, divide per-process in-memory quota by worker process count to prevent quota multiplication")
    TRUST_FORWARDED_HEADERS: bool = Field(False, description="Whether to trust X-Forwarded-For headers for unauthenticated client IP resolution")
    # Optional internal fallback URLs (for backwards compatibility if queried)
    INCIDENT_SERVICE_URL: str = "http://localhost:8000"
    CORRELATION_SERVICE_URL: str = "http://localhost:8000"
    RCA_SERVICE_URL: str = "http://localhost:8000"
    LOG_INTELLIGENCE_SERVICE_URL: str = "http://localhost:8000"
    RETRIEVAL_SERVICE_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_weights(self) -> "Settings":
        if self.DATABASE_URL and self.DATABASE_URL.strip():
            self.DATABASE_URL = normalize_database_url(self.DATABASE_URL)
        else:
            self.DATABASE_URL = normalize_database_url(
                "postgresql+psycopg://neondb_owner:your_neon_password@ep-curly-mode-b4ilila7-pooler.c-6.us-east-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
            )

        if self.DATABASE_URL_UNPOOLED and self.DATABASE_URL_UNPOOLED.strip():
            self.DATABASE_URL_UNPOOLED = normalize_database_url(self.DATABASE_URL_UNPOOLED)

        if self.EMBEDDING_MODEL and self.EMBEDDING_MODEL.strip():
            self.EMBEDDING_MODEL_NAME = self.EMBEDDING_MODEL.strip()

        # Validate correlation weights
        corr_total = (
            self.WEIGHT_TIME
            + self.WEIGHT_SERVICE
            + self.WEIGHT_ENVIRONMENT
            + self.WEIGHT_TRACE
            + self.WEIGHT_SEVERITY
            + self.WEIGHT_METRIC
            + self.WEIGHT_DEPLOYMENT
        )
        if abs(corr_total - 1.0) > 0.01:
            raise ValueError(f"Correlation weights must sum to 1.00 (got {corr_total:.2f})")

        # Validate RCA weights
        rca_total = (
            self.RCA_WEIGHT_TEMPORAL
            + self.RCA_WEIGHT_ANOMALY
            + self.RCA_WEIGHT_CORRELATION
            + self.RCA_WEIGHT_DOWNSTREAM_IMPACT
            + self.RCA_WEIGHT_DEPLOYMENT
            + self.RCA_WEIGHT_SERVICE_ROLE
            + self.RCA_WEIGHT_SEVERITY
        )
        if abs(rca_total - 1.0) > 0.01:
            raise ValueError(f"RCA weights must sum to 1.00 (got {rca_total:.2f})")

        # Validate retrieval weights
        ret_total = (
            self.RETRIEVAL_WEIGHT_SEMANTIC
            + self.RETRIEVAL_WEIGHT_METADATA
            + self.RETRIEVAL_WEIGHT_RECENCY
            + self.RETRIEVAL_WEIGHT_SOURCE
        )
        if abs(ret_total - 1.0) > 0.01:
            raise ValueError(f"Retrieval weights must sum to 1.00 (got {ret_total:.2f})")

        return self


@lru_cache()
def get_settings() -> Settings:
    """Return cached singleton instance of Settings."""
    return Settings()


if __name__ == "__main__":
    import os

    settings = get_settings()
    diag_pooled = get_safe_db_diagnostic(os.getenv("DATABASE_URL") or settings.DATABASE_URL)
    diag_unpooled = get_safe_db_diagnostic(os.getenv("DATABASE_URL_UNPOOLED") or settings.DATABASE_URL_UNPOOLED)

    print("=== Vermithor Database Safe Diagnostic (No Secrets) ===")
    print(
        f"DATABASE_URL:          hostname={diag_pooled['hostname']}, "
        f"username={diag_pooled['username']}, database={diag_pooled['database']}, "
        f"mode={diag_pooled['mode']}, password_present={diag_pooled['password_present']}"
    )
    print(
        f"DATABASE_URL_UNPOOLED: hostname={diag_unpooled['hostname']}, "
        f"username={diag_unpooled['username']}, database={diag_unpooled['database']}, "
        f"mode={diag_unpooled['mode']}, password_present={diag_unpooled['password_present']}"
    )

