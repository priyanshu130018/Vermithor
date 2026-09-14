import logging
from typing import List, Optional
from sentence_transformers import SentenceTransformer
import torch

from backend.app.common.config import Settings, get_settings
from backend.app.log_intelligence.parsing.normalizer import LogNormalizer

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Manages sentence-transformer model loading, controlled input formatting, and dense vector generation."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._model: Optional[SentenceTransformer] = None
        self._loaded: bool = False

    def load_model(self) -> None:
        """Load the SentenceTransformer model into memory on the configured device."""
        if self._loaded and self._model is not None:
            return

        logger.info(
            "Loading embedding model '%s' on device '%s'...",
            self.settings.EMBEDDING_MODEL_NAME,
            self.settings.EMBEDDING_DEVICE,
        )
        try:
            device = self.settings.EMBEDDING_DEVICE
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA requested but not available. Falling back to CPU.")
                device = "cpu"

            self._model = SentenceTransformer(self.settings.EMBEDDING_MODEL_NAME, device=device)
            if hasattr(self._model, "get_embedding_dimension"):
                dim = self._model.get_embedding_dimension()
            else:
                dim = self._model.get_sentence_embedding_dimension()

            if dim != self.settings.EMBEDDING_DIMENSION:
                raise ValueError(
                    f"Model embedding dimension mismatch: configured {self.settings.EMBEDDING_DIMENSION}, actual {dim}"
                )

            self._loaded = True
            logger.info("Embedding model loaded successfully. Output dimension: %d", dim)
        except Exception as exc:
            self._loaded = False
            logger.error("Failed to load embedding model: %s", exc)
            raise exc

    @property
    def is_loaded(self) -> bool:
        """Return True if model is loaded in memory."""
        return self._loaded and self._model is not None

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
        Passes through secret redaction to ensure no credentials are embedded.
        """
        redacted_msg = LogNormalizer.redact_secrets(message)
        return f"service: {service}\nseverity: {severity}\ncategory: {category}\nmessage: {redacted_msg}"

    def embed_text(self, text: str) -> List[float]:
        """Generate a normalized 384-D dense embedding vector for a single string."""
        if not self.is_loaded:
            self.load_model()
        
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate normalized dense embedding vectors for a batch of strings."""
        if not texts:
            return []
        if not self.is_loaded:
            self.load_model()

        embeddings = self._model.encode(texts, batch_size=32, normalize_embeddings=True)
        return embeddings.tolist()


# Global singleton instance
_embedding_service_instance: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Return the global EmbeddingService singleton."""
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
        _embedding_service_instance.load_model()
    return _embedding_service_instance
