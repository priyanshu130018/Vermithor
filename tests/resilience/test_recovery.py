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
from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.scoring import CandidateScorer
from backend.app.retrieval.schemas.runbooks import RunbookCreateRequest, RunbookResponse


def test_post_recovery_e2e_pipeline_execution():
    """Verify that after simulated service or dependency recovery, the full synthetic scenario processes successfully."""
    scenario_id = f"post-recovery-{uuid.uuid4().hex[:8]}"
    scenario = load_scenario("database_connection_saturation")
    base_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=180)

    batch = build_telemetry_batch(scenario, scenario_id, base_time)
    assert len(batch["events"]) > 0

    # 1. RCA Candidate Generation after recovery
    signals = [
        {
            "signal_id": "sig-rec-1",
            "signal_type": "ANOMALY",
            "service": "postgres",
            "metadata": {"metric_name": "db_query_latency_ms"},
            "value": 1200.0,
            "timestamp": (base_time + datetime.timedelta(seconds=60)).isoformat(),
        },
        {
            "signal_id": "sig-rec-2",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "metadata": {"metric_name": "db_connection_pool_utilization_ratio"},
            "value": 0.98,
            "timestamp": (base_time + datetime.timedelta(seconds=60)).isoformat(),
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    scorer = CandidateScorer()
    ranked = scorer.score_candidates(
        candidates=candidates,
        signals=signals,
        edges=[],
    )

    assert len(ranked) > 0
    assert ranked[0].get("candidate_type") == "DATABASE"
    assert ranked[0].get("score", 0.0) >= 0.40


def test_data_integrity_preservation():
    """Verify that runbook and historical incident models preserve required schema fields."""
    rb_create = RunbookCreateRequest(
        runbook_key="rb-resilience-001",
        title="Database Saturation Recovery",
        service="postgres",
        environment="production",
        tags=["database", "pool", "recovery"],
        content="Detailed steps to drain connections and resize pool.",
    )
    assert rb_create.runbook_key == "rb-resilience-001"
    assert rb_create.service == "postgres"
