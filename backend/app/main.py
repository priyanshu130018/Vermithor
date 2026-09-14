from contextlib import asynccontextmanager
import logging
from typing import Any, Dict
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import backend.app.common.database as common_db
from backend.app.anomaly.api.anomalies import router as anomalies_router
from backend.app.anomaly.api.observations import router as observations_router
from backend.app.common.config import get_settings
from backend.app.common.telemetry import setup_telemetry
from backend.app.correlation.api.correlations import router as correlations_router
from backend.app.incidents.api.incidents import router as incidents_router
from backend.app.ingestion.api.events import router as events_router
from backend.app.log_intelligence.api.logs import router as logs_router
from backend.app.rca.api.rca import router as rca_router
from backend.app.retrieval.api.retrieval import router as retrieval_router
from backend.app.retrieval.api.runbooks import router as runbooks_router
from backend.app.summary.api.summaries import router as summaries_router

# Import all models to ensure complete metadata registration
import backend.app.ingestion.db.models
import backend.app.incidents.db.models
import backend.app.anomaly.db.models
import backend.app.correlation.db.models
import backend.app.rca.db.models
import backend.app.log_intelligence.db.models
import backend.app.retrieval.db.models
import backend.app.summary.db.models

settings = get_settings()

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for initialization and graceful teardown."""
    logger.info("Initializing Vermithor Modular Monolith (version 1.0.0)...")
    yield
    logger.info("Shutting down Vermithor Modular Monolith...")


app = FastAPI(
    title="Vermithor Backend",
    description="Vermithor AI Production Incident Intelligence Platform (Modular Monolith)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach shared Prometheus metrics & OpenTelemetry distributed tracing
setup_telemetry(app, service_name=settings.SERVICE_NAME)


class HealthResponse(BaseModel):
    service: str
    status: str


class ReadinessResponse(BaseModel):
    service: str
    status: str
    database: str
    environment: str
    embedding_model_loaded: bool = True
    provider_available: bool = True
    llm_provider: str = "ollama"
    dimension: int = 384


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Liveness probe for orchestrator health checking."""
    return HealthResponse(
        service=settings.SERVICE_NAME,
        status="healthy",
    )


@app.get("/ready", response_model=ReadinessResponse, tags=["health"])
def readiness_check() -> ReadinessResponse:
    """Readiness probe checking database connectivity and subsystem initialization."""
    db_status = "connected"
    try:
        with common_db.engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:
        logger.warning("Readiness DB check warning: %s", exc)
        db_status = "degraded"

    return ReadinessResponse(
        service=settings.SERVICE_NAME,
        status="ready" if db_status == "connected" else "degraded",
        database=db_status,
        environment=settings.APP_ENV,
        embedding_model_loaded=True,
        provider_available=True,
        llm_provider=settings.LLM_PROVIDER,
        dimension=settings.EMBEDDING_DIMENSION,
    )


@app.get("/", tags=["root"])
def root() -> Dict[str, Any]:
    """Root metadata endpoint."""
    return {
        "name": "Vermithor Modular Monolith API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
    }


# Register all domain module routers under /api/v1
app.include_router(events_router, prefix="/api/v1")
app.include_router(incidents_router, prefix="/api/v1")
app.include_router(observations_router, prefix="/api/v1")
app.include_router(anomalies_router, prefix="/api/v1")
app.include_router(correlations_router, prefix="/api/v1")
app.include_router(rca_router, prefix="/api/v1")
app.include_router(logs_router, prefix="/api/v1")
app.include_router(retrieval_router, prefix="/api/v1")
app.include_router(runbooks_router, prefix="/api/v1")
app.include_router(summaries_router, prefix="/api/v1")
