from abc import ABC, abstractmethod
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Tuple


class LLMProvider(ABC):
    """Abstract interface for cloud LLM synthesis and investigation providers."""

    @abstractmethod
    def generate(self, prompt: str, task: Optional[str] = None) -> str:
        """Generate response text from input prompt for an optional intelligence task."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether provider and model are available."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider identifier (e.g. 'huggingface')."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return model identifier (e.g. 'meta-llama/Llama-3.1-8B-Instruct')."""
        pass

    def get_task(self) -> str:
        """Return the assigned intelligence task for this provider instance."""
        return "general"

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Return audit trail of model calls executed by this provider instance."""
        return []

    def generate_with_telemetry(
        self, prompt: str, task: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Execute generation while recording client-observed request latency,
        task routing, provider ID, model ID, fallback status, and errors.
        """
        active_task = task or self.get_task()
        start_time = time.perf_counter()
        try:
            content = self.generate(prompt, task=active_task)
            latency_sec = time.perf_counter() - start_time
            record = {
                "provider": self.get_provider_name(),
                "actual_model_id": self.get_model_name(),
                "task": active_task,
                "request_latency_ms": round(latency_sec * 1000.0, 2),
                "request_latency_seconds": round(latency_sec, 4),
                "fallback_status": False,
                "errors": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return content, record
        except Exception as exc:
            latency_sec = time.perf_counter() - start_time
            record = {
                "provider": self.get_provider_name(),
                "actual_model_id": self.get_model_name(),
                "task": active_task,
                "request_latency_ms": round(latency_sec * 1000.0, 2),
                "request_latency_seconds": round(latency_sec, 4),
                "fallback_status": True,
                "errors": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            raise exc
