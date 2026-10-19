from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """Abstract interface for vector embedding generation providers."""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate a single dense normalized embedding vector for the given string."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate dense normalized embedding vectors for a batch of strings."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Verify reachability and authentication with the embedding provider."""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the vector dimensionality (e.g. 384)."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider identifier (e.g. 'huggingface')."""
        pass
