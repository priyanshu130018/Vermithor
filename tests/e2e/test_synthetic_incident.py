import os
import sys
import uuid
import datetime
import pytest

# Add tool directory to sys.path
tool_dir = os.path.abspath("scripts/demo/synthetic-incidents")
if tool_dir not in sys.path:
    sys.path.insert(0, tool_dir)

from generator import load_scenario, build_telemetry_batch
from client import VermithorClient

from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.scoring import CandidateScorer
from backend.app.correlation.scoring.scorer import CorrelationScorer
from backend.app.correlation.schemas.correlation import SignalInput
from backend.app.log_intelligence.parsing.classifier import LogClassifier
from backend.app.log_intelligence.parsing.normalizer import LogNormalizer
from backend.app.retrieval.retrieval.context_assembler import ContextAssembler
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType
from backend.app.summary.prompts.incident_summary import IncidentSummaryPromptBuilder


def test_synthetic_scenario_end_to_end():
    """Validates the full 8-stage incident pipeline for database connection saturation."""
    scenario_id = f"test-e2e-{uuid.uuid4().hex[:8]}"
    scenario = load_scenario("database_connection_saturation")
    base_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=180)

    batch = build_telemetry_batch(scenario, scenario_id, base_time)

    # 1. Ingestion Phase Verification
    assert len(batch["events"]) > 0
    assert len(batch["observations"]) > 0
    assert len(batch["logs"]) > 0

    # 2. RCA Semantic Evaluation
    signals = [
        {
            "signal_id": "sig-1",
            "signal_type": "ANOMALY",
            "service": "postgres",
            "environment": "production",
            "timestamp": (base_time + datetime.timedelta(seconds=10)).isoformat(),
            "severity": "CRITICAL",
            "source_reference": "obs-1",
            "metadata": {"metric_name": "db_connections_active", "value": 98.0},
        },
        {
            "signal_id": "sig-2",
            "signal_type": "LOG",
            "service": "booking-api",
            "environment": "production",
            "timestamp": (base_time + datetime.timedelta(seconds=45)).isoformat(),
            "severity": "ERROR",
            "source_reference": "log-1",
            "metadata": {"message": "FATAL: remaining connection slots are reserved"},
        },
        {
            "signal_id": "sig-3",
            "signal_type": "LOG",
            "service": "frontend",
            "environment": "production",
            "timestamp": (base_time + datetime.timedelta(seconds=90)).isoformat(),
            "severity": "ERROR",
            "source_reference": "log-2",
            "metadata": {"message": "HTTP 500 internal server error on checkout"},
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    assert len(candidates) >= 1
    root_candidate = next((c for c in candidates if "postgres" in c["candidate_name"].lower() or "connection" in c["candidate_name"].lower()), None)
    assert root_candidate is not None, "PostgreSQL connection exhaustion candidate was not identified"

    scorer = CandidateScorer()
    scored = scorer.score_candidates(
        candidates=candidates,
        signals=signals,
        edges=[],
    )
    assert len(scored) > 0
    top_cause = scored[0]
    assert "postgres" in top_cause["candidate_name"].lower() or "connection" in top_cause["candidate_name"].lower()
    assert top_cause["score"] > 0.40

    # 3. Correlation Scoring Verification
    sig1 = SignalInput(
        signal_id="sig-1",
        signal_type="ANOMALY",
        service="postgres",
        environment="production",
        timestamp=base_time,
        severity="CRITICAL",
    )
    sig2 = SignalInput(
        signal_id="sig-2",
        signal_type="EVENT",
        service="booking-api",
        environment="production",
        timestamp=base_time + datetime.timedelta(seconds=30),
        severity="ERROR",
    )
    corr_scorer = CorrelationScorer()
    score, reasons = corr_scorer.score_pair(sig1, sig2)
    assert score >= 0.30
    assert len(reasons) > 0


def test_log_intelligence_vector_retrieval():
    """Verify semantic vector search correctly classifies and normalizes database timeout log templates."""
    msg = "2026-08-29 12:00:00 [ERROR] Connection to database host 10.0.1.5:5432 timed out after 30000ms"
    category = LogClassifier.classify(msg)
    assert category.value in ["DATABASE", "APPLICATION_ERROR"]

    norm_res = LogNormalizer.normalize_log(msg)
    assert "<IP>" in norm_res or "10.0.1.5" not in norm_res
    assert "<NUM>" in norm_res or "30000" not in norm_res


def test_rag_runbook_and_history_assembly():
    """Verify RAG context assembler correctly formats runbook and historical evidence."""
    items = [
        RetrievalResultItem(
            source_type=SourceType.RUNBOOK,
            source_id="rb-db-conn",
            title="Database Connection Exhaustion Runbook",
            content="Check pg_stat_activity, kill idle in transaction connections, increase max_connections.",
            service="postgres",
            environment="production",
            similarity_score=0.95,
            citation="[RUNBOOK:rb-db-conn]",
            metadata={"priority": "P1"},
        ),
        RetrievalResultItem(
            source_type=SourceType.INCIDENT,
            source_id="INC-2026-0012",
            title="Prior DB Connection Saturation",
            content="Resolved by pool restart and clearing blocked locks in transaction pool.",
            service="postgres",
            environment="production",
            similarity_score=0.88,
            citation="[INCIDENT:INC-2026-0012]",
            metadata={"severity": "SEV1"},
        ),
    ]

    assembler = ContextAssembler()
    included, context_text, is_truncated = assembler.assemble(
        items=items,
        max_results=5,
        max_chars=4000,
    )

    assert len(included) == 2
    assert "[RUNBOOK:rb-db-conn]" in context_text
    assert "[INCIDENT:INC-2026-0012]" in context_text
    assert "pg_stat_activity" in context_text


def test_summary_prompt_and_structure_validation():
    """Verify summary prompt builder packages the full evidence chain."""
    incident = {
        "incident_key": "INC-TEST-001",
        "title": "Database Connection Pool Saturation",
        "description": "Critical pool exhaustion across booking-api and checkout.",
        "severity": "SEV1",
        "environment": "production",
        "started_at": "2026-08-29T12:00:00Z",
    }
    rca_analysis = {
        "analysis_key": "RCA-0001",
        "primary_root_cause": "PostgreSQL Connection Pool Exhaustion",
        "primary_confidence": 0.94,
        "causal_chain": ["postgres: db connection spike", "booking-api: timeout", "frontend: 500 error"],
    }
    rag_context = {
        "context_text": "### [RUNBOOK:rb-db-conn] Kill idle transactions.\n### [INCIDENT:INC-2026-0012] Restart pooler.",
        "context": [{"source_id": "rb-db-conn"}, {"source_id": "INC-2026-0012"}],
    }

    prompt = IncidentSummaryPromptBuilder.build_prompt(
        incident=incident,
        rca=rca_analysis,
        rag_context=rag_context,
    )

    assert "INC-TEST-001" in prompt
    assert "PostgreSQL Connection Pool Exhaustion" in prompt
    assert "[RUNBOOK:rb-db-conn]" in prompt
    assert "JSON" in prompt
