import logging
from typing import Optional

from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)
_provider_instance: Optional[LLMProvider] = None


class ProviderFactory:
    """Factory to instantiate or retrieve configured LLMProvider."""

    @staticmethod
    def get_provider(settings: Optional[Settings] = None) -> LLMProvider:
        global _provider_instance
        if _provider_instance is not None:
            return _provider_instance

        cfg = settings or get_settings()
        provider_name = cfg.LLM_PROVIDER.lower()

        if provider_name == "ollama":
            _provider_instance = OllamaProvider(cfg)
            return _provider_instance
        else:
            logger.warning("Unknown LLM provider '%s', defaulting to OllamaProvider", provider_name)
            _provider_instance = OllamaProvider(cfg)
            return _provider_instance

    @staticmethod
    def set_provider(provider: LLMProvider) -> None:
        """Override global provider instance (used for testing with FakeLLMProvider)."""
        global _provider_instance
        _provider_instance = provider
