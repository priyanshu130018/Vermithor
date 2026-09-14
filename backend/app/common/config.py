from functools import lru_cache
from typing import Optional, Union
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Unified application settings for the Vermithor Modular Monolith."""

    # Application & Environment
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    SERVICE_NAME: str = "vermithor-backend"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # PostgreSQL Database & pgvector
    POSTGRES_USER: str = "vermithor"
    POSTGRES_PASSWORD: str = "vermithor_password"
    POSTGRES_DB: str = "vermithor"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800

    # Redis Cache & Celery Task Queue
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Gateway JWT Security Boundary
    JWT_SECRET: str = "vermithor-dev-secret-key-32-chars-min"
    JWT_ISSUER: str = "vermithor"
    JWT_AUDIENCE: str = "vermithor-api"

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

    # Log Intelligence & Vector Embeddings
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_DEVICE: str = "cpu"
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

    # Summary & LLM Synthesis
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "llama3.2:3b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    SUMMARY_VERSION: str = "1.0"
    LLM_TIMEOUT_SECONDS: int = Field(120, ge=5)
    LLM_FALLBACK_ENABLED: bool = False
    MAX_PROMPT_CHARS: int = Field(30000, ge=1000)
    MAX_OUTPUT_TOKENS: int = Field(2000, ge=100)

    # Observability & Distributed Tracing
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = "http://localhost:4318"

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
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

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
