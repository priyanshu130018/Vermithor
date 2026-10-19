import logging
import time
from typing import Optional
import httpx

from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    Local / Self-hosted Ollama API client using the /api/chat endpoint with JSON format enforcement.
    Default endpoint: http://localhost:11434/api/chat (or http://host.docker.internal:11434 from Docker)
    Default model: llama3.2 (or configured OLLAMA_MODEL)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = (self.settings.OLLAMA_BASE_URL or "http://localhost:11434").rstrip("/")
        self.model = self.settings.OLLAMA_MODEL or "llama3.2"
        self.timeout = self.settings.LLM_TIMEOUT_SECONDS
        self.max_tokens = self.settings.MAX_OUTPUT_TOKENS

    def get_provider_name(self) -> str:
        return "ollama"

    def get_model_name(self) -> str:
        return self.model

    def is_available(self) -> bool:
        """
        Lightweight health check verifying Ollama server reachability and responsiveness.
        Queries the /api/tags endpoint with a bounded timeout (3.0s).
        """
        url = f"{self.base_url}/api/tags"
        headers = {
            "User-Agent": "Vermithor-Incident-Intelligence/1.0",
        }
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(url, headers=headers)
                return res.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str) -> str:
        """
        Sends the incident-summary prompt as a chat completion request to Ollama /api/chat.
        Enforces structured JSON output format via Ollama's native 'format: json' mode.
        Enforces low-temperature (0.1) for deterministic factual grounding.
        Handles connection errors, model unavailability, timeouts, and empty responses.
        """
        url = f"{self.base_url}/api/chat"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Vermithor-Incident-Intelligence/1.0",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,  # Low temperature for factual, deterministic output
                "num_predict": self.max_tokens,
            },
        }

        max_retries = 2
        last_exc: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    res = client.post(url, headers=headers, json=payload)

                    if res.status_code == 200:
                        data = res.json()
                        message = data.get("message")
                        if not message or not isinstance(message, dict):
                            raise RuntimeError("Ollama API returned response without 'message' object.")

                        content = message.get("content")
                        if not content or not isinstance(content, str) or not content.strip():
                            raise RuntimeError("Ollama API returned empty message content in completion response.")

                        return content.strip()

                    # Handle 404 Model Not Found
                    if res.status_code == 404:
                        logger.error(
                            "Ollama model '%s' not found or endpoint 404 at %s",
                            self.model,
                            self.base_url,
                        )
                        raise RuntimeError(
                            f"Ollama model '{self.model}' not found on server at {self.base_url} (HTTP 404). "
                            f"Ensure the model is pulled by running 'ollama pull {self.model}' or configure OLLAMA_MODEL."
                        )

                    # Handle 502 / 503 / 504 Service Unavailable (Transient Ollama startup/load)
                    if res.status_code in (502, 503, 504) and attempt < max_retries:
                        logger.warning(
                            "Ollama transient server error (HTTP %d). Retrying (%d/%d)...",
                            res.status_code,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(1.0)
                        continue

                    # Other HTTP error
                    sanitized_error = res.text[:200]
                    raise RuntimeError(f"Ollama API returned HTTP {res.status_code}: {sanitized_error}")

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.error(
                    "Ollama generation timed out after %d seconds (attempt %d/%d)",
                    self.timeout,
                    attempt + 1,
                    max_retries + 1,
                )
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                raise TimeoutError(f"LLM generation timed out after {self.timeout}s") from exc

            except (httpx.ConnectError, httpx.RequestError) as exc:
                last_exc = exc
                logger.error(
                    "Network communication error connecting to Ollama at %s: %s (attempt %d/%d)",
                    self.base_url,
                    exc.__class__.__name__,
                    attempt + 1,
                    max_retries + 1,
                )
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                raise RuntimeError(
                    f"Failed to connect to Ollama server at {self.base_url}: {exc.__class__.__name__}. "
                    "Ensure Ollama is running ('ollama serve') and accessible."
                ) from exc

        if last_exc:
            raise last_exc
        raise RuntimeError("Ollama generation failed after retries.")
