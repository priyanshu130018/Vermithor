import math
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import MagicMock, patch
import httpx
import pytest

from backend.app.common.config import Settings
from backend.app.log_intelligence.db.models import LogEmbedding, ProcessedLog
from backend.app.log_intelligence.embedding.huggingface_provider import HuggingFaceEmbeddingProvider
from backend.app.log_intelligence.embedding.mock_provider import MockEmbeddingProvider
from backend.app.log_intelligence.embedding.service import EmbeddingService, get_embedding_service


def _make_dummy_vector(dim: int = 384, val: float = 0.05) -> List[float]:
    """Create a raw vector with specified dimension."""
    return [val] * dim


def test_hf_embedding_provider_single_success():
    """Verify HuggingFaceEmbeddingProvider successfully processes single text response."""
    test_settings = Settings(
        HF_TOKEN="hf_test_secret_token",
        EMBEDDING_PROVIDER="huggingface",
        EMBEDDING_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2",
        EMBEDDING_DIMENSION=384,
        HF_EMBEDDING_BASE_URL="https://router.huggingface.co/hf-inference",
        EMBEDDING_TIMEOUT_SECONDS=5,
        EMBEDDING_MAX_RETRIES=1,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)
    assert provider.get_provider_name() == "huggingface"
    assert provider.get_model_name() == "sentence-transformers/all-MiniLM-L6-v2"
    assert provider.get_dimension() == 384

    dummy_vec = _make_dummy_vector(384, 0.1)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [dummy_vec]

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        vec = provider.embed_text("database connection timeout error")
        assert len(vec) == 384
        # Verify L2 normalization (~1.0)
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer hf_test_secret_token"
        assert kwargs["json"] == {"inputs": "database connection timeout error"}


