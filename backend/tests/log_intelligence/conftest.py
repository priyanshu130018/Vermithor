import os
import pytest
from backend.app.log_intelligence.embedding.service import get_embedding_service
from backend.app.log_intelligence.embedding.mock_provider import MockEmbeddingProvider

os.environ["SERVICE_UNDER_TEST"] = "log-intelligence"
os.environ["EMBEDDING_PROVIDER"] = "mock"


@pytest.fixture(autouse=True)
def setup_mock_embeddings():
    """Ensure all log intelligence tests run offline using deterministic MockEmbeddingProvider."""
    get_embedding_service(provider=MockEmbeddingProvider())
    yield
