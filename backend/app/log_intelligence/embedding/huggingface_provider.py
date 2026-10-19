import logging
import math
import time
from typing import Any, Dict, List, Optional, Union
import httpx

from backend.app.common.config import Settings, get_settings
from backend.app.log_intelligence.embedding.provider import EmbeddingProvider

logger = logging.getLogger(__name__)


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """
    Cloud vector embedding provider utilizing Hugging Face Inference Providers API.
    Calls serverless pipeline feature-extraction for dense text vector representations.

    Default Endpoint: https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction
    Default Model: sentence-transformers/all-MiniLM-L6-v2 (384-dimensional dense vectors)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.token = self.settings.HF_TOKEN
        self.model = self.settings.EMBEDDING_MODEL_NAME or "sentence-transformers/all-MiniLM-L6-v2"
        self.dimension = self.settings.EMBEDDING_DIMENSION or 384
        self.base_url = (self.settings.HF_EMBEDDING_BASE_URL or "https://router.huggingface.co/hf-inference").rstrip("/")
        self.endpoint_url = self.settings.HF_EMBEDDING_URL or f"{self.base_url}/models/{self.model}/pipeline/feature-extraction"
        self.timeout = float(self.settings.EMBEDDING_TIMEOUT_SECONDS)
        self.max_retries = int(self.settings.EMBEDDING_MAX_RETRIES)
        self.batch_size = int(self.settings.EMBEDDING_BATCH_SIZE)

    def get_provider_name(self) -> str:
        return "huggingface"

    def get_model_name(self) -> str:
        return self.model

    def get_dimension(self) -> int:
        return self.dimension

    def is_available(self) -> bool:
        """
        Bounded, authenticated check verifying Hugging Face API reachability and token validity.
        Queries the model listing endpoint without incurring embedding generation quotas.
        """
        if not self.token or not self.token.strip():
            return False

        headers = {
            "Authorization": f"Bearer {self.token.strip()}",
            "User-Agent": "Vermithor-Incident-Intelligence/1.0",
        }
        # Check model reachability on router
        check_url = f"{self.base_url}/models/{self.model}"
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(check_url, headers=headers)
                return res.status_code == 200
        except Exception:
            return False

    def _normalize_vector(self, vec: List[float]) -> List[float]:
        """Compute L2 unit normalization for exact cosine similarity compatibility."""
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-12:
            return [float(x / norm) for x in vec]
        return [float(x) for x in vec]

    def _validate_vector(self, vec: Any, expected_dim: int) -> List[float]:
        """Validate vector is a non-empty, finite list of expected dimensionality."""
        if not isinstance(vec, (list, tuple)):
            raise ValueError(f"Invalid embedding format: expected list, got {type(vec).__name__}")

        if len(vec) != expected_dim:
            raise ValueError(f"Vector dimension mismatch: expected {expected_dim}, got {len(vec)}")

        for idx, val in enumerate(vec):
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError(f"Vector contains invalid or non-finite value at index {idx}: {val}")

        return self._normalize_vector(list(vec))

    def _pool_tokens_if_needed(self, item: Any) -> List[float]:
        """
        If the response is a 2D matrix of shape (seq_len, hidden_dim),
        apply mean pooling across the sequence to produce a 1D vector (hidden_dim).
        """
        # Unwrap extra nested dimensions if present (e.g. 1 x seq_len x dim)
        while isinstance(item, list) and len(item) == 1 and isinstance(item[0], list) and len(item[0]) > 0 and isinstance(item[0][0], list):
            item = item[0]

        if isinstance(item, list) and len(item) > 0 and isinstance(item[0], list):
            # item is a list of token vectors [[float, ...], [float, ...]]
            seq_len = len(item)
            dim = len(item[0])
            summed = [0.0] * dim
            for token_vec in item:
                if len(token_vec) != dim:
                    raise ValueError("Inconsistent token vector length in 3D embedding response")
                for d in range(dim):
                    summed[d] += float(token_vec[d])
            return [val / seq_len for val in summed]
        elif isinstance(item, list):
            return [float(x) for x in item]
        else:
            raise ValueError(f"Unexpected item structure in embedding response: {type(item).__name__}")

    def _parse_embeddings_response(self, data: Any, expected_count: int) -> List[List[float]]:
        """
        Parse raw JSON response from Hugging Face Inference Providers API or OpenAI-compatible format.
        Supports:
        1. Feature extraction standard list of lists: [[float, ...], ...]
        2. Token-level 3D list: [[[float, ...], ...], ...] (with automated mean pooling)
        3. Single vector response: [float, ...] or [[float, ...]]
        4. OpenAI-compatible envelope: {"data": [{"embedding": [...]}, ...]}
        """
        raw_vectors: List[Any] = []

        if isinstance(data, dict):
            # OpenAI-compatible envelope
            if "data" in data and isinstance(data["data"], list):
                raw_vectors = [item.get("embedding") for item in data["data"]]
            elif "embeddings" in data and isinstance(data["embeddings"], list):
                raw_vectors = data["embeddings"]
            elif "error" in data:
                raise RuntimeError(f"Hugging Face API returned error: {data['error']}")
            else:
                raise ValueError(f"Unrecognized embedding response dictionary keys: {list(data.keys())}")
        elif isinstance(data, list):
            if len(data) == 0:
                raise ValueError("Hugging Face API returned empty embedding list")

            # Check if single 1D vector returned for expected_count == 1
            if expected_count == 1 and all(isinstance(x, (int, float)) for x in data):
                raw_vectors = [data]
            else:
                raw_vectors = data
        else:
            raise ValueError(f"Unexpected embedding response type: {type(data).__name__}")

        if len(raw_vectors) != expected_count:
            raise ValueError(
                f"Embedding count mismatch: sent {expected_count} texts, received {len(raw_vectors)} vectors"
            )

        validated: List[List[float]] = []
        for raw_item in raw_vectors:
            pooled = self._pool_tokens_if_needed(raw_item)
            validated.append(self._validate_vector(pooled, self.dimension))

        return validated

    def _execute_api_call(self, inputs: Union[str, List[str]], expected_count: int) -> List[List[float]]:
        """
        Execute authenticated HTTP POST request to Hugging Face with retries and backoff.
        Ensures secrets and log messages are not leaked into exception traces.
        """
        if not self.token or not self.token.strip():
            raise ValueError(
                "HF_TOKEN is not configured. Please configure HF_TOKEN in your environment or .env file "
                "to generate cloud embeddings."
            )

        headers = {
            "Authorization": f"Bearer {self.token.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "Vermithor-Incident-Intelligence/1.0",
        }
        payload = {"inputs": inputs}

        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    res = client.post(self.endpoint_url, headers=headers, json=payload)

                    if res.status_code == 200:
                        data = res.json()
                        return self._parse_embeddings_response(data, expected_count)

                    if res.status_code == 401:
                        logger.error("Hugging Face embedding authentication failed (HTTP 401).")
                        raise RuntimeError(
                            "Hugging Face embedding authentication failed (HTTP 401). Please verify your HF_TOKEN."
                        )

                    if res.status_code in (429, 503):
                        retry_after = res.headers.get("Retry-After")
                        logger.warning(
                            "Hugging Face embedding API returned HTTP %d (attempt %d/%d).",
                            res.status_code,
                            attempt + 1,
                            self.max_retries + 1,
                        )
                        if attempt < self.max_retries:
                            sleep_sec = float(retry_after) if (retry_after and retry_after.isdigit()) else (1.5 * (2 ** attempt))
                            time.sleep(sleep_sec)
                            continue
                        raise RuntimeError(
                            f"Hugging Face embedding API rate limit or service unavailable (HTTP {res.status_code})."
                        )

                    # Other HTTP error statuses
                    raise RuntimeError(
                        f"Hugging Face embedding API failed with HTTP {res.status_code}: {res.text[:200]}"
                    )

            except (httpx.TimeoutException, httpx.RequestError) as net_err:
                last_exc = net_err
                logger.warning(
                    "Network error reaching Hugging Face embedding API (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries + 1,
                    type(net_err).__name__,
                )
                if attempt < self.max_retries:
                    time.sleep(1.0 * (2 ** attempt))
                    continue
                raise RuntimeError(
                    f"Hugging Face embedding request failed after {self.max_retries + 1} attempts: {type(net_err).__name__}"
                ) from net_err

        if last_exc:
            raise last_exc
        raise RuntimeError("Embedding request failed unexpectedly.")

    def embed_text(self, text: str) -> List[float]:
        """Generate a single 384-D normalized vector using the cloud API."""
        if not text or not text.strip():
            # Return zero vector or embed whitespace placeholder safely
            text = " "
        results = self._execute_api_call(inputs=text, expected_count=1)
        return results[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate normalized dense embeddings for a batch of strings, chunked by batch_size."""
        if not texts:
            return []

        all_vectors: List[List[float]] = []

        # Process in chunks of self.batch_size to respect HF payload limits
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]
            # Replace empty strings with whitespace so model receives valid tokens
            sanitized_chunk = [t if (t and t.strip()) else " " for t in chunk]
            chunk_vectors = self._execute_api_call(inputs=sanitized_chunk, expected_count=len(chunk))
            all_vectors.extend(chunk_vectors)

        return all_vectors