def test_hf_embedding_provider_batch_success():
    """Verify HuggingFaceEmbeddingProvider processes batch text responses."""
    test_settings = Settings(
        HF_TOKEN="hf_test_secret_token",
        EMBEDDING_PROVIDER="huggingface",
        EMBEDDING_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2",
        EMBEDDING_DIMENSION=384,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    batch_vecs = [_make_dummy_vector(384, 0.1), _make_dummy_vector(384, 0.2)]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = batch_vecs

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = provider.embed_batch(["text one", "text two"])
        assert len(res) == 2
        assert len(res[0]) == 384
        assert len(res[1]) == 384
        mock_post.assert_called_once()


def test_hf_embedding_provider_chunking():
    """Verify HuggingFaceEmbeddingProvider chunks requests exceeding EMBEDDING_BATCH_SIZE."""
    test_settings = Settings(
        HF_TOKEN="hf_test_secret_token",
        EMBEDDING_PROVIDER="huggingface",
        EMBEDDING_BATCH_SIZE=2,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    mock_resp1 = MagicMock(status_code=200, json=lambda: [_make_dummy_vector(384), _make_dummy_vector(384)])
    mock_resp2 = MagicMock(status_code=200, json=lambda: [_make_dummy_vector(384), _make_dummy_vector(384)])
    mock_resp3 = MagicMock(status_code=200, json=lambda: [_make_dummy_vector(384)])

    with patch("httpx.Client.post", side_effect=[mock_resp1, mock_resp2, mock_resp3]) as mock_post:
        res = provider.embed_batch(["a", "b", "c", "d", "e"])
        assert len(res) == 5
        assert mock_post.call_count == 3


def test_hf_embedding_provider_missing_token():
    """Verify clear error is raised when HF_TOKEN is missing or empty."""
    test_settings = Settings(HF_TOKEN="")
    provider = HuggingFaceEmbeddingProvider(test_settings)

    with pytest.raises(ValueError, match="HF_TOKEN is not configured"):
        provider.embed_text("test")


def test_hf_embedding_provider_401_auth_failure():
    """Verify authentication errors (HTTP 401) raise descriptive RuntimeError."""
    test_settings = Settings(HF_TOKEN="invalid_token")
    provider = HuggingFaceEmbeddingProvider(test_settings)

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = '{"error":"Invalid credentials"}'

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Hugging Face embedding authentication failed.*401"):
            provider.embed_text("test")


def test_hf_embedding_provider_rate_limit_retry():
    """Verify HTTP 429 rate limit triggers bounded retries with backoff."""
    test_settings = Settings(
        HF_TOKEN="hf_token",
        EMBEDDING_MAX_RETRIES=2,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    mock_resp_429 = MagicMock(status_code=429, headers={"Retry-After": "0"})
    mock_resp_200 = MagicMock(status_code=200, json=lambda: [_make_dummy_vector(384)])

    with patch("time.sleep") as mock_sleep:
        with patch("httpx.Client.post", side_effect=[mock_resp_429, mock_resp_200]) as mock_post:
            res = provider.embed_text("test")
            assert len(res) == 384
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once()


def test_hf_embedding_provider_rate_limit_exhausted():
    """Verify HTTP 429 raises RuntimeError when max retries are exhausted."""
    test_settings = Settings(
        HF_TOKEN="hf_token",
        EMBEDDING_MAX_RETRIES=1,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    mock_resp_429 = MagicMock(status_code=429, headers={"Retry-After": "0"})

    with patch("time.sleep"):
        with patch("httpx.Client.post", return_value=mock_resp_429) as mock_post:
            with pytest.raises(RuntimeError, match="rate limit or service unavailable"):
                provider.embed_text("test")
            assert mock_post.call_count == 2  # Initial + 1 retry


def test_hf_embedding_provider_503_retry():
    """Verify HTTP 503 service unavailable triggers retry and succeeds."""
    test_settings = Settings(
        HF_TOKEN="hf_token",
        EMBEDDING_MAX_RETRIES=2,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    mock_resp_503 = MagicMock(status_code=503, headers={})
    mock_resp_200 = MagicMock(status_code=200, json=lambda: [_make_dummy_vector(384)])

    with patch("time.sleep"):
        with patch("httpx.Client.post", side_effect=[mock_resp_503, mock_resp_200]):
            res = provider.embed_text("test")
            assert len(res) == 384


def test_hf_embedding_provider_timeout_retry():
    """Verify network timeout triggers retry and raises error when exhausted."""
    test_settings = Settings(
        HF_TOKEN="hf_token",
        EMBEDDING_MAX_RETRIES=1,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    with patch("time.sleep"):
        with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timed out")):
            with pytest.raises(RuntimeError, match="failed after 2 attempts: TimeoutException"):
                provider.embed_text("test")


def test_hf_embedding_provider_dimension_validation():
    """Verify vectors with incorrect dimensionality (not 384) are rejected."""
    test_settings = Settings(
        HF_TOKEN="hf_token",
        EMBEDDING_DIMENSION=384,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    # Return 256-D vector instead of 384-D
    mock_resp = MagicMock(status_code=200, json=lambda: [_make_dummy_vector(256)])

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ValueError, match="Vector dimension mismatch: expected 384, got 256"):
            provider.embed_text("test")


def test_hf_embedding_provider_non_finite_validation():
    """Verify vectors with NaN or Inf floats are rejected."""
    test_settings = Settings(
        HF_TOKEN="hf_token",
        EMBEDDING_DIMENSION=384,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    bad_vec = _make_dummy_vector(384)
    bad_vec[10] = float("nan")
    mock_resp = MagicMock(status_code=200, json=lambda: [bad_vec])

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(ValueError, match="Vector contains invalid or non-finite value"):
            provider.embed_text("test")


def test_hf_embedding_provider_token_level_mean_pooling():
    """Verify 3D token matrices are correctly mean-pooled into a 1D vector."""
    test_settings = Settings(
        HF_TOKEN="hf_token",
        EMBEDDING_DIMENSION=384,
    )
    provider = HuggingFaceEmbeddingProvider(test_settings)

    # 3D token matrix: 2 tokens, each 384-D
    token_1 = [0.2] * 384
    token_2 = [0.4] * 384
    mock_resp = MagicMock(status_code=200, json=lambda: [[[token_1, token_2]]])

    with patch("httpx.Client.post", return_value=mock_resp):
        vec = provider.embed_text("test")
        assert len(vec) == 384
        # Mean is 0.3, normalized to unit length
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4


def test_reembed_logs_utility(db_session):
    """Verify reembed_logs safely iterates logs and persists updated vectors."""
    # Insert two sample processed logs
    log1 = ProcessedLog(
        id=uuid.uuid4(),
        source_event_id="evt-reembed-1",
        timestamp=datetime.now(timezone.utc),
        service="order-service",
        environment="production",
        severity="ERROR",
        category="DATABASE",
        raw_message="Connection pool exhausted",
        normalized_message="Connection pool exhausted",
        template="Connection pool exhausted",
    )
    log2 = ProcessedLog(
        id=uuid.uuid4(),
        source_event_id="evt-reembed-2",
        timestamp=datetime.now(timezone.utc),
        service="payment-service",
        environment="production",
        severity="CRITICAL",
        category="DATABASE",
        raw_message="Database host unreachable",
        normalized_message="Database host unreachable",
        template="Database host unreachable",
    )
    db_session.add_all([log1, log2])
    db_session.commit()

    service = EmbeddingService(provider=MockEmbeddingProvider())
    reembedded = service.reembed_logs(db=db_session, batch_size=2)
    assert reembedded == 2

    # Verify embeddings exist in database
    embeddings = db_session.query(LogEmbedding).all()
    assert len(embeddings) == 2
    assert all(e.dimension == 384 for e in embeddings)


def test_no_sentence_transformers_or_torch_in_runtime():
    """Verify that sentence_transformers and torch are not required in runtime path."""
    # Ensure neither module is imported as part of embedding service
    assert "sentence_transformers" not in sys.modules
