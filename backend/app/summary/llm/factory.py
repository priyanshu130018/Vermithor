from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.huggingface_provider import HuggingFaceProvider
from backend.app.summary.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)
_provider_instance: Optional[LLMProvider] = None
_task_instances: Dict[str, LLMProvider] = {}


class ProviderFactory:
    """
    Factory to instantiate or retrieve configured task-specific LLMProvider.
    Hugging Face Inference Providers is the default cloud LLM backend.
    Supports task-specific routing for:
      - investigation (root-cause analysis & hypothesis evaluation)
      - summary (incident summary & postmortem generation)
      - report_review (report verification & citation validation)
    """

    _provider_instance: Optional[LLMProvider] = None
    _task_instances: Dict[str, LLMProvider] = {}
    _call_history: List[Dict[str, Any]] = []

    @classmethod
    def get_provider(
        cls, settings: Optional[Settings] = None, task: Optional[str] = None
    ) -> LLMProvider:
        global _provider_instance
        # Global override takes precedence (e.g. mock in unit tests)
        if cls._provider_instance is not None:
            return cls._provider_instance
        if _provider_instance is not None:
            return _provider_instance

        cfg = settings or get_settings()
        task_key = (task or "general").strip().lower()

        if task_key in cls._task_instances:
            return cls._task_instances[task_key]

        provider_name = (cfg.LLM_PROVIDER or "huggingface").lower().strip()

        if provider_name == "huggingface":
            inst = HuggingFaceProvider(cfg, task=task_key)
            cls._task_instances[task_key] = inst
            return inst
        elif provider_name == "ollama":
            logger.warning(
                "Ollama is deprecated as an active runtime provider in favor of cloud Hugging Face Inference Providers."
            )
            inst = OllamaProvider(cfg)
            cls._task_instances[task_key] = inst
            return inst
        else:
            raise ValueError(
                f"Unsupported LLM provider: '{cfg.LLM_PROVIDER}'. "
                f"Configured cloud backend is 'huggingface'."
            )

    @classmethod
    def get_provider_for_task(
        cls, task: str, settings: Optional[Settings] = None
    ) -> LLMProvider:
        """Explicit task-routed provider accessor."""
        return cls.get_provider(settings=settings, task=task)

    @classmethod
    def set_provider(cls, provider: Optional[LLMProvider]) -> None:
        """Override global provider instance (used for testing with FakeLLMProvider)."""
        global _provider_instance
        cls._provider_instance = provider
        _provider_instance = provider
        cls._task_instances.clear()

    @classmethod
    def reset_provider(cls) -> None:
        """Reset global provider instance and task caches to ensure test isolation."""
        global _provider_instance
        cls._provider_instance = None
        _provider_instance = None
        cls._task_instances.clear()

    @classmethod
    def record_call(cls, record: Dict[str, Any]) -> None:
        """Record model call telemetry into global audit log."""
        cls._call_history.append(record)

    @classmethod
    def get_call_history(cls) -> List[Dict[str, Any]]:
        """Retrieve audit log of all model calls."""
        return list(cls._call_history)

    @classmethod
    def clear_call_history(cls) -> None:
        """Clear call history."""
        cls._call_history.clear()
