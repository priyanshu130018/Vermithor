import logging
import time
from typing import Optional
import httpx

from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class HuggingFaceProvider(LLMProvider):
    """
    Hugging Face Inference Providers API client using OpenAI-compatible chat completions.
    Default endpoint: https://router.huggingface.co/v1/chat/completions
    Default model: meta-llama/Llama-3.1-8B-Instruct (hosted on HF Inference Providers router)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = (self.settings.HF_BASE_URL or "https://router.huggingface.co/v1").rstrip("/")
        self.model = self.settings.HF_MODEL or "meta-llama/Llama-3.1-8B-Instruct"
        self.timeout = self.settings.LLM_TIMEOUT_SECONDS
        self.token = self.settings.HF_TOKEN

    def get_provider_name(self) -> str:
        return "huggingface"

    def get_model_name(self) -> str:
        return self.model

    def is_available(self) -> bool:
        """
        Bounded, authenticated check verifying HF router reachability and token validity.
        Queries the model listing endpoint without triggering expensive generation calls.

        Limitation Note: While this validates network connectivity, API authentication,
        and router readiness, specific serverless endpoints may still experience transient
        provider load or cold starts during actual generation.
        """
        if not self.token or not self.token.strip():
            return False

        url = f"{self.base_url}/models"
        headers = {
            "Authorization": f"Bearer {self.token.strip()}",
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
        Sends the incident-summary prompt as a chat completion request to Hugging Face.
        Parses choices[0].message.content from the OpenAI-compatible response.
        Enforces low-temperature (0.1) for deterministic factual grounding.
        Handles authentication failures, rate limits, timeouts, and empty responses.
        """
        if not self.token or not self.token.strip():
            raise ValueError(
                "HF_TOKEN is not configured. Please configure HF_TOKEN in your environment or .env file."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.token.strip()}",
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
            "temperature": 0.1,  # Strict low temperature for factual grounding
            "max_tokens": self.settings.MAX_OUTPUT_TOKENS,
        }

        max_retries = 2
        last_exc: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    res = client.post(url, headers=headers, json=payload)

                    if res.status_code == 200:
                        data = res.json()
                        choices = data.get("choices")
                        if not choices or not isinstance(choices, list) or len(choices) == 0:
                            raise RuntimeError("Hugging Face API returned empty choices in completion response.")

                        message = choices[0].get("message", {})
                        content = message.get("content")
                        if not content or not isinstance(content, str) or not content.strip():
                            raise RuntimeError("Hugging Face API returned empty message content in completion response.")

                        return content.strip()

                    # Handle 401 Unauthorized
                    if res.status_code == 401:
                        logger.error("Hugging Face authentication failed (HTTP 401). Invalid or expired token.")
                        raise RuntimeError("Hugging Face authentication failed (HTTP 401). Please verify your HF_TOKEN.")

                    # Handle 402 Payment Required / Prepaid Credits Exhausted
                    if res.status_code == 402:
                        error_data = {}
                        try:
                            error_data = res.json()
                        except Exception:
                            pass
                        error_msg = error_data.get("error", "Prepaid credits required") if isinstance(error_data, dict) else res.text[:200]
                        logger.error("Hugging Face account has no remaining credits (HTTP 402): %s", error_msg)
                        raise RuntimeError(
                            "Hugging Face Inference Providers requires prepaid credits or PRO subscription (HTTP 402: PrepaidCreditsRequired). "
                            f"Check remaining credits or billing settings at https://huggingface.co/settings/billing. Error: {error_msg}"
                        )

                    # Handle 404 Model Not Found
                    if res.status_code == 404:
                        logger.error("Hugging Face model '%s' not found on router (HTTP 404).", self.model)
                        raise RuntimeError(f"Hugging Face model '{self.model}' not found on router (HTTP 404). Verify HF_MODEL.")

                    # Handle 429 Rate Limiting
                    if res.status_code == 429:
                        retry_after = res.headers.get("Retry-After")
                        logger.warning(
                            "Hugging Face rate limit reached (HTTP 429). Attempt %d/%d.",
                            attempt + 1,
                            max_retries + 1,
                        )
                        if attempt < max_retries:
                            sleep_seconds = 1.0
                            if retry_after:
                                try:
                                    sleep_seconds = min(max(float(retry_after), 0.5), 3.0)
                                except ValueError:
                                    sleep_seconds = 1.0
                            time.sleep(sleep_seconds)
                            continue
                        raise RuntimeError("Hugging Face API rate limit reached (HTTP 429). Please retry later.")

                    # Handle 502 / 503 / 504 Service Unavailable (Cold Start / Model Loading)
                    if res.status_code in (502, 503, 504) and attempt < max_retries:
                        logger.warning(
                            "Hugging Face transient service error (HTTP %d). Retrying (%d/%d)...",
                            res.status_code,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(1.0)
                        continue

                    # Other HTTP error
                    sanitized_error = res.text[:200]
                    raise RuntimeError(f"Hugging Face API returned HTTP {res.status_code}: {sanitized_error}")

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.error(
                    "Hugging Face generation timed out after %d seconds (attempt %d/%d)",
                    self.timeout,
                    attempt + 1,
                    max_retries + 1,
                )
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                raise TimeoutError(f"LLM generation timed out after {self.timeout}s") from exc

            except httpx.RequestError as exc:
                last_exc = exc
                logger.error("Network communication error with Hugging Face: %s", exc.__class__.__name__)
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                raise RuntimeError(f"Failed to communicate with Hugging Face Inference API: {exc}") from exc

        if last_exc:
            raise last_exc
        raise RuntimeError("Hugging Face generation failed after retries.")
