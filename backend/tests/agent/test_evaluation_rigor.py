"""
Rigorous evaluation meta-tests for Vermithor incident diagnosis engine (Prompt 13).
Validates:
1. Ground-truth leakage absence in scenario files and runtime states
2. Deterministic reproducibility of investigation runs
3. Stability under evidence permutation (order invariance)
4. Deduplication of duplicate telemetry and log events
5. Missing telemetry detection (not conflated with nominal telemetry)
6. Timestamp skew and out-of-window filtering
7. Multiple concurrent root causes handling
8. False temporal correlation rejection
9. Malformed evidence reference handling
10. Excessive causal graph expansion bounding
11. Safe abstention on unsupported hypotheses
"""

from datetime import datetime, timezone, timedelta
import glob
import json
from pathlib import Path
import pytest
import yaml

from backend.app.agent.graph.nodes.correlate_evidence import correlate_evidence_node
from backend.app.agent.graph.nodes.evaluate_hypotheses import evaluate_hypotheses_node
from backend.app.agent.graph.nodes.gather_evidence import gather_evidence_node
from backend.app.agent.graph.nodes.generate_rca import generate_rca_node
from backend.app.agent.graph.nodes.produce_report import produce_report_node
from backend.app.agent.schemas.investigation import InvestigationStatus
from backend.app.rca.analysis.causal_graph import CausalGraphBuilder
from backend.app.rca.analysis.scoring import CandidateScorer
from backend.app.rca.analysis.candidate_generator import CandidateGenerator


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def test_no_ground_truth_leakage_in_held_out_scenarios():
    """Verify that held-out scenario files contain zero evaluation answer keys or labels."""
    scenarios_dir = REPO_ROOT / "evaluation" / "benchmarks" / "held_out_incidents" / "scenarios"
    scenario_files = glob.glob(str(scenarios_dir / "*.yaml"))
    assert len(scenario_files) >= 24, f"Expected at least 24 scenarios, found {len(scenario_files)}"

    forbidden_keys = {
        "ground_truth",
        "expected_root_cause_keywords",
        "injected_cause",
        "abstain_required",
        "repair_appropriate",
        "repair_expected_defect",
        "answer_key",
    }

    for sf in scenario_files:
        with open(sf, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for fk in forbidden_keys:
            assert fk not in data, f"Ground-truth leakage detected in {sf}: key '{fk}' is present"


def test_deterministic_reproducibility():
    """Ensure identical inputs produce identical candidates and scores under deterministic fallback."""
    signals = [
        {
            "signal_id": "sig-db-1",
            "signal_type": "ANOMALY",
            "service": "billing-core",
            "timestamp": "2026-10-20T10:00:00Z",
            "severity": "CRITICAL",
            "message": "Hikari connection pool exhausted",
            "metadata": {"metric_name": "db_pool_utilization_ratio", "value": 1.0},
        },
        {
            "signal_id": "sig-db-2",
            "signal_type": "EVENT",
            "service": "billing-core",
            "timestamp": "2026-10-20T10:01:00Z",
            "severity": "ERROR",
            "message": "ConnectionAcquisitionTimeoutException: pool exhausted",
        },
    ]

    candidates1 = CandidateGenerator.generate_candidates(signals)
    edges1, _ = CausalGraphBuilder.build_graph(signals)
    scorer1 = CandidateScorer()
    scored1 = scorer1.score_candidates(candidates1, signals, edges1)

    candidates2 = CandidateGenerator.generate_candidates(signals)
    edges2, _ = CausalGraphBuilder.build_graph(signals)
    scorer2 = CandidateScorer()
    scored2 = scorer2.score_candidates(candidates2, signals, edges2)

    assert len(scored1) == len(scored2)
    assert scored1[0]["candidate_name"] == scored2[0]["candidate_name"]
    assert scored1[0]["score"] == scored2[0]["score"]
    assert scored1[0]["confidence"] == scored2[0]["confidence"]


def test_order_invariance_ranking():
    """Verify that shuffling the input order of signals does not alter the primary root cause."""
    sig1 = {
        "signal_id": "sig-cpu",
        "signal_type": "ANOMALY",
        "service": "worker-svc",
        "timestamp": "2026-10-20T10:00:00Z",
        "severity": "CRITICAL",
        "message": "CPU throttling at 99%",
        "metadata": {"metric_name": "container_cpu_utilization_ratio", "value": 0.99},
    }
    sig2 = {
        "signal_id": "sig-log",
        "signal_type": "EVENT",
        "service": "worker-svc",
        "timestamp": "2026-10-20T10:02:00Z",
        "severity": "WARN",
        "message": "Thread starvation in worker thread pool",
    }

    # Order A: Anomaly first, then log
    signals_a = [sig1, sig2]
    cands_a = CandidateGenerator.generate_candidates(signals_a)
    edges_a, _ = CausalGraphBuilder.build_graph(signals_a)
    scored_a = CandidateScorer().score_candidates(cands_a, signals_a, edges_a)

    # Order B: Log first, then anomaly
    signals_b = [sig2, sig1]
    cands_b = CandidateGenerator.generate_candidates(signals_b)
    edges_b, _ = CausalGraphBuilder.build_graph(signals_b)
    scored_b = CandidateScorer().score_candidates(cands_b, signals_b, edges_b)

    assert scored_a[0]["candidate_type"] == scored_b[0]["candidate_type"]
    assert scored_a[0]["candidate_name"] == scored_b[0]["candidate_name"]
    assert abs(scored_a[0]["score"] - scored_b[0]["score"]) < 1e-4


def test_duplicate_events_deduplication():
    """Verify duplicate events with identical messages/IDs do not artificially inflate candidate score."""
    sig_single = {
        "signal_id": "sig-1",
        "signal_type": "EVENT",
        "service": "auth-svc",
        "timestamp": "2026-10-20T10:00:00Z",
        "severity": "ERROR",
        "message": "JWTVerificationError: kid not found",
    }

    signals_unique = [sig_single]
    signals_duplicated = [sig_single, sig_single, sig_single]

    cands_u = CandidateGenerator.generate_candidates(signals_unique)
    cands_d = CandidateGenerator.generate_candidates(signals_duplicated)

    assert len(cands_u) == len(cands_d)
    assert cands_u[0]["candidate_name"] == cands_d[0]["candidate_name"]


def test_missing_telemetry_not_treated_as_nominal():
    """Missing metrics with zero telemetry must not score as healthy or produce confident diagnosis."""
    state = {
        "incident_key": "INC-TEST-EMPTY",
        "incident_title": "Empty telemetry incident",
        "target_service": "unknown-service",
        "environment": "production",
        "window_start": "2026-10-20T10:00:00Z",
        "window_end": "2026-10-20T11:00:00Z",
        "collected_evidence": [],
        "rca_candidates": [],
        "primary_root_cause": "Insufficient evidence",
        "primary_confidence": 0.10,
        "is_fallback": True,
    }

    report_output = produce_report_node(state)
    assert report_output["status"] == InvestigationStatus.INSUFFICIENT_EVIDENCE.value
    assert report_output["primary_confidence"] < 0.45


def test_timestamp_skew_and_out_of_window_events():
    """Events occurring hours outside the incident window should not trigger false deployment causality."""
    now = datetime.now(timezone.utc)
    old_deployment = {
        "signal_id": "dep-old",
        "signal_type": "DEPLOYMENT",
        "service": "cart-api",
        "timestamp": (now - timedelta(hours=48)).isoformat(),
        "severity": "INFO",
        "message": "Old deployment 48 hours ago",
        "metadata": {"version": "v1.0.0"},
    }
    recent_anomaly = {
        "signal_id": "sig-recent",
        "signal_type": "ANOMALY",
        "service": "cart-api",
        "timestamp": now.isoformat(),
        "severity": "CRITICAL",
        "message": "High memory consumption",
        "metadata": {"metric_name": "container_memory_working_set_bytes_ratio", "value": 0.98},
    }

    signals = [old_deployment, recent_anomaly]
    cands = CandidateGenerator.generate_candidates(signals)
    edges, _ = CausalGraphBuilder.build_graph(signals)
    scored = CandidateScorer().score_candidates(cands, signals, edges)

    assert scored[0]["candidate_type"] == "RESOURCE"
    assert "memory" in scored[0]["candidate_name"].lower()


def test_multiple_concurrent_root_causes():
    """When two distinct primary candidates are both corroborated by anomalies, both must appear in Top-3."""
    sig_db = {
        "signal_id": "sig-db",
        "signal_type": "ANOMALY",
        "service": "api-service",
        "timestamp": "2026-10-20T10:00:00Z",
        "severity": "CRITICAL",
        "message": "Database pool saturation",
        "metadata": {"metric_name": "db_connection_pool_utilization_ratio", "value": 1.0},
    }
    sig_cache = {
        "signal_id": "sig-cache",
        "signal_type": "ANOMALY",
        "service": "api-service",
        "timestamp": "2026-10-20T10:01:00Z",
        "severity": "CRITICAL",
        "message": "Redis eviction storm",
        "metadata": {"metric_name": "redis_evicted_keys_rate_per_sec", "value": 5000.0},
    }

    signals = [sig_db, sig_cache]
    cands = CandidateGenerator.generate_candidates(signals)
    edges, _ = CausalGraphBuilder.build_graph(signals)
    scored = CandidateScorer().score_candidates(cands, signals, edges)

    assert len(scored) >= 2
    cand_names = [c["candidate_name"].lower() for c in scored[:3]]
    assert any("database" in n for n in cand_names)
    assert any("redis" in n for n in cand_names)


def test_false_temporal_correlation_rejected():
    """A deployment that occurs AFTER the failure started cannot be diagnosed as the cause."""
    now = datetime.now(timezone.utc)
    early_failure = {
        "signal_id": "sig-fail",
        "signal_type": "ANOMALY",
        "service": "checkout-svc",
        "timestamp": (now - timedelta(minutes=15)).isoformat(),
        "severity": "CRITICAL",
        "message": "HTTP 500 spike",
        "metadata": {"metric_name": "http_5xx_error_rate_ratio", "value": 0.50},
    }
    later_deployment = {
        "signal_id": "dep-later",
        "signal_type": "DEPLOYMENT",
        "service": "checkout-svc",
        "timestamp": (now - timedelta(minutes=5)).isoformat(),
        "severity": "INFO",
        "message": "Deployment initiated to try to hotfix the issue",
        "metadata": {"version": "v2.0.1"},
    }

    signals = [early_failure, later_deployment]
    cands = CandidateGenerator.generate_candidates(signals)
    edges, _ = CausalGraphBuilder.build_graph(signals)
    scored = CandidateScorer().score_candidates(cands, signals, edges)

    assert scored[0]["candidate_type"] != "DEPLOYMENT"


def test_malformed_evidence_references():
    """Signals with missing metadata, empty strings, or non-numeric values must not raise uncaught exceptions."""
    malformed_signals = [
        {"signal_id": "mal-1", "signal_type": "EVENT", "service": "unknown", "timestamp": "2026-10-20T10:00:00Z", "severity": "INFO", "message": ""},
        {"signal_id": "", "message": None, "metadata": {}, "timestamp": "2026-10-20T10:01:00Z", "service": "unknown"},
        {"metadata": {"metric_name": "unknown_metric", "value": "not-a-number"}, "timestamp": "2026-10-20T10:02:00Z", "service": "unknown"},
    ]

    cands = CandidateGenerator.generate_candidates(malformed_signals)
    edges, _ = CausalGraphBuilder.build_graph(malformed_signals)
    scored = CandidateScorer().score_candidates(cands, malformed_signals, edges)

    assert len(scored) >= 1
    assert scored[0]["candidate_type"] == "UNKNOWN"


def test_causal_graph_bounding():
    """Graph construction with 100 signals must strictly cap node inputs to prevent quadratic edge explosion."""
    signals = []
    base_ts = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    for i in range(100):
        signals.append({
            "signal_id": f"sig-stress-{i:03d}",
            "signal_type": "ANOMALY" if i % 10 == 0 else "EVENT",
            "service": f"service-{i % 5}",
            "timestamp": (base_ts + timedelta(seconds=i)).isoformat(),
            "severity": "CRITICAL" if i % 10 == 0 else "INFO",
            "message": f"Stress test telemetry signal {i}",
            "metadata": {"metric_name": "container_cpu_utilization_ratio", "value": 0.88 if i % 10 == 0 else 0.20},
        })

    edges, chain = CausalGraphBuilder.build_graph(signals)
    # Bounded to MAX_SIGNALS_TO_GRAPH (50)
    assert len(chain) <= 50
    assert len(edges) <= 100


def test_abstention_on_unsupported_hypothesis():
    """When observed signals have sub-threshold values and no confirmed errors, agent must abstain."""
    signals = [
        {
            "signal_id": "sig-nom-1",
            "signal_type": "EVENT",
            "service": "gateway-api",
            "timestamp": "2026-10-20T10:00:00Z",
            "severity": "INFO",
            "message": "Routine health ping completed in 12ms",
        },
        {
            "signal_id": "sig-nom-2",
            "signal_type": "EVENT",
            "service": "gateway-api",
            "timestamp": "2026-10-20T10:01:00Z",
            "severity": "WARN",
            "message": "Minor connection jitter: retry succeeded",
            "metadata": {"metric_name": "http_5xx_error_rate_ratio", "value": 0.001},
        },
    ]

    cands = CandidateGenerator.generate_candidates(signals)
    edges, _ = CausalGraphBuilder.build_graph(signals)
    scored = CandidateScorer().score_candidates(cands, signals, edges)

    assert len(scored) == 1
    assert scored[0]["candidate_type"] == "UNKNOWN"
    assert scored[0]["score"] <= 0.35
