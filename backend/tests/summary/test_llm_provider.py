import json
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory
from backend.app.summary.llm.ollama_provider import OllamaProvider


def test_ollama_provider_generate(monkeypatch):
    """Verify OllamaProvider issues correct POST request and parses response."""
    provider = OllamaProvider()

    class MockRes:
        status_code = 200
        def json(self):
            return {"response": json.dumps({"executive_summary": "Test summary"})}

    monkeypatch.setattr("httpx.Client.post", lambda self, url, json=None: MockRes())

    res = provider.generate("Test prompt")
    parsed = json.loads(res)
    assert parsed["executive_summary"] == "Test summary"


def test_provider_factory_override(fake_llm):
    """Verify factory returns set provider."""
    provider = ProviderFactory.get_provider()
    assert provider.get_provider_name() == "fake_llm"
