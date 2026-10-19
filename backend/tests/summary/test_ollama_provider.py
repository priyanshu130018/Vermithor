import json
import pytest
import httpx
from fastapi.testclient import TestClient

from backend.app.common.config import Settings
from backend.app.main import app
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory
from backend.app.summary.llm.ollama_provider import OllamaProvider
from backend.app.summary.services.summary_service import IncidentSummaryService


class MockIncidentClient:
    def get_incident(self, key):
        return {
            "incident_key": key,
            "service": "payment-api",
            "severity": "CRITICAL",
            "status": "DETECTED",
            "title": "Payment API Connection Pool Exhaustion",
            "description": "Pool saturated at 100% active connections following v2.8.4 deployment.",
            "environment": "production",
            "started_at": "2026-10-13T14:04:00Z",
        }


class MockRCAClient:
    def get_rca_reports(self, top_k=1):
        return [
            {
                "primary_root_cause": "PostgreSQL Connection Pool Exhaustion caused by connection leak under load.",
                "primary_confidence": 0.88,
                "candidates": [
                    {
                        "cause": "PostgreSQL Connection Pool Exhaustion caused by connection leak under load.",
                        "confidence": 0.88,
                    }
                ],
            }
        ]


class MockRetrievalClient:
    def get_rag_context(self, incident_key=None, top_k=10):
        return {
            "context": [
                {
                    "source_id": "evt-db-01",
                    "source_type": "LOG",
                    "title": "Pool saturated log",
                }
            ]
        }


class MockDB:
    def execute(self, stmt):
        class ScalarResult:
            def scalar_one_or_none(self):
                return None
            def scalar(self):
                return 1
        return ScalarResult()

    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        import uuid
        obj.id = uuid.uuid4()
        obj.created_at = "2026-10-13T09:30:00Z"
        obj.updated_at = "2026-10-13T09:30:00Z"

    def get_bind(self):
        class Dialect:
            name = "sqlite"
        class Bind:
            dialect = Dialect()
        return Bind()


def test_ollama_provider_generate_success(monkeypatch):
    """Verify OllamaProvider issues structured JSON request to /api/chat and extracts content."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_TIMEOUT_SECONDS=45,
        MAX_OUTPUT_TOKENS=1500,
    )
    provider = OllamaProvider(settings)

    captured_requests = []

    class MockResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {
                "model": "llama3.2",
                "created_at": "2026-10-13T09:30:00Z",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"executive_summary": "Ollama test summary"}),
                },
                "done": True,
            }

    def mock_post(self, url, headers=None, json=None):
        captured_requests.append({"url": url, "headers": headers, "json": json})
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    result = provider.generate("Summarize incident INC-1042")
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["url"] == "http://localhost:11434/api/chat"
    assert req["headers"]["Content-Type"] == "application/json"
    assert req["json"]["model"] == "llama3.2"
    assert req["json"]["stream"] is False
    assert req["json"]["format"] == "json"
    assert req["json"]["options"]["temperature"] == 0.1
    assert req["json"]["options"]["num_predict"] == 1500
    assert req["json"]["messages"][0]["content"] == "Summarize incident INC-1042"

    parsed = json.loads(result)
    assert parsed["executive_summary"] == "Ollama test summary"


def test_ollama_provider_timeout(monkeypatch):
    """Verify TimeoutException translates into clean TimeoutError."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_TIMEOUT_SECONDS=5,
    )
    provider = OllamaProvider(settings)

    def mock_post_timeout(self, url, headers=None, json=None):
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(httpx.Client, "post", mock_post_timeout)

    with pytest.raises(TimeoutError, match="timed out"):
        provider.generate("Test prompt")


