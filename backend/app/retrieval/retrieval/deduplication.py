from typing import List
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem


class ResultDeduplicator:
    """Deduplicates retrieval results across heterogeneous sources using stable source keys."""

    @staticmethod
    def deduplicate(items: List[RetrievalResultItem]) -> List[RetrievalResultItem]:
        """
        Deduplicate items preserving the highest-scoring occurrence.

        Returns:
            List[RetrievalResultItem]: Deduplicated list.
        """
        seen_keys = {}
        for item in items:
            key = (item.source_type, str(item.source_id).strip().lower())
            if key not in seen_keys or item.final_score > seen_keys[key].final_score:
                seen_keys[key] = item

        return list(seen_keys.values())
