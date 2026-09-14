import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pytest
from sqlalchemy.orm import Session

from backend.app.common.database import SessionLocal, get_db
from backend.app.retrieval.clients.incident_client import IncidentServiceClient
from backend.app.retrieval.repositories.runbook_repository import RunbookRepository
from backend.app.retrieval.retrieval.context_assembler import ContextAssembler
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.prompts.incident_summary import IncidentSummaryPromptBuilder
from backend.app.summary.schemas.summaries import (
    EvidenceItemSchema,
    ImpactSchema,
    IncidentSummaryGeneratedSchema,
    IncidentSummaryResponse,
    RemediationItemSchema,
    TimelineItemSchema,
)
from backend.app.summary.services.evidence_validator import EvidenceValidator
from backend.app.summary.services.summary_service import IncidentSummaryService


class MockStaticLLMProvider(LLMProvider):
    """Mock provider returning deterministic JSON output for unit tests."""

    def __init__(self, response_json: Dict[str, Any]):
        self.response_json = response_json

    def get_provider_name(self) -> str:
        return "mock_static"

    def get_model_name(self) -> str:
        return "mock-v1"

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str) -> str:
        return json.dumps(self.response_json)


class FailingLLMProvider(LLMProvider):
    """Mock provider simulating network or model timeout."""

    def get_provider_name(self) -> str:
        return "failing_mock"

    def get_model_name(self) -> str:
        return "mock-fail"

    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str) -> str:
        raise TimeoutError("Ollama connection timed out after 30.0s")


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_canonical_runbook_retrieval(db_session: Session):
    """Verify search across canonical runbooks (Database, Redis, Memory, Deployment, CPU)."""
    # 1. Search Database Runbook
    db_results = RunbookRepository.search_runbooks(
        db=db_session,
        query="database connection pool exhausted timeout",
        top_k=2,
    )
    assert len(db_results) >= 1
    top_db = db_results[0]
    assert "Database Connection Pool" in top_db.title
    assert top_db.source_type == SourceType.RUNBOOK
    assert top_db.similarity_score >= 0.70

    # 2. Search Redis Runbook
    redis_results = RunbookRepository.search_runbooks(
        db=db_session,
        query="redis cluster cache node connection refused",
        top_k=2,
    )
    assert len(redis_results) >= 1
    assert "Redis Cache" in redis_results[0].title

    # 3. Search Deployment Runbook
    dep_results = RunbookRepository.search_runbooks(
        db=db_session,
        query="breaking software release rollback feature flag",
        top_k=2,
    )
    assert len(dep_results) >= 1
    assert "Deployment Rollback" in dep_results[0].title


def test_prioritized_bounded_context_assembly():
    """Verify context assembler enforces source priority (RCA > LOG > INCIDENT > RUNBOOK) and max length."""
    assembler = ContextAssembler()

    items = [
        RetrievalResultItem(
            source_type=SourceType.DEPLOYMENT,
            source_id="dep-1",
            title="Deployment Event",
            content="Deployed v2.4.0 on booking-api",
            final_score=0.70,
            citation="[DEPLOYMENT:dep-1]",
        ),
        RetrievalResultItem(
            source_type=SourceType.RUNBOOK,
            source_id="RB-000001",
            title="Database Runbook",
            content="Scale connection pool and terminate idle queries",
            final_score=0.80,
            citation="[RUNBOOK:RB-000001]",
        ),
        RetrievalResultItem(
            source_type=SourceType.RCA,
            source_id="RCA-001",
            title="Root Cause Analysis",
            content="Primary Root Cause: Database pool saturation on postgres",
            final_score=0.99,
            citation="[RCA:RCA-001]",
        ),
        RetrievalResultItem(
            source_type=SourceType.LOG,
            source_id="sig-log-1",
            title="Postgres Log",
            content="Connection to database timed out after 30000ms",
            final_score=0.90,
            citation="[LOG:sig-log-1]",
        ),
    ]

    included, context_text, is_truncated = assembler.assemble(items, max_results=4, max_chars=4000)

    assert len(included) == 4
    # Highest priority is RCA
    assert included[0].source_type == SourceType.RCA
    # Second priority is LOG
    assert included[1].source_type == SourceType.LOG
    # Third is RUNBOOK
    assert included[2].source_type == SourceType.RUNBOOK
    # Lowest is DEPLOYMENT
    assert included[3].source_type == SourceType.DEPLOYMENT
    assert "[RCA:RCA-001]" in context_text


