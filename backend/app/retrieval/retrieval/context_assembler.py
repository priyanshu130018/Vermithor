from typing import List, Tuple
from backend.app.common.config import Settings, get_settings
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem


class ContextAssembler:
    """Assembles ranked, deduplicated evidence and constructs bounded RAG prompt context."""

    def __init__(self, settings: Settings = None):
        self.settings = settings or get_settings()

    def assemble(
        self,
        items: List[RetrievalResultItem],
        max_results: int = None,
        max_chars: int = None,
    ) -> Tuple[List[RetrievalResultItem], str, bool]:
        """
        Sorts by final_score, truncates within character bounds, and formats context text.

        Returns:
            Tuple[List[RetrievalResultItem], str, bool]: (included_items, context_text, is_truncated)
        """
        limit_results = max_results or self.settings.MAX_CONTEXT_RESULTS
        limit_chars = max_chars or self.settings.MAX_CONTEXT_CHARS

        # Sort by final_score descending
        sorted_items = sorted(items, key=lambda x: x.final_score, reverse=True)

        included_items: List[RetrievalResultItem] = []
        text_blocks: List[str] = []
        current_chars = 0
        is_truncated = False

        for item in sorted_items:
            if len(included_items) >= limit_results:
                is_truncated = True
                break

            block = (
                f"### {item.citation} {item.title}\n"
                f"Source: {item.source_type.value} | Final Score: {item.final_score:.2f} | "
                f"Service: {item.service or 'N/A'} | Environment: {item.environment or 'N/A'}\n"
                f"Content: {item.content.strip()}\n"
            )

            if current_chars + len(block) > limit_chars:
                is_truncated = True
                if not included_items:
                    truncated_content = item.content[: max(50, limit_chars - 200)] + "... [TRUNCATED]"
                    block = (
                        f"### {item.citation} {item.title}\n"
                        f"Source: {item.source_type.value} | Final Score: {item.final_score:.2f}\n"
                        f"Content: {truncated_content}\n"
                    )
                    included_items.append(item)
                    text_blocks.append(block)
                break

            included_items.append(item)
            text_blocks.append(block)
            current_chars += len(block)

        context_text = "\n".join(text_blocks)
        return included_items, context_text, is_truncated
