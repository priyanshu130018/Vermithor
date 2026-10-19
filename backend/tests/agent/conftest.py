from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pytest
from sqlalchemy.orm import Session

from backend.app.incidents.db.models import Incident
from backend.app.incidents.schemas.incident import IncidentCreate, IncidentSeverity, IncidentStatus
from backend.app.incidents.services.incident_service import IncidentService
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService
from backend.app.summary.llm.base import LLMProvider


class FakeTelemetryEvidenceService(TelemetryEvidenceService):
    """Mock telemetry service returning deterministic Prometheus & Jaeger data without network calls."""

    def __init__(self, service_available: bool = True):
        self.service_available = service_available

    def get_telemetry_snapshot(self, service: str, lookback_minutes: int = 15) -> Dict[str, Any]:
        if not self.service_available:
            raise ConnectionError(f"Prometheus and Jaeger services unreachable for {service}")

        now = datetime.now(timezone.utc)
        return {
            "service": service,
            "lookback_minutes": lookback_minutes,
            "collected_at": now.isoformat(),
            "sources": {
                "prometheus": {
                    "base_url": "http://mock-prometheus:9090",
                    "metrics": {
                        "db_connection_pool_utilization_ratio": {"value": 1.0, "query": "db_pool_util"},
                        "api_request_latency_ms": {"value": 4800.0, "query": "latency"},
                        "http_5xx_error_rate_ratio": {"value": 0.28, "query": "5xx_rate"},
                    },
                },
                "jaeger": {
                    "base_url": "http://mock-jaeger:16686",
                    "total_traces": 1,
                    "summaries": [
                        {
                            "trace_id": "9bf92f3577b34da6a3ce929d0e0e1042",
                            "root_service": service,
                            "root_operation": "POST /api/v1/payments/charge",
                            "start_time": now.isoformat(),
                            "duration_ms": 4800.0,
                            "span_count": 12,
                            "services_involved": [service, "postgres"],
                            "has_error": True,
                            "error_spans": [{"span_id": "sp-101", "error_message": "ConnectionAcquisitionTimeoutException"}],
                            "bottleneck_spans": [{"span_id": "sp-101", "duration_ms": 4800.0}],
                        }
                    ],
                },
            },
        }


class FakeValidLLM(LLMProvider):
    """Mock LLM returning valid structured evaluation JSON matching Vermithor schema."""

    def __init__(self, provider_name: str = "mock_llm", model_name: str = "mock-model"):
        self.provider = provider_name
        self.model = model_name

    def generate(self, prompt: str) -> str:
        return """{
  "observed_facts": [
    "[EV-PROM-1] Database connection pool utilization reached 1.0 (100% capacity)",
    "[EV-PROM-2] API request latency spiked to 4800.0ms",
    "[EV-PROM-3] HTTP 5xx error rate reached 0.28 (28%)",
    "[EV-TRACE-1] Jaeger trace 9bf92f3577b34da6 captured ConnectionAcquisitionTimeoutException"
  ],
  "inferred_relationships": [
    "Deployment v2.8.4 preceded database connection acquisition timeouts",
    "HikariCP pool saturation on payment-api caused upstream latency cascade"
  ],
  "confirmed_findings": [
    "Database connection pool exhaustion on payment-api is confirmed as the primary operational failure"
  ],
  "hypotheses_evaluated": [
    {{
      "hypothesis": "Database connection pool exhaustion on payment-api",
      "candidate_type": "DATABASE",
      "original_score": 0.94,
      "calibrated_status": "CONFIRMED",
      "supporting_evidence_ids": ["EV-PROM-1", "EV-TRACE-1"],
      "contradicting_evidence_ids": [],
      "reasoning": "Direct evidence of 100% pool utilization and ConnectionAcquisitionTimeoutException error spans"
    }},
    {{
      "hypothesis": "Recent deployment on payment-api",
      "candidate_type": "DEPLOYMENT",
      "original_score": 0.75,
      "calibrated_status": "PLAUSIBLE",
      "supporting_evidence_ids": ["EV-EVT-1"],
      "contradicting_evidence_ids": [],
      "reasoning": "Deployment v2.8.4 introduced persistent connection configuration immediately preceding the saturation"
    }}
  ],
  "alternative_explanations": [
    "Downstream network partition between payment-api and postgres (unlikely due to fast TCP connection rejections)"
  ],
  "missing_evidence": [
    "PostgreSQL pg_stat_activity connection list at exact incident onset"
  ],
  "contradictory_evidence": [],
  "uncertainty_assessment": "Low uncertainty: Telemetry definitively isolates connection pool exhaustion as root cause",
  "recommended_diagnostic_steps": [
    {{
      "action": "Inspect pg_stat_activity to identify leaking connection holding queries",
      "target_service": "postgres",
      "rationale": "Verify whether connection leaks or unindexed slow queries hold pool slots",
      "priority": "HIGH",
      "requires_human_approval": true
    }},
    {{
      "action": "Verify HikariCP connection pool timeout configuration on payment-api",
      "target_service": "payment-api",
      "rationale": "Assess if pool size should be scaled from 100 to 150",
      "priority": "HIGH",
      "requires_human_approval": true
    }}
  ]
}"""

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return self.provider

    def get_model_name(self) -> str:
        return self.model


class FakeFailingLLM(LLMProvider):
    """Mock LLM simulating timeout or network error."""

    def generate(self, prompt: str) -> str:
        raise TimeoutError("Inference API request timed out after 30.0s")

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "failing_llm"

    def get_model_name(self) -> str:
        return "failing_model"


class FakeMalformedLLM(LLMProvider):
    """Mock LLM returning invalid JSON non-compliant with schema."""

    def generate(self, prompt: str) -> str:
        return "I think the server crashed because of high load. No JSON here!"

    def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "malformed_llm"

    def get_model_name(self) -> str:
        return "malformed_model"


@pytest.fixture
def mock_telemetry_service():
    return FakeTelemetryEvidenceService(service_available=True)


@pytest.fixture
def mock_unavailable_telemetry_service():
    return FakeTelemetryEvidenceService(service_available=False)


@pytest.fixture
def mock_valid_llm():
    return FakeValidLLM()


@pytest.fixture
def mock_failing_llm():
    return FakeFailingLLM()


@pytest.fixture
def mock_malformed_llm():
    return FakeMalformedLLM()


@pytest.fixture
def test_payment_incident(db_session: Session) -> Incident:
    """Creates synthetic INC-2026-1042 incident record in test database session."""
    now = datetime.now(timezone.utc)
    inc_in = IncidentCreate(
        incident_key="INC-2026-1042",
        title="Payment API Database Connection Pool Exhaustion & Latency Spike",
        description="Database connection pool utilization reached 100% on payment-api.",
        severity=IncidentSeverity.SEV1,
        environment="production",
        started_at=now,
        confidence=0.94,
    )
    return IncidentService.create_incident(db_session, inc_in)
