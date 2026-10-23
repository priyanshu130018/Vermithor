from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class HuggingFaceProvider(LLMProvider):
    """
    Cloud-only Hugging Face Inference Providers API client using OpenAI-compatible chat completions.
    Default endpoint: https://router.huggingface.co/v1/chat/completions
    Supports task-specific model routing (investigation, summary, report_review).
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        task: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.settings = settings or get_settings()
        self.task = (task or "general").strip().lower()
        self.base_url = (self.settings.HF_BASE_URL or "https://router.huggingface.co/v1").rstrip("/")
        if model:
            self.model = model
        elif hasattr(self.settings, "get_model_for_task"):
            self.model = self.settings.get_model_for_task(self.task)
        else:
            self.model = self.settings.HF_MODEL or "meta-llama/Llama-3.1-8B-Instruct"

        self.timeout = self.settings.LLM_TIMEOUT_SECONDS
        self.token = self.settings.HF_TOKEN
        self.call_history: List[Dict[str, Any]] = []

    def get_provider_name(self) -> str:
        return "huggingface"

    def get_model_name(self) -> str:
        return self.model

    def get_task(self) -> str:
        return self.task

    def get_call_history(self) -> List[Dict[str, Any]]:
        return list(self.call_history)

    def is_available(self) -> bool:
        """
        Bounded, authenticated check verifying HF router reachability and token validity.
        Queries the model listing endpoint without triggering expensive generation calls.
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

    def generate_with_telemetry(
        self, prompt: str, task: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Execute chat completion request to Hugging Face Inference Providers.
        Measures client-observed request latency (from request start to response headers/body).
        Does not infer or fabricate hidden model reasoning time.
        Records provider, actual model ID, task, latency, fallback status, and errors.
        """
        active_task = (task or self.task).strip().lower()
        active_model = (
            self.settings.get_model_for_task(active_task)
            if hasattr(self.settings, "get_model_for_task") and task
            else self.model
        )

        if not self.token or not self.token.strip():
            err_msg = "HF_TOKEN is not configured. Please configure HF_TOKEN in your environment or .env file."
            record = {
                "provider": "huggingface",
                "actual_model_id": active_model,
                "task": active_task,
                "request_latency_ms": 0.0,
                "request_latency_seconds": 0.0,
                "fallback_status": True,
                "errors": err_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.call_history.append(record)
            raise ValueError(err_msg)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.token.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "Vermithor-Incident-Intelligence/1.0",
        }
        payload = {
            "model": active_model,
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
        start_time = time.perf_counter()

        for attempt in range(max_retries + 1):
            try:
                attempt_start = time.perf_counter()
                with httpx.Client(timeout=self.timeout) as client:
                    res = client.post(url, headers=headers, json=payload)
                    attempt_latency = time.perf_counter() - attempt_start

                    if res.status_code == 200:
                        total_client_latency = time.perf_counter() - start_time
                        data = res.json()
                        choices = data.get("choices")
                        if not choices or not isinstance(choices, list) or len(choices) == 0:
                            raise RuntimeError("Hugging Face API returned empty choices in completion response.")

                        message = choices[0].get("message", {})
                        content = message.get("content")
                        if not content or not isinstance(content, str) or not content.strip():
                            raise RuntimeError("Hugging Face API returned empty message content in completion response.")

                        record = {
                            "provider": "huggingface",
                            "actual_model_id": active_model,
                            "task": active_task,
                            "request_latency_ms": round(total_client_latency * 1000.0, 2),
                            "request_latency_seconds": round(total_client_latency, 4),
                            "fallback_status": False,
                            "errors": None,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        self.call_history.append(record)
                        return content.strip(), record

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
                        logger.error("Hugging Face model '%s' not found on router (HTTP 404).", active_model)
                        raise RuntimeError(f"Hugging Face model '{active_model}' not found on router (HTTP 404). Verify HF_MODEL.")

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
                last_exc = TimeoutError(f"LLM generation timed out after {self.timeout}s")

            except httpx.RequestError as exc:
                last_exc = exc
                logger.error("Network communication error with Hugging Face: %s", exc.__class__.__name__)
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                last_exc = RuntimeError(f"Failed to communicate with Hugging Face Inference API: {exc}")

            except Exception as exc:
                last_exc = exc
                break

        total_client_latency = time.perf_counter() - start_time
        err_str = str(last_exc) if last_exc else "Hugging Face generation failed after retries."
        record = {
            "provider": "huggingface",
            "actual_model_id": active_model,
            "task": active_task,
            "request_latency_ms": round(total_client_latency * 1000.0, 2),
            "request_latency_seconds": round(total_client_latency, 4),
            "fallback_status": True,
            "errors": err_str,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.call_history.append(record)

        if last_exc:
            raise last_exc
        raise RuntimeError(err_str)

    def generate(self, prompt: str, task: Optional[str] = None) -> str:
        """Convenience method returning response text from generate_with_telemetry."""
        content, _ = self.generate_with_telemetry(prompt, task=task)
        return content