def test_ollama_provider_connection_failure(monkeypatch):
    """Verify ConnectError produces clear error with setup guidance without leaking secrets."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
    )
    provider = OllamaProvider(settings)

    def mock_post_connect_error(self, url, headers=None, json=None):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.Client, "post", mock_post_connect_error)

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("Test prompt")
    assert "Failed to connect to Ollama server at http://localhost:11434" in str(exc_info.value)
    assert "ollama serve" in str(exc_info.value)


def test_ollama_provider_model_not_found_404(monkeypatch):
    """Verify HTTP 404 returns actionable guidance with model pull command."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="nonexistent-model",
    )
    provider = OllamaProvider(settings)

    class Mock404Response:
        status_code = 404
        headers = {}
        text = "model 'nonexistent-model' not found"

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: Mock404Response())

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("Test prompt")
    assert "Ollama model 'nonexistent-model' not found" in str(exc_info.value)
    assert "ollama pull nonexistent-model" in str(exc_info.value)


def test_ollama_provider_empty_message(monkeypatch):
    """Verify empty choices or content raises RuntimeError."""
    settings = Settings(LLM_PROVIDER="ollama")
    provider = OllamaProvider(settings)

    class MockEmptyResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {"message": {"content": ""}}

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: MockEmptyResponse())

    with pytest.raises(RuntimeError, match="empty message content"):
        provider.generate("Test prompt")


def test_ollama_provider_is_available(monkeypatch):
    """Verify is_available performs lightweight check on /api/tags."""
    provider = OllamaProvider(Settings(OLLAMA_BASE_URL="http://localhost:11434"))

    # When 200 OK
    class Mock200:
        status_code = 200
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, headers=None: Mock200())
    assert provider.is_available() is True

    # When 500
    class Mock500:
        status_code = 500
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, headers=None: Mock500())
    assert provider.is_available() is False

    # When ConnectError
    def mock_get_error(self, url, headers=None):
        raise httpx.ConnectError("Connection refused")
    monkeypatch.setattr(httpx.Client, "get", mock_get_error)
    assert provider.is_available() is False


def test_provider_factory_selection_ollama():
    """Verify ProviderFactory selects OllamaProvider when configured."""
    ProviderFactory.reset_provider()
    ollama_settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
    )
    provider = ProviderFactory.get_provider(ollama_settings)
    assert isinstance(provider, OllamaProvider)
    assert provider.get_provider_name() == "ollama"
    assert provider.get_model_name() == "llama3.2"
    ProviderFactory.reset_provider()


def test_ollama_end_to_end_success_is_fallback_false(monkeypatch):
    """Verify successful Ollama generation produces validated summary with is_fallback=False."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_FALLBACK_ENABLED=True,
    )
    ollama_provider = OllamaProvider(settings)

    valid_json = {
        "executive_summary": "Payment API connection pool exhaustion caused service disruption.",
        "what_happened": "At 14:04 UTC, payment-api connection pool hit 100% saturation following v2.8.4 deployment.",
        "probable_root_cause": "PostgreSQL Connection Pool Exhaustion caused by connection leak under load.",
        "impact": {
            "services": ["payment-api"],
            "severity": "CRITICAL",
            "description": "Payment requests timed out with HTTP 500 errors.",
        },
        "timeline": [
            {"timestamp": "2026-10-13T14:04:00Z", "event": "Pool reached 100% active", "source": "LOG"}
        ],
        "evidence": [
            {
                "claim": "Connection pool saturated",
                "source_type": "LOG",
                "source_id": "evt-db-01",
                "support": "Connection pool exhausted",
            }
        ],
        "remediation": [
            {"action": "Increase connection pool size", "priority": "HIGH", "reason": "Prevent exhaustion"}
        ],
        "confidence": 0.88,
        "limitations": [],
    }

    class MockSuccessResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(valid_json),
                }
            }

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: MockSuccessResponse())

    service = IncidentSummaryService(
        incident_client=MockIncidentClient(),
        rca_client=MockRCAClient(),
        retrieval_client=MockRetrievalClient(),
        llm_provider=ollama_provider,
        settings=settings,
    )

    result = service.generate_summary_for_incident(
        db=MockDB(),
        incident_key="INC-2026-1042",
        regenerate=True,
    )

    assert result.is_fallback is False
    assert result.model_provider == "ollama"
    assert result.model_name == "llama3.2"
    assert result.executive_summary == "Payment API connection pool exhaustion caused service disruption."
    assert result.status.value == "COMPLETED"


def test_ollama_connection_failure_activates_deterministic_fallback(monkeypatch):
    """Verify Ollama connection failure triggers deterministic fallback with is_fallback=True when fallback is enabled."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_FALLBACK_ENABLED=True,
    )
    ollama_provider = OllamaProvider(settings)

    def mock_connect_error(self, url, headers=None, json=None):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.Client, "post", mock_connect_error)

    service = IncidentSummaryService(
        incident_client=MockIncidentClient(),
        rca_client=MockRCAClient(),
        retrieval_client=MockRetrievalClient(),
        llm_provider=ollama_provider,
        settings=settings,
    )

    result = service.generate_summary_for_incident(
        db=MockDB(),
        incident_key="INC-2026-1042",
        regenerate=True,
    )

    assert result.is_fallback is True
    assert result.model_provider == "fallback"
    assert result.model_name == "deterministic_rules"
    assert any("deterministic rules engine" in lim.lower() for lim in result.limitations)