def test_structured_output_schema_and_properties():
    """Verify Pydantic schema validation and property getters for frontend consumption."""
    raw_summary = {
        "id": uuid.uuid4(),
        "summary_key": "SUM-000099",
        "incident_key": "INC-000099",
        "status": "COMPLETED",
        "summary_version": "1.0.0",
        "model_provider": "ollama",
        "model_name": "qwen2.5-coder:7b",
        "executive_summary": "Database pool exhaustion caused checkout latency.",
        "what_happened": "High traffic saturated the database connection pool.",
        "probable_root_cause": "Database connection saturation on postgres",
        "impact": {
            "services": ["booking-api", "postgres"],
            "severity": "CRITICAL",
            "description": "Checkout service degraded",
        },
        "timeline": [
            {
                "timestamp": "2026-08-29T14:00:00Z",
                "event": "Latency spike started",
                "source": "[METRIC:sig-1]",
            }
        ],
        "evidence": [
            {
                "evidence_id": "E1",
                "claim": "Database connections reached 100% capacity",
                "source_type": "METRIC",
                "source_id": "sig-db-pool",
                "support": "db_active_connections reached 100",
            }
        ],
        "remediation": [
            {
                "action": "Scale max pool size from 100 to 150",
                "priority": "HIGH",
                "reason": "Permits higher connection concurrency under peak load",
            }
        ],
        "confidence": 0.92,
        "limitations": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    resp = IncidentSummaryResponse(**raw_summary)

    # Validate properties
    assert resp.incident_id == "INC-000099"
    assert resp.summary == "Database pool exhaustion caused checkout latency."
    assert resp.root_cause == "Database connection saturation on postgres"
    assert resp.severity == "CRITICAL"
    assert resp.affected_services == ["booking-api", "postgres"]
    assert len(resp.recommended_actions) == 1
    assert resp.recommended_actions[0].action == "Scale max pool size from 100 to 150"
    assert resp.confidence == 0.92


def test_evidence_validation_rejects_hallucinated_root_cause():
    """Verify evidence validator overrides hallucinated root cause when RCA is UNKNOWN."""
    rca = {
        "analysis_key": "RCA-UNKNOWN-001",
        "primary_root_cause": "UNKNOWN",
        "primary_confidence": 0.15,
        "candidates": [],
    }

    probable_cause = "BGP routing anomaly caused network blackout"
    aligned_cause, warning = EvidenceValidator.validate_root_cause(probable_cause, rca)

    assert "Insufficient evidence" in aligned_cause
    assert warning is not None
    assert "overriding hallucinated cause" in warning


def test_evidence_validation_filters_unobserved_services():
    """Verify evidence validator filters out hallucinated services not present in incident/RCA."""
    incident = {"incident_key": "INC-01", "service": "booking-api"}
    rca = {
        "candidates": [
            {"service": "postgres", "affected_services": ["booking-api", "postgres"]}
        ]
    }

    candidate_services = ["booking-api", "postgres", "crypto-mining-daemon", "unrelated-auth-api"]
    valid_svcs, warnings = EvidenceValidator.validate_affected_services(
        candidate_services,
        incident,
        rca,
    )

    assert "booking-api" in valid_svcs
    assert "postgres" in valid_svcs
    assert "crypto-mining-daemon" not in valid_svcs
    assert "unrelated-auth-api" not in valid_svcs
    assert len(warnings) == 2


def test_evidence_validation_auto_assigns_evidence_ids_and_filters_unverified():
    """Verify evidence validator filters out fabricated source IDs and assigns E1, E2..."""
    valid_ids = {"sig-db-1", "sig-db-2", "rca-001"}

    evidence_items = [
        EvidenceItemSchema(
            claim="Database latency spike occurred at 14:00",
            source_type="ANOMALY",
            source_id="sig-db-1",
        ),
        EvidenceItemSchema(
            claim="Cosmic ray flipped bit on CPU",
            source_type="LOG",
            source_id="fake-source-9999",
        ),
    ]

    filtered, warnings = EvidenceValidator.validate_and_filter_evidence(evidence_items, valid_ids)

    assert len(filtered) == 1
    assert filtered[0].source_id == "sig-db-1"
    assert filtered[0].evidence_id == "E1"
    assert len(warnings) == 1
    assert "fake-source-9999" in warnings[0]


def test_deterministic_fallback_on_llm_failure(db_session: Session):
    """Verify service returns a structured fallback when LLM fails without crashing."""
    class DummyIncidentClient:
        def get_incident(self, key):
            return {
                "incident_key": key,
                "title": "PostgreSQL Latency Outage",
                "service": "booking-api",
                "environment": "production",
                "severity": "CRITICAL",
                "started_at": "2026-08-29T14:00:00Z",
            }

    class DummyRCAClient:
        def get_rca_reports(self, top_k=1):
            return [
                {
                    "analysis_key": "RCA-009",
                    "primary_root_cause": "Database connection saturation on postgres",
                    "primary_confidence": 0.88,
                    "candidates": [
                        {
                            "candidate_name": "Database connection saturation on postgres",
                            "score": 0.88,
                            "service": "postgres",
                            "affected_services": ["booking-api", "postgres"],
                        }
                    ],
                }
            ]

    class DummyRetrievalClient:
        def get_rag_context(self, incident_key, top_k=10):
            return {
                "context_text": "Runbook RB-000001: Scale connection pool.",
                "context": [{"source_id": "RB-000001", "source_type": "RUNBOOK"}],
            }

    service = IncidentSummaryService(
        incident_client=DummyIncidentClient(),
        rca_client=DummyRCAClient(),
        retrieval_client=DummyRetrievalClient(),
        llm_provider=FailingLLMProvider(),
    )

    resp = service.generate_summary_for_incident(
        db=db_session,
        incident_key=f"INC-TEST-{uuid.uuid4().hex[:6]}",
        regenerate=True,
        allow_fallback=True,
    )

    assert resp.status.value == "COMPLETED"
    assert resp.is_fallback is True
    assert resp.model_provider == "fallback"
    assert "Database connection saturation on postgres" in resp.probable_root_cause
    assert resp.confidence == 0.88
    assert len(resp.recommended_actions) >= 1
    assert "connection pool" in resp.recommended_actions[0].action.lower()


def test_end_to_end_grounded_summary_generation(db_session: Session):
    """Verify complete summary synthesis with grounded Mock LLM provider."""
    mock_llm_payload = {
        "executive_summary": "PostgreSQL connection pool exhaustion on postgres caused checkout failures in booking-api.",
        "what_happened": "At 14:00 UTC, active connections saturated the maximum pool limit of 100.",
        "probable_root_cause": "Database connection saturation on postgres",
        "impact": {
            "services": ["booking-api", "postgres"],
            "severity": "CRITICAL",
            "description": "Booking checkout service was degraded with HTTP 500 errors",
        },
        "timeline": [
            {
                "timestamp": "2026-08-29T14:00:00Z",
                "event": "Database connection pool saturated at 100%",
                "source": "[METRIC:sig-db-pool]",
            }
        ],
        "evidence": [
            {
                "evidence_id": "E1",
                "claim": "Database active connections reached pool limit of 100",
                "source_type": "ANOMALY",
                "source_id": "sig-db-pool",
                "support": "Metric db_active_connections reached 100.0",
            }
        ],
        "remediation": [
            {
                "action": "Scale PostgreSQL max_connections and application pool size",
                "priority": "HIGH",
                "reason": "Prevents client connection wait timeouts during high load",
            }
        ],
        "confidence": 0.90,
        "limitations": [],
        "similar_incidents": [],
    }

    class DummyIncidentClient:
        def get_incident(self, key):
            return {
                "incident_key": key,
                "title": "Postgres Pool Exhaustion",
                "service": "booking-api",
                "environment": "production",
                "severity": "CRITICAL",
                "started_at": "2026-08-29T14:00:00Z",
            }

    class DummyRCAClient:
        def get_rca_reports(self, top_k=1):
            return [
                {
                    "analysis_key": "RCA-001",
                    "primary_root_cause": "Database connection saturation on postgres",
                    "primary_confidence": 0.94,
                    "candidates": [
                        {
                            "candidate_name": "Database connection saturation on postgres",
                            "score": 0.94,
                            "service": "postgres",
                            "associated_signal_ids": ["sig-db-pool"],
                            "affected_services": ["booking-api", "postgres"],
                        }
                    ],
                }
            ]

    class DummyRetrievalClient:
        def get_rag_context(self, incident_key, top_k=10):
            return {
                "context_text": "Runbook RB-000001: Database Connection Pool Exhaustion.",
                "context": [
                    {
                        "source_id": "sig-db-pool",
                        "source_type": "ANOMALY",
                        "title": "DB Active Connections",
                        "similarity_score": 0.92,
                        "final_score": 0.90,
                    }
                ],
            }

    service = IncidentSummaryService(
        incident_client=DummyIncidentClient(),
        rca_client=DummyRCAClient(),
        retrieval_client=DummyRetrievalClient(),
        llm_provider=MockStaticLLMProvider(mock_llm_payload),
    )

    inc_key = f"INC-SYNTH-{uuid.uuid4().hex[:6]}"
    resp = service.generate_summary_for_incident(
        db=db_session,
        incident_key=inc_key,
        regenerate=True,
    )

    assert resp.status.value == "COMPLETED"
    assert resp.is_fallback is False
    assert resp.confidence == 0.94  # Strict RCA confidence inheritance
    assert resp.root_cause == "Database connection saturation on postgres"
    assert "booking-api" in resp.affected_services
    assert "postgres" in resp.affected_services
    assert len(resp.evidence) == 1
    assert resp.evidence[0].evidence_id == "E1"
    assert resp.evidence[0].source_id == "sig-db-pool"
    assert resp.debug_rag_info is not None
    assert resp.debug_rag_info["total_retrieved"] == 1
