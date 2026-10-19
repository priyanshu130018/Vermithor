import logging
from typing import Optional

from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.huggingface_provider import HuggingFaceProvider
from backend.app.summary.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)
_provider_instance: Optional[LLMProvider] = None


class ProviderFactory:
    """Factory to instantiate or retrieve configured LLMProvider."""

    _provider_instance: Optional[LLMProvider] = None

    @classmethod
    def get_provider(cls, settings: Optional[Settings] = None) -> LLMProvider:
        global _provider_instance
        if cls._provider_instance is not None:
            return cls._provider_instance
        if _provider_instance is not None:
            return _provider_instance

        cfg = settings or get_settings()
        provider_name = (cfg.LLM_PROVIDER or "").lower().strip()

        if provider_name == "huggingface":
            inst = HuggingFaceProvider(cfg)
            cls._provider_instance = inst
            _provider_instance = inst
            return inst
        elif provider_name == "ollama":
            inst = OllamaProvider(cfg)
            cls._provider_instance = inst
            _provider_instance = inst
            return inst
        else:
            raise ValueError(
                f"Unsupported LLM provider: '{cfg.LLM_PROVIDER}'. "
                f"Supported providers: ['huggingface', 'ollama']"
            )

    @classmethod
    def set_provider(cls, provider: Optional[LLMProvider]) -> None:
        """Override global provider instance (used for testing with FakeLLMProvider)."""
        global _provider_instance
        cls._provider_instance = provider
        _provider_instance = provider

    @classmethod
    def reset_provider(cls) -> None:
        """Reset global provider instance to ensure test isolation."""
        global _provider_instance
        cls._provider_instance = None
        _provider_instance = None
