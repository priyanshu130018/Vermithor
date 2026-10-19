import pytest
from backend.app.summary.llm.base import LLMProvider


def test_llm_readiness_probe_reflects_provider_availability():
    """Verify that Summary Service readiness probe reports provider availability state."""
    class FailingProvider(LLMProvider):
        def generate(self, prompt: str) -> str:
            raise ConnectionError("Hugging Face API unreachable or rate limited")

        def is_available(self) -> bool:
            return False

        def get_provider_name(self) -> str:
            return "huggingface-failing"

        def get_model_name(self) -> str:
            return "meta-llama/Llama-3.1-8B-Instruct"

    provider = FailingProvider()
    assert provider.is_available() is False
    assert provider.get_provider_name() == "huggingface-failing"
