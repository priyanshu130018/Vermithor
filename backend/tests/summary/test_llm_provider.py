import json
import pytest
import httpx
from backend.app.common.config import Settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory
from backend.app.summary.llm.huggingface_provider import HuggingFaceProvider


def test_huggingface_provider_generate_success(monkeypatch):
    """Verify HuggingFaceProvider issues correct authenticated request and parses choices[0].message.content."""
    settings = Settings(
        LLM_PROVIDER="huggingface",
        HF_TOKEN="hf_test_secret_token_12345",
        HF_MODEL="meta-llama/Llama-3.1-8B-Instruct",
        HF_BASE_URL="https://router.huggingface.co/v1",
        LLM_TIMEOUT_SECONDS=30,
        MAX_OUTPUT_TOKENS=1000,
    )
    provider = HuggingFaceProvider(settings)

    captured_requests = []

    class MockResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"executive_summary": "HF test summary"}),
                        },
                        "finish_reason": "stop",
                    }
                ],
            }

    def mock_post(self, url, headers=None, json=None):
        captured_requests.append({"url": url, "headers": headers, "json": json})
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    result = provider.generate("Summarize incident INC-001")
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["url"] == "https://router.huggingface.co/v1/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer hf_test_secret_token_12345"
    assert req["headers"]["Content-Type"] == "application/json"
    assert req["json"]["model"] == "meta-llama/Llama-3.1-8B-Instruct"
    assert req["json"]["temperature"] == 0.1
    assert req["json"]["max_tokens"] == 1000
    assert req["json"]["messages"][0]["content"] == "Summarize incident INC-001"

    parsed = json.loads(result)
    assert parsed["executive_summary"] == "HF test summary"


def test_huggingface_provider_missing_token():
    """Verify ValueError is raised when HF_TOKEN is not configured."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN=None)
    provider = HuggingFaceProvider(settings)
    with pytest.raises(ValueError, match="HF_TOKEN is not configured"):
        provider.generate("Test prompt")


def test_huggingface_provider_auth_failure_401(monkeypatch):
    """Verify HTTP 401 returns clear authentication error without exposing token."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="invalid_token")
    provider = HuggingFaceProvider(settings)

    class Mock401Response:
        status_code = 401
        headers = {}
        text = "Unauthorized: Invalid credentials"

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: Mock401Response())

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("Test prompt")
    assert "authentication failed (HTTP 401)" in str(exc_info.value)
    assert "invalid_token" not in str(exc_info.value)


def test_huggingface_provider_rate_limit_429(monkeypatch):
    """Verify rate limit 429 retries within bounds and raises clean error when exceeded."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="valid_token")
    provider = HuggingFaceProvider(settings)

    class Mock429Response:
        status_code = 429
        headers = {"Retry-After": "0.1"}
        text = "Rate limit exceeded"

    attempts = [0]
    def mock_post(self, url, headers=None, json=None):
        attempts[0] += 1
        return Mock429Response()

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    with pytest.raises(RuntimeError, match="rate limit reached"):
        provider.generate("Test prompt")
    # Verified bounded retries (attempt 1 + 2 retries = 3 attempts total)
    assert attempts[0] == 3


def test_huggingface_provider_timeout(monkeypatch):
    """Verify TimeoutException translates into TimeoutError."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="valid_token", LLM_TIMEOUT_SECONDS=5)
    provider = HuggingFaceProvider(settings)

    def mock_post_timeout(self, url, headers=None, json=None):
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(httpx.Client, "post", mock_post_timeout)

    with pytest.raises(TimeoutError, match="timed out"):
        provider.generate("Test prompt")


def test_huggingface_provider_empty_response(monkeypatch):
    """Verify empty choices or empty content raises RuntimeError."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="valid_token")
    provider = HuggingFaceProvider(settings)

    class MockEmptyResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {"choices": [{"message": {"content": ""}}]}

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: MockEmptyResponse())

    with pytest.raises(RuntimeError, match="empty message content"):
        provider.generate("Test prompt")


def test_huggingface_provider_is_available(monkeypatch):
    """Verify is_available performs lightweight authenticated check."""
    # Without token
    provider_no_token = HuggingFaceProvider(Settings(HF_TOKEN=None))
    assert provider_no_token.is_available() is False

    # With valid token and 200 response
    provider_with_token = HuggingFaceProvider(Settings(HF_TOKEN="valid_test_token"))
    class MockGet200:
        status_code = 200
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, headers=None: MockGet200())
    assert provider_with_token.is_available() is True

    # With token and 401 response
    class MockGet401:
        status_code = 401
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, headers=None: MockGet401())
    assert provider_with_token.is_available() is False


def test_provider_factory_selection():
    """Verify ProviderFactory selects HuggingFaceProvider and rejects unsupported providers."""
    ProviderFactory.reset_provider()
    hf_settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="test_token")
    provider = ProviderFactory.get_provider(hf_settings)
    assert isinstance(provider, HuggingFaceProvider)
    assert provider.get_provider_name() == "huggingface"

    ProviderFactory.reset_provider()
    bad_settings = Settings(LLM_PROVIDER="unsupported_custom_provider")
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        ProviderFactory.get_provider(bad_settings)

    ProviderFactory.reset_provider()


def test_provider_factory_override(fake_llm):
    """Verify factory returns overridden test provider."""
    provider = ProviderFactory.get_provider()
    assert provider.get_provider_name() == "fake_llm"


def test_huggingface_provider_payment_required_402(monkeypatch):
    """Verify HTTP 402 raises clean error highlighting prepaid credits and billing URL."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="valid_token")
    provider = HuggingFaceProvider(settings)

    class Mock402Response:
        status_code = 402
        headers = {"content-type": "application/json"}
        def json(self):
            return {"error": "You have no remaining credits. Purchase pre-paid credits to continue."}

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: Mock402Response())

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("Test prompt")
    assert "PrepaidCreditsRequired" in str(exc_info.value)
    assert "https://huggingface.co/settings/billing" in str(exc_info.value)


def test_huggingface_provider_model_not_found_404(monkeypatch):
    """Verify HTTP 404 returns clean error when model is not available on router."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="valid_token", HF_MODEL="nonexistent/model")
    provider = HuggingFaceProvider(settings)

    class Mock404Response:
        status_code = 404
        headers = {}
        text = "Model nonexistent/model not found"

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: Mock404Response())

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("Test prompt")
    assert "not found on router (HTTP 404)" in str(exc_info.value)


def test_summary_service_parse_json_with_markdown_fences():
    """Verify _parse_json properly extracts JSON wrapped in markdown codeblocks."""
    from backend.app.summary.services.summary_service import IncidentSummaryService

    svc = IncidentSummaryService()
    raw_markdown = """```json
{
  "executive_summary": "Database saturation detected.",
  "what_happened": "Connections spiked.",
  "probable_root_cause": "Database connection pool exhaustion",
  "confidence": 0.85
}
```"""
    parsed = svc._parse_json(raw_markdown)
    assert parsed["executive_summary"] == "Database saturation detected."
    assert parsed["confidence"] == 0.85

