from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, Optional
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import backend.app.common.database as common_db
from backend.app.anomaly.api.anomalies import router as anomalies_router
from backend.app.anomaly.api.observations import router as observations_router
from backend.app.auth.api.auth import router as auth_router
from backend.app.common.config import get_settings
from backend.app.common.security import require_jwt_auth
from backend.app.common.telemetry import setup_telemetry
from backend.app.correlation.api.correlations import router as correlations_router
from backend.app.incidents.api.incidents import router as incidents_router
from backend.app.ingestion.api.events import router as events_router
from backend.app.log_intelligence.api.logs import router as logs_router
from backend.app.observability.api.observability import router as observability_router
from backend.app.rca.api.rca import router as rca_router
from backend.app.retrieval.api.retrieval import router as retrieval_router
from backend.app.retrieval.api.runbooks import router as runbooks_router
from backend.app.summary.api.summaries import router as summaries_router
from backend.app.agent.api.investigations import router as agent_router
from backend.app.agent.api.repairs import router as repairs_router

# Import all models to ensure complete metadata registration
import backend.app.ingestion.db.models
import backend.app.incidents.db.models
import backend.app.anomaly.db.models
import backend.app.correlation.db.models
import backend.app.rca.db.models
import backend.app.log_intelligence.db.models
import backend.app.retrieval.db.models
import backend.app.summary.db.models
import backend.app.agent.db.models

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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Structured JSON error handler for HTTP exceptions ensuring consistent API responses."""
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        req_id = request.headers.get("x-request-id", "unknown")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "detail": exc.detail,
                "error": "unauthorized",
                "message": exc.detail,
                "request_id": req_id,
            },
            headers=exc.headers or {"WWW-Authenticate": "Bearer"},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
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
    llm_provider: str = "huggingface"
    llm_model: Optional[str] = None
    llm_connectivity: str = "connected"
    embedding_provider: str = "huggingface"
    dimension: int = 384


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Public liveness probe for orchestrator health checking (unauthenticated)."""
    return HealthResponse(
        service=settings.SERVICE_NAME,
        status="healthy",
    )


@app.get("/ready", response_model=ReadinessResponse, tags=["health"])
def readiness_check() -> ReadinessResponse:
    """Public readiness probe checking database connectivity and subsystem initialization (unauthenticated)."""
    db_status = "connected"
    try:
        with common_db.engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:
        logger.warning("Readiness DB check warning: %s", exc)
        db_status = "degraded"

    # LLM provider connectivity check
    llm_avail = False
    llm_model_name = None
    llm_provider_name = settings.LLM_PROVIDER
    try:
        from backend.app.summary.llm.factory import ProviderFactory
        provider = ProviderFactory.get_provider(settings)
        llm_avail = provider.is_available()
        llm_model_name = provider.get_model_name()
        llm_provider_name = provider.get_provider_name()
    except Exception as exc:
        logger.warning("Readiness LLM provider check warning: %s", exc)
        llm_avail = False

    return ReadinessResponse(
        service=settings.SERVICE_NAME,
        status="ready" if db_status == "connected" else "degraded",
        database=db_status,
        environment=settings.APP_ENV,
        embedding_model_loaded=True,
        provider_available=llm_avail,
        llm_provider=llm_provider_name,
        llm_model=llm_model_name,
        llm_connectivity="connected" if llm_avail else "unreachable",
        embedding_provider=settings.EMBEDDING_PROVIDER,
        dimension=settings.EMBEDDING_DIMENSION,
    )


@app.get("/", tags=["root"])
def root() -> Dict[str, Any]:
    """Public root metadata endpoint (unauthenticated)."""
    return {
        "name": "Vermithor Modular Monolith API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
    }


# Public authentication endpoint for development token issuance and client authorization
app.include_router(auth_router, prefix="/api/v1")

# Register all domain module routers under /api/v1 with enforced JWT authentication
jwt_dependency = [Depends(require_jwt_auth)]

app.include_router(events_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(incidents_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(observations_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(anomalies_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(correlations_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(rca_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(logs_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(retrieval_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(runbooks_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(summaries_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(observability_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(agent_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(repairs_router, prefix="/api/v1", dependencies=jwt_dependency)
