import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.common.config import Settings, get_settings
from backend.app.log_intelligence.embedding.huggingface_provider import HuggingFaceEmbeddingProvider
from backend.app.log_intelligence.embedding.mock_provider import MockEmbeddingProvider
from backend.app.log_intelligence.embedding.provider import EmbeddingProvider
from backend.app.log_intelligence.parsing.normalizer import LogNormalizer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Manages vector embedding generation, input sanitization, and cloud provider orchestration.
    Delegates embedding computation to cloud APIs (Hugging Face Inference Providers) without
    loading local PyTorch or SentenceTransformer models into process memory.
    """

    def __init__(
        self,
        provider: Optional[EmbeddingProvider] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        if provider:
            self.provider = provider
        elif getattr(self.settings, "EMBEDDING_PROVIDER", "huggingface").lower() == "mock":
            self.provider = MockEmbeddingProvider(self.settings)
        else:
            self.provider = HuggingFaceEmbeddingProvider(self.settings)

        self._loaded: bool = True

    def load_model(self) -> None:
        """
        Backwards-compatible initialization method.
        Cloud embeddings do not require heavy local model downloads or memory loading.
        """
        logger.info(
            "Using cloud embedding provider '%s' (model: '%s', dimension: %d).",
            self.provider.get_provider_name(),
            self.provider.get_model_name(),
            self.provider.get_dimension(),
        )
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        """Return True indicating the embedding service is configured and ready."""
        return self._loaded

    @property
    def is_available(self) -> bool:
        """Check if the underlying embedding provider is reachable."""
        return self.provider.is_available()

    @classmethod
    def format_embedding_input(
        cls,
        service: str,
        severity: str,
        category: str,
        message: str,
    ) -> str:
        """
        Construct structured embedding context text.
        Passes through secret redaction to ensure no credentials or sensitive tokens are embedded.
        """
        redacted_msg = LogNormalizer.redact_secrets(message)
        return f"service: {service}\nseverity: {severity}\ncategory: {category}\nmessage: {redacted_msg}"

    def embed_text(self, text: str) -> List[float]:
        """Generate a normalized 384-D dense embedding vector for a single string."""
        return self.provider.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate normalized dense embedding vectors for a batch of strings."""
        if not texts:
            return []
        return self.provider.embed_batch(texts)

    def reembed_logs(self, db: Session, batch_size: int = 32) -> int:
        """
        Safely re-embed existing processed logs in the database.
        Allows non-destructive migration and synchronization of vector representations.
        """
        from backend.app.log_intelligence.db.models import LogEmbedding, ProcessedLog
        from backend.app.log_intelligence.repositories.log_repository import LogRepository

        stmt = select(ProcessedLog).order_by(ProcessedLog.created_at.asc())
        logs = db.execute(stmt).scalars().all()
        if not logs:
            return 0

        reembedded_count = 0
        for i in range(0, len(logs), batch_size):
            chunk = logs[i : i + batch_size]
            texts = [
                self.format_embedding_input(
                    service=l.service,
                    severity=l.severity,
                    category=l.category,
                    message=l.raw_message,
                )
                for l in chunk
            ]
            vectors = self.embed_batch(texts)
            for log_record, vec in zip(chunk, vectors):
                LogRepository.save_log_embedding(
                    db=db,
                    log_id=log_record.id,
                    model_name=self.provider.get_model_name(),
                    model_version=self.settings.MODEL_VERSION,
                    dimension=self.provider.get_dimension(),
                    embedding=vec,
                )
                reembedded_count += 1
            db.commit()

        logger.info("Successfully re-embedded %d log records.", reembedded_count)
        return reembedded_count


# Global singleton instance
_embedding_service_instance: Optional[EmbeddingService] = None


def get_embedding_service(provider: Optional[EmbeddingProvider] = None) -> EmbeddingService:
    """Return the global EmbeddingService singleton, optionally overriding the provider."""
    global _embedding_service_instance
    if provider is not None:
        _embedding_service_instance = EmbeddingService(provider=provider)
        _embedding_service_instance.load_model()
        return _embedding_service_instance

    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
        _embedding_service_instance.load_model()
    return _embedding_service_instance
