import logging
import uuid
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.app.log_intelligence.embedding.service import EmbeddingService, get_embedding_service
from backend.app.log_intelligence.repositories.log_repository import LogRepository
from backend.app.log_intelligence.schemas.logs import (
    LogCategory,
    SearchResultItem,
    SemanticSearchRequest,
    SemanticSearchResponse,
)

logger = logging.getLogger(__name__)


class SemanticSearchService:
    """Orchestrates query vectorization and semantic vector search."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        self.embedding_service = embedding_service or get_embedding_service()

    def search(
        self,
        db: Session,
        req: SemanticSearchRequest,
    ) -> SemanticSearchResponse:
        """Execute semantic search across all indexed logs with optional metadata filters."""
        # 1. Embed query
        query_vector = self.embedding_service.embed_text(req.query)

        # 2. Query repository
        category_val = req.category.value if req.category else None
        matches = LogRepository.search_vector_similarity(
            db=db,
            query_vector=query_vector,
            top_k=req.top_k,
            service=req.service,
            environment=req.environment,
            severity=req.severity,
            category=category_val,
            start_time=req.start_time,
            end_time=req.end_time,
            min_similarity=req.min_similarity,
        )

        results: List[SearchResultItem] = [
            SearchResultItem(
                log_id=log.id,
                source_event_id=log.source_event_id,
                timestamp=log.timestamp,
                service=log.service,
                environment=log.environment,
                severity=log.severity,
                category=LogCategory(log.category),
                message=log.raw_message,
                normalized_message=log.normalized_message,
                template=log.template,
                similarity_score=round(score, 4),
            )
            for log, score in matches
        ]

        return SemanticSearchResponse(
            query=req.query,
            total_results=len(results),
            results=results,
        )

    def find_similar_to_log(
        self,
        db: Session,
        log_id: uuid.UUID,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
    ) -> List[SearchResultItem]:
        """Find logs semantically similar to an existing processed log."""
        source_log = LogRepository.get_by_id(db, log_id)
        if not source_log:
            return []

        if source_log.embedding and source_log.embedding.embedding:
            query_vector = (
                source_log.embedding.embedding
                if isinstance(source_log.embedding.embedding, list)
                else list(source_log.embedding.embedding)
            )
        else:
            text = self.embedding_service.format_embedding_input(
                service=source_log.service,
                severity=source_log.severity,
                category=source_log.category,
                message=source_log.raw_message,
            )
            query_vector = self.embedding_service.embed_text(text)

        matches = LogRepository.search_vector_similarity(
            db=db,
            query_vector=query_vector,
            top_k=top_k,
            exclude_log_id=log_id,
            min_similarity=min_similarity,
        )

        return [
            SearchResultItem(
                log_id=log.id,
                source_event_id=log.source_event_id,
                timestamp=log.timestamp,
                service=log.service,
                environment=log.environment,
                severity=log.severity,
                category=LogCategory(log.category),
                message=log.raw_message,
                normalized_message=log.normalized_message,
                template=log.template,
                similarity_score=round(score, 4),
            )
            for log, score in matches
        ]
