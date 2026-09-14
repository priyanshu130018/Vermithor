from datetime import datetime, timezone
import math
from typing import Optional
from backend.app.common.config import Settings, get_settings
from backend.app.retrieval.schemas.retrieval import RetrievalQuery, RetrievalResultItem, SourceType


class HybridRanker:
    """Computes normalized hybrid ranking scores across heterogeneous operational sources."""

    SOURCE_RELIABILITY = {
        SourceType.RCA: 1.00,
        SourceType.INCIDENT: 0.90,
        SourceType.RUNBOOK: 0.90,
        SourceType.LOG: 0.80,
        SourceType.DEPLOYMENT: 0.80,
    }

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def score_item(
        self,
        item: RetrievalResultItem,
        query_context: RetrievalQuery,
    ) -> RetrievalResultItem:
        """
        Calculate individual and composite hybrid score for a retrieval result.

        Returns:
            RetrievalResultItem: Updated item with metadata_score, recency_score, source_score, and final_score.
        """
        # 1. Semantic score (from source or default)
        semantic_score = item.similarity_score

        # 2. Metadata score (boost if service/environment matches query context)
        metadata_score = 0.50
        matches = 0
        checks = 0

        if query_context.service:
            checks += 1
            if item.service and item.service.lower() == query_context.service.lower():
                matches += 1

        if query_context.environment:
            checks += 1
            if item.environment and item.environment.lower() == query_context.environment.lower():
                matches += 1

        if checks > 0:
            metadata_score = matches / checks

        # 3. Recency score (bounded time decay)
        recency_score = 0.70
        if item.timestamp:
            now = datetime.now(timezone.utc)
            item_ts = item.timestamp
            if item_ts.tzinfo is None:
                item_ts = item_ts.replace(tzinfo=timezone.utc)
            delta_days = max(0.0, (now - item_ts).total_seconds() / 86400.0)
            # Smooth bounded decay: score approaches 0.2 over 30 days
            recency_score = max(0.20, 1.0 / (1.0 + (delta_days * 0.05)))

        # 4. Source reliability score
        source_score = self.SOURCE_RELIABILITY.get(item.source_type, 0.80)

        # 5. Composite weighted final score
        final_score = (
            semantic_score * self.settings.RETRIEVAL_WEIGHT_SEMANTIC
            + metadata_score * self.settings.RETRIEVAL_WEIGHT_METADATA
            + recency_score * self.settings.RETRIEVAL_WEIGHT_RECENCY
            + source_score * self.settings.RETRIEVAL_WEIGHT_SOURCE
        )

        item.metadata_score = round(min(1.0, max(0.0, metadata_score)), 4)
        item.recency_score = round(min(1.0, max(0.0, recency_score)), 4)
        item.source_score = round(min(1.0, max(0.0, source_score)), 4)
        item.final_score = round(min(1.0, max(0.0, final_score)), 4)
        return item
