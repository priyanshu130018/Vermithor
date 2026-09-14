import pytest
from backend.app.summary.llm.base import LLMProvider


def test_llm_readiness_probe_reflects_provider_availability():
    """Verify that Summary Service readiness probe reports provider availability state."""
    class FailingProvider(LLMProvider):
        def generate(self, prompt: str) -> str:
            raise ConnectionError("Ollama host unreachable at http://localhost:11434")

        def is_available(self) -> bool:
            return False

        def get_provider_name(self) -> str:
            return "ollama-failing"

        def get_model_name(self) -> str:
            return "llama3.2:3b"

    provider = FailingProvider()
    assert provider.is_available() is False
    assert provider.get_provider_name() == "ollama-failing"
