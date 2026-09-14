import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.common.config import get_settings
from backend.app.common.database import get_db
from backend.app.log_intelligence.clustering.service import LogClusteringService
from backend.app.log_intelligence.embedding.service import get_embedding_service
from backend.app.log_intelligence.parsing.classifier import LogClassifier
from backend.app.log_intelligence.parsing.normalizer import LogNormalizer
from backend.app.log_intelligence.parsing.template_extractor import LogTemplateExtractor
from backend.app.log_intelligence.repositories.log_repository import LogRepository
from backend.app.log_intelligence.schemas.logs import (
    LogBatchIngestRequest,
    LogBatchIngestResponse,
    LogCategory,
    LogClusterItem,
    LogClusteringRequest,
    LogClusteringResponse,
    LogEmbeddingMetadataResponse,
    LogIngestRequest,
    ProcessedLogResponse,
    SearchResultItem,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from backend.app.log_intelligence.search.semantic_search import SemanticSearchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/logs", tags=["logs"])
settings = get_settings()


def _to_processed_log_response(log) -> ProcessedLogResponse:
    emb_meta = None
    if log.embedding:
        emb_meta = LogEmbeddingMetadataResponse(
            model_name=log.embedding.model_name,
            model_version=log.embedding.model_version,
            dimension=log.embedding.dimension,
            created_at=log.embedding.created_at,
        )
    return ProcessedLogResponse(
        id=log.id,
        source_event_id=log.source_event_id,
        timestamp=log.timestamp,
        service=log.service,
        environment=log.environment,
        severity=log.severity,
        category=LogCategory(log.category),
        raw_message=log.raw_message,
        normalized_message=log.normalized_message,
        template=log.template,
        trace_id=log.trace_id,
        metadata=log.metadata_json or {},
        embedding=emb_meta,
        created_at=log.created_at,
    )


@router.post(
    "",
    response_model=ProcessedLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest and process a single log event",
    description="Redacts secrets, normalizes volatile values, extracts template, classifies category, and generates vector embedding.",
)
def ingest_log(
    req: LogIngestRequest,
    db: Session = Depends(get_db),
) -> ProcessedLogResponse:
    """Process and embed a single observability log."""
    embedding_service = get_embedding_service()

    # 1. Normalization & parsing
    normalized = LogNormalizer.normalize_log(req.message)
    template = LogTemplateExtractor.extract_template(normalized)
    category = LogClassifier.classify(req.message, req.service)

    # 2. Persist processed log
    log_record = LogRepository.save_processed_log(
        db=db,
        log_data={
            "source_event_id": req.source_event_id,
            "timestamp": req.timestamp,
            "service": req.service,
            "environment": req.environment,
            "severity": req.severity,
            "category": category.value,
            "raw_message": req.message,
            "normalized_message": normalized,
            "template": template,
            "trace_id": req.trace_id,
            "metadata": req.metadata,
        },
    )

    # 3. Generate embedding
    emb_text = embedding_service.format_embedding_input(
        service=req.service,
        severity=req.severity,
        category=category.value,
        message=req.message,
    )
    vector = embedding_service.embed_text(emb_text)

    # 4. Save embedding
    LogRepository.save_log_embedding(
        db=db,
        log_id=log_record.id,
        model_name=settings.EMBEDDING_MODEL_NAME,
        model_version=settings.MODEL_VERSION,
        dimension=settings.EMBEDDING_DIMENSION,
        embedding=vector,
    )

    db.commit()
    db.refresh(log_record)
    return _to_processed_log_response(log_record)


@router.post(
    "/batch",
    response_model=LogBatchIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Batch ingest and process multiple log events",
    description="Efficiently processes and embeds multiple log events using batch model inference.",
)
def batch_ingest_logs(
    batch_req: LogBatchIngestRequest,
    db: Session = Depends(get_db),
) -> LogBatchIngestResponse:
    """Batch process logs and generate embeddings concurrently."""
    embedding_service = get_embedding_service()

    parsed_items = []
    texts_to_embed = []

    for req in batch_req.logs:
        normalized = LogNormalizer.normalize_log(req.message)
        template = LogTemplateExtractor.extract_template(normalized)
        category = LogClassifier.classify(req.message, req.service)

        parsed_items.append({
            "req": req,
            "normalized": normalized,
            "template": template,
            "category": category,
        })
        texts_to_embed.append(
            embedding_service.format_embedding_input(
                service=req.service,
                severity=req.severity,
                category=category.value,
                message=req.message,
            )
        )

    # Batch model embedding
    embeddings = embedding_service.embed_batch(texts_to_embed)

    processed_logs = []
    for item, vector in zip(parsed_items, embeddings):
        req = item["req"]
        log_record = LogRepository.save_processed_log(
            db=db,
            log_data={
                "source_event_id": req.source_event_id,
                "timestamp": req.timestamp,
                "service": req.service,
                "environment": req.environment,
                "severity": req.severity,
                "category": item["category"].value,
                "raw_message": req.message,
                "normalized_message": item["normalized"],
                "template": item["template"],
                "trace_id": req.trace_id,
                "metadata": req.metadata,
            },
        )
        LogRepository.save_log_embedding(
            db=db,
            log_id=log_record.id,
            model_name=settings.EMBEDDING_MODEL_NAME,
            model_version=settings.MODEL_VERSION,
            dimension=settings.EMBEDDING_DIMENSION,
            embedding=vector,
        )
        processed_logs.append(log_record)

    db.commit()
    for record in processed_logs:
        db.refresh(record)

    return LogBatchIngestResponse(
        processed=len(processed_logs),
        items=[_to_processed_log_response(r) for r in processed_logs],
    )


@router.post(
    "/search",
    response_model=SemanticSearchResponse,
    summary="Semantic vector search across indexed logs",
)
def search_logs(
    search_req: SemanticSearchRequest,
    db: Session = Depends(get_db),
) -> SemanticSearchResponse:
    """Perform semantic vector similarity search against indexed logs with metadata filters."""
    search_service = SemanticSearchService(get_embedding_service())
    return search_service.search(db=db, req=search_req)


# ==============================================================================
# HDBSCAN Log Clustering Endpoints (Defined before dynamic /{log_id})
# ==============================================================================

@router.post(
    "/clusters/run",
    response_model=LogClusteringResponse,
    summary="Execute HDBSCAN log clustering across a custom time window",
    description="Clusters processed log embeddings using HDBSCAN, identifies noise, and extracts representative error patterns.",
)
def run_log_clustering(
    req: LogClusteringRequest,
    db: Session = Depends(get_db),
) -> LogClusteringResponse:
    """Run HDBSCAN log clustering on-demand with filter criteria."""
    clustering_service = LogClusteringService()
    return clustering_service.cluster_db_logs(db=db, req=req)


@router.get(
    "/clusters",
    response_model=LogClusteringResponse,
    summary="Get semantic log clusters for the recent time window",
    description="Returns discovered log clusters and noise points within the default or specified time window.",
)
def get_log_clusters(
    service: Optional[str] = Query(None, description="Filter by service name"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    min_cluster_size: Optional[int] = Query(None, ge=2, description="Minimum cluster size"),
    include_noise: bool = Query(True, description="Include outlier/noise points"),
    db: Session = Depends(get_db),
) -> LogClusteringResponse:
    """Retrieve current log clusters for the active monitoring window."""
    req = LogClusteringRequest(
        service=service,
        environment=environment,
        min_cluster_size=min_cluster_size,
        include_noise=include_noise,
    )
    clustering_service = LogClusteringService()
    return clustering_service.cluster_db_logs(db=db, req=req)


@router.get(
    "/clusters/{cluster_id}",
    response_model=LogClusterItem,
    summary="Get details for a specific log cluster",
)
def get_log_cluster_by_id(
    cluster_id: int,
    db: Session = Depends(get_db),
) -> LogClusterItem:
    """Fetch details, representative messages, and member log IDs for a specific cluster."""
    clustering_service = LogClusteringService()
    response = clustering_service.cluster_db_logs(db=db)
    target = next((c for c in response.clusters if c.cluster_id == cluster_id), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log cluster with ID {cluster_id} not found in recent time window",
        )
    return target


# ==============================================================================
# Single Log Detail & Similar Endpoints
# ==============================================================================

@router.get(
    "/{log_id}",
    response_model=ProcessedLogResponse,
    summary="Get processed log by ID",
)
def get_log_by_id(
    log_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProcessedLogResponse:
    """Retrieve processed log details and embedding metadata."""
    log = LogRepository.get_by_id(db, log_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log with ID '{log_id}' not found",
        )
    return _to_processed_log_response(log)


@router.get(
    "/{log_id}/similar",
    response_model=List[SearchResultItem],
    summary="Find similar logs to an existing log",
)
def get_similar_logs(
    log_id: uuid.UUID,
    top_k: int = Query(5, ge=1, le=50),
    min_similarity: Optional[float] = Query(None, ge=-1.0, le=1.0),
    db: Session = Depends(get_db),
) -> List[SearchResultItem]:
    """Find logs semantically similar to the specified log ID."""
    source_log = LogRepository.get_by_id(db, log_id)
    if not source_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log with ID '{log_id}' not found",
        )

    search_service = SemanticSearchService(get_embedding_service())
    return search_service.find_similar_to_log(
        db=db,
        log_id=log_id,
        top_k=top_k,
        min_similarity=min_similarity,
    )