def test_ollama_connection_failure_raises_when_fallback_disabled(monkeypatch):
    """Verify Ollama connection failure raises RuntimeError when fallback is disabled."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_FALLBACK_ENABLED=False,
    )
    ollama_provider = OllamaProvider(settings)

    def mock_connect_error(self, url, headers=None, json=None):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.Client, "post", mock_connect_error)

    service = IncidentSummaryService(
        incident_client=MockIncidentClient(),
        rca_client=MockRCAClient(),
        retrieval_client=MockRetrievalClient(),
        llm_provider=ollama_provider,
        settings=settings,
    )

    with pytest.raises(RuntimeError, match="Incident summary generation failed"):
        service.generate_summary_for_incident(
            db=MockDB(),
            incident_key="INC-2026-1042",
            regenerate=True,
        )


def test_ollama_malformed_json_activates_fallback(monkeypatch):
    """Verify malformed JSON from Ollama activates deterministic fallback."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_FALLBACK_ENABLED=True,
    )
    ollama_provider = OllamaProvider(settings)

    class MockMalformedResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {
                "message": {
                    "role": "assistant",
                    "content": "Not valid JSON output from model",
                }
            }

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: MockMalformedResponse())

    service = IncidentSummaryService(
        incident_client=MockIncidentClient(),
        rca_client=MockRCAClient(),
        retrieval_client=MockRetrievalClient(),
        llm_provider=ollama_provider,
        settings=settings,
    )

    result = service.generate_summary_for_incident(
        db=MockDB(),
        incident_key="INC-2026-1042",
        regenerate=True,
    )

    assert result.is_fallback is True
    assert result.model_provider == "fallback"


def test_readiness_probe_distinguishes_ollama_connectivity():
    """Verify /ready clearly reports Ollama connectivity while keeping app status healthy."""
    client = TestClient(app)

    # 1. Health liveness is always healthy
    h_res = client.get("/health")
    assert h_res.status_code == 200
    assert h_res.json()["status"] == "healthy"

    # 2. When provider is available
    class MockAvailableProvider(LLMProvider):
        def generate(self, prompt: str) -> str: return "{}"
        def is_available(self) -> bool: return True
        def get_provider_name(self) -> str: return "ollama"
        def get_model_name(self) -> str: return "llama3.2"

    ProviderFactory.set_provider(MockAvailableProvider())
    r_res = client.get("/ready")
    assert r_res.status_code == 200
    data = r_res.json()
    assert data["status"] in ["ready", "degraded"]
    assert data["provider_available"] is True
    assert data["llm_connectivity"] == "connected"
    assert data["llm_model"] == "llama3.2"

    # 3. When provider is unreachable (Ollama offline)
    class MockUnreachableProvider(LLMProvider):
        def generate(self, prompt: str) -> str: raise httpx.ConnectError("Offline")
        def is_available(self) -> bool: return False
        def get_provider_name(self) -> str: return "ollama"
        def get_model_name(self) -> str: return "llama3.2"

    ProviderFactory.set_provider(MockUnreachableProvider())
    r_res2 = client.get("/ready")
    assert r_res2.status_code == 200
    data2 = r_res2.json()
    # App is still ready because of deterministic fallback
    assert data2["status"] in ["ready", "degraded"]
    # But Ollama connectivity is clearly marked as unreachable
    assert data2["provider_available"] is False
    assert data2["llm_connectivity"] == "unreachable"

    ProviderFactory.reset_provider()


