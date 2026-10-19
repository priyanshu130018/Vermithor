import hashlib
import math
from typing import List, Optional

from backend.app.common.config import Settings, get_settings
from backend.app.log_intelligence.embedding.provider import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic vector embedding provider for offline testing and benchmarking.
    Generates unit-normalized 384-dimensional vectors from text hash digests without network I/O.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.dimension = self.settings.EMBEDDING_DIMENSION or 384
        self.model = self.settings.EMBEDDING_MODEL_NAME or "sentence-transformers/all-MiniLM-L6-v2"

    def get_provider_name(self) -> str:
        return "mock"

    def get_model_name(self) -> str:
        return self.model

    def get_dimension(self) -> int:
        return self.dimension

    def is_available(self) -> bool:
        return True

    def _generate_vector(self, text: str) -> List[float]:
        """Generate a deterministic, pseudo-semantic normalized 384-D vector from text content."""
        clean_text = text.strip() if text else ""
        raw = []

        # Use SHA-512 in chunks to produce 384 pseudo-random but deterministic floats
        seed_bytes = clean_text.encode("utf-8")
        block_idx = 0
        while len(raw) < self.dimension:
            digest = hashlib.sha512(seed_bytes + block_idx.to_bytes(4, "big")).digest()
            for b in digest:
                # Map byte 0-255 to float in [-1.0, 1.0]
                val = (float(b) / 127.5) - 1.0
                raw.append(val)
                if len(raw) == self.dimension:
                    break
            block_idx += 1

        # Add keyword bias so semantically similar phrases correlate positively in tests
        lower_text = clean_text.lower()
        if "redis" in lower_text or "cache" in lower_text or "category: cache" in lower_text:
            for i in range(60, 90):
                raw[i] += 2.5
        elif "login" in lower_text or "auth" in lower_text or "jwt" in lower_text or "category: authentication" in lower_text:
            for i in range(30, 60):
                raw[i] += 2.5
        elif "database" in lower_text or "postgres" in lower_text or "sql" in lower_text or "category: database" in lower_text:
            for i in range(0, 30):
                raw[i] += 2.5
        elif "operational" in lower_text or "backup" in lower_text or "category: operational" in lower_text:
            for i in range(90, 120):
                raw[i] += 2.5

        # L2 unit normalization
        norm = math.sqrt(sum(x * x for x in raw))
        if norm > 1e-12:
            return [x / norm for x in raw]
        return [0.0] * self.dimension

    def embed_text(self, text: str) -> List[float]:
        return self._generate_vector(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]
