import logging
from typing import Optional
import httpx

from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Local Ollama HTTP LLM provider."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = self.settings.LLM_MODEL
        self.timeout = self.settings.LLM_TIMEOUT_SECONDS

    def get_provider_name(self) -> str:
        return "ollama"

    def get_model_name(self) -> str:
        return self.model

    def is_available(self) -> bool:
        """Check if Ollama service is reachable."""
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str) -> str:
        """Send prompt to Ollama /api/generate requesting JSON output."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_predict": self.settings.MAX_OUTPUT_TOKENS,
                "temperature": 0.1,  # Low temperature for strict factual grounding
            },
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("response", "")
                raise RuntimeError(f"Ollama returned HTTP {res.status_code}: {res.text}")
        except httpx.TimeoutException as exc:
            logger.error("Ollama generation timed out after %d seconds: %s", self.timeout, exc)
            raise TimeoutError(f"LLM generation timed out after {self.timeout}s") from exc
        except Exception as exc:
            logger.error("Error communicating with Ollama: %s", exc)
            raise RuntimeError(f"Ollama provider failed: {exc}") from exc