def test_ollama_invalid_schema_json_activates_fallback(monkeypatch):
    """Verify that when Ollama returns valid JSON that violates summary schema, fallback is safely activated."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_FALLBACK_ENABLED=True,
    )
    ollama_provider = OllamaProvider(settings)

    class MockInvalidSchemaResponse:
        status_code = 200
        headers = {}
        def json(self):
            return {
                "message": {
                    "role": "assistant",
                    # Valid JSON syntax, but missing required executive_summary, what_happened, etc.
                    "content": json.dumps({"unknown_field": "some output", "number": 42}),
                }
            }

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, headers=None, json=None: MockInvalidSchemaResponse())

    service = IncidentSummaryService(
        incident_client=MockIncidentClient(),
        rca_client=MockRCAClient(),
        retrieval_client=MockRetrievalClient(),
        llm_provider=ollama_provider,
        settings=settings,
    )

    result = service.generate_summary_for_incident(
        db=MockDB(),
        incident_key="INC-2026-1042",
        regenerate=True,
    )

    assert result.is_fallback is True
    assert result.model_provider == "fallback"
    assert result.model_name == "deterministic_rules"
    assert result.status.value == "COMPLETED"
    assert len(result.evidence) >= 1
    assert any("deterministic" in lim.lower() for lim in result.limitations)


def test_ollama_fallback_metadata_and_evidence_grounding(monkeypatch):
    """Verify fallback result conforms strictly to schema and grounds evidence in supplied incident context."""
    settings = Settings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.2",
        LLM_FALLBACK_ENABLED=True,
    )
    ollama_provider = OllamaProvider(settings)

    def mock_timeout(self, url, headers=None, json=None):
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(httpx.Client, "post", mock_timeout)

    service = IncidentSummaryService(
        incident_client=MockIncidentClient(),
        rca_client=MockRCAClient(),
        retrieval_client=MockRetrievalClient(),
        llm_provider=ollama_provider,
        settings=settings,
    )

    result = service.generate_summary_for_incident(
        db=MockDB(),
        incident_key="INC-2026-1042",
        regenerate=True,
    )

    # Validate schema fields
    assert result.is_fallback is True
    assert result.model_provider == "fallback"
    assert result.model_name == "deterministic_rules"
    assert result.executive_summary != ""
    assert result.what_happened != ""
    assert result.probable_root_cause != ""
    assert result.confidence > 0.0
    assert result.impact.severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    assert "payment-api" in result.impact.services
    assert len(result.timeline) >= 1
    assert len(result.evidence) >= 1
    assert len(result.remediation) >= 1
    # Check that limitations explain fallback reason
    assert any("fallback" in lim.lower() or "deterministic" in lim.lower() for lim in result.limitations)


def test_provider_status_endpoint_ollama(client: TestClient, unauthenticated_client: TestClient):
    """Verify /api/v1/summaries/provider/status requires auth and reports metadata without leaking secrets."""
    # 1. Unauthenticated request must be rejected with 401
    unauth_res = unauthenticated_client.get("/api/v1/summaries/provider/status")
    assert unauth_res.status_code == 401

    # 2. Authenticated request succeeds and returns provider status
    res = client.get("/api/v1/summaries/provider/status")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert "model" in data
    assert "available" in data
    assert "status" in data
    assert "fallback_enabled" in data
    # Ensure no secrets leaked
    assert "token" not in data
    assert "password" not in data
    assert "secret" not in data
    assert "url" not in data

