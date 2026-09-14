import os
os.environ["SERVICE_UNDER_TEST"] = "summary"

import json
import pytest
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory


class FakeLLMProvider(LLMProvider):
    """Fake LLM provider for testing."""

    DEFAULT_RESPONSE = json.dumps({
        "title": "Incident Summary",
        "executive_summary": "PostgreSQL connection pool exhaustion caused service disruption in booking-api.",
        "what_happened": "At 12:00 UTC, booking-api experienced high connection count leading to exhaustion.",
        "probable_root_cause": "PostgreSQL Connection Pool Exhaustion caused by connection leak under load.",
        "impact": {
            "services": ["booking-api"],
            "severity": "CRITICAL",
            "description": "API requests failed with 500 errors",
        },
        "timeline": [
            {"timestamp": "2026-08-29T12:00:00Z", "event": "Connection pool saturated", "source": "LOG"}
        ],
        "evidence": [
            {
                "claim": "Connection pool saturated",
                "source_type": "LOG",
                "source_id": "evt-db-01",
                "support": "Connection pool exhausted",
            },
            {
                "claim": "RCA Root Cause",
                "source_type": "RCA",
                "source_id": "RCA-000001",
                "support": "PostgreSQL Connection Pool Exhaustion",
            },
            {
                "claim": "Generic evidence",
                "source_type": "LOG",
                "source_id": "evt-01",
                "support": "Error in logs",
            },
        ],
        "remediation": [
            {"action": "Increase connection pool size", "priority": "HIGH", "reason": "Prevent exhaustion"}
        ],
        "confidence": 0.89,
        "limitations": [],
        "status": "completed",
    })

    def __init__(self, response_text: str = None, exception_to_raise: Exception = None):
        self.response_text = response_text or self.DEFAULT_RESPONSE
        self.exception_to_raise = exception_to_raise
        self.last_prompt = ""

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.exception_to_raise:
            raise self.exception_to_raise
        return self.response_text

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "fake_llm"

    def get_model_name(self) -> str:
        return "fake_model"


@pytest.fixture(name="fake_llm", autouse=True)
def fake_llm_fixture():
    fake = FakeLLMProvider()
    ProviderFactory.set_provider(fake)
    yield fake
    ProviderFactory.set_provider(None)
