from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import pytest

from backend.app.rca.analysis.analyzer import RCAAnalyzer
from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.scoring import CandidateScorer
from backend.app.rca.evidence.deployment_evaluator import DeploymentEvidenceEvaluator
from backend.app.rca.evidence.topology_evaluator import TopologyEvidenceEvaluator
from backend.app.rca.evidence.trace_extractor import TraceEvidenceExtractor
from backend.app.topology.service_graph import ServiceTopologyGraph, get_service_topology_graph


@pytest.fixture
def base_time():
    return datetime(2026, 8, 29, 14, 0, 0, tzinfo=timezone.utc)


def test_trace_evidence_extraction(base_time):
    """Verify trace evidence extraction identifies latency bottlenecks, failed spans, and DB queries."""
    signals = [
        {
            "signal_id": "sig-api-err-1",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=20),
            "severity": "CRITICAL",
            "message": "HTTP 500 internal server error during checkout",
            "metadata": {
                "trace_id": "trace-checkout-991",
                "spans": [
                    {
                        "service": "gateway",
                        "span_name": "HTTP POST /api/v1/checkout",
                        "duration_ms": 2600.0,
                        "status": "ERROR",
                        "error": True,
                    },
                    {
                        "service": "booking-api",
                        "span_name": "process_booking",
                        "duration_ms": 2550.0,
                        "status": "ERROR",
                        "error": True,
                    },
                    {
                        "service": "postgres",
                        "span_name": "pg_query_execute",
                        "statement": "SELECT * FROM reservations WHERE id = $1 FOR UPDATE",
                        "duration_ms": 2480.0,
                        "status": "OK",
                        "error": False,
                    },
                ],
            },
        }
    ]

    extractor = TraceEvidenceExtractor()
    evidence_items = extractor.extract_trace_evidence(signals)

    assert len(evidence_items) >= 3
    # Check postgres bottleneck span
    pg_evidence = next((e for e in evidence_items if e.service == "postgres"), None)
    assert pg_evidence is not None
    assert pg_evidence.duration_ms == 2480.0
    assert pg_evidence.is_bottleneck is True
    assert pg_evidence.strength >= 0.70
    assert "database span latency" in pg_evidence.description


def test_log_trace_correlation(base_time):
    """Verify logs sharing trace_id with slow spans amplify trace evidence strength."""
    signals = [
        {
            "signal_id": "sig-log-db-1",
            "signal_type": "EVENT",
            "service": "postgres",
            "timestamp": base_time + timedelta(seconds=10),
            "severity": "CRITICAL",
            "message": "Query wait lock timeout on relation reservations",
            "metadata": {"trace_id": "trace-shared-123"},
        },
        {
            "signal_id": "sig-api-lat-1",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=15),
            "severity": "ERROR",
            "metadata": {
                "trace_id": "trace-shared-123",
                "spans": [
                    {
                        "service": "postgres",
                        "span_name": "SELECT lock acquisition",
                        "duration_ms": 1800.0,
                        "status": "ERROR",
                        "error": True,
                    }
                ],
            },
        },
    ]

    extractor = TraceEvidenceExtractor()
    evidence_items = extractor.extract_trace_evidence(signals)
    pg_trace = next((e for e in evidence_items if e.service == "postgres"), None)

    assert pg_trace is not None
    assert "sig-log-db-1" in pg_trace.linked_log_ids
    assert pg_trace.strength >= 0.85


def test_deployment_timing_and_scoring(base_time):
    """Verify deployment preceding symptoms by 2 minutes receives high score and detailed description."""
    signals = [
        {
            "signal_id": "sig-dep-1",
            "signal_type": "DEPLOYMENT",
            "service": "booking-api",
            "timestamp": base_time,
            "severity": "INFO",
            "metadata": {"version": "v2.4.0", "environment": "production"},
        },
        {
            "signal_id": "sig-anom-1",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=120),
            "severity": "CRITICAL",
            "metadata": {"metric_name": "api_error_rate_5xx", "value": 0.35},
        },
        {
            "signal_id": "sig-err-1",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=140),
            "severity": "ERROR",
            "message": "Uncaught NullPointerException in PaymentProcessor.java:82",
        },
    ]

    evaluator = DeploymentEvidenceEvaluator()
    results = evaluator.evaluate(signals)

    assert len(results) == 1
    dep_res = results[0]
    assert dep_res.is_causally_plausible is True
    assert dep_res.score >= 0.80
    assert "v2.4.0 deployed on booking-api 2m prior to degradation" in dep_res.description


def test_service_topology_validation():
    """Verify service dependency graph accurately evaluates upstream causality."""
    topology = get_service_topology_graph()

    # Direct dependencies
    assert topology.is_dependency("postgres", "booking-api") is True
    assert topology.is_dependency("postgres", "payment-service") is True
    assert topology.is_dependency("redis", "cache-service") is True
    assert topology.is_dependency("redis", "booking-api") is True  # Transitive: booking-api -> cache-service -> redis

    # Transitive dependency: gateway -> booking-api -> postgres
    assert topology.is_dependency("postgres", "gateway") is True

    # Path retrieval
    path = topology.get_dependency_path("gateway", "postgres")
    assert len(path) >= 3
    assert path[0] == "gateway"
    assert path[-1] == "postgres"

    # Non-dependency: postgres does NOT depend on gateway
    assert topology.is_dependency("gateway", "postgres") is False


def test_scenario_database_failure(base_time):
    """
    Test Scenario 1: Database Failure
    DB latency + DB connection saturation + DB timeout logs + slow postgres span + API 500
    -> Database root cause ranks #1 with high confidence.
    """
    signals = [
        {
            "signal_id": "sig-db-lat",
            "signal_type": "ANOMALY",
            "service": "postgres",
            "timestamp": base_time,
            "severity": "CRITICAL",
            "metadata": {"metric_name": "db_query_latency_ms", "value": 4500.0},
        },
        {
            "signal_id": "sig-db-pool",
            "signal_type": "ANOMALY",
            "service": "postgres",
            "timestamp": base_time + timedelta(seconds=15),
            "severity": "CRITICAL",
            "metadata": {"metric_name": "db_active_connections", "value": 100.0, "max_pool": 100},
        },
        {
            "signal_id": "sig-db-log",
            "signal_type": "EVENT",
            "service": "postgres",
            "timestamp": base_time + timedelta(seconds=20),
            "severity": "CRITICAL",
            "message": "Connection to PostgreSQL database timed out after 30000ms: pool exhausted",
            "metadata": {"cluster_label": "database_timeout", "cluster_category": "DATABASE", "trace_id": "trace-db-881"},
        },
        {
            "signal_id": "sig-api-err",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=45),
            "severity": "ERROR",
            "message": "HTTP 500: could not obtain database connection from pool",
            "metadata": {
                "trace_id": "trace-db-881",
                "spans": [
                    {
                        "service": "postgres",
                        "span_name": "acquire_connection",
                        "duration_ms": 3200.0,
                        "status": "ERROR",
                        "error": True,
                    }
                ],
            },
        },
    ]

    analyzer = RCAAnalyzer()
    result = analyzer.analyze({"group_key": "grp-db-001", "signals": signals})

    assert result["primary_confidence"] >= 0.75
    assert any(term in result["primary_root_cause"].lower() for term in ["database", "postgres", "connection", "saturation"])

    # Verify Top-3 candidate structure and evidence breakdown
    top_cand = result["candidates"][0]
    assert top_cand["candidate_type"] == "DATABASE"
    assert top_cand["rank"] == 1
    assert top_cand["is_primary"] is True
    assert "postgres" in top_cand["affected_services"]
    assert "booking-api" in top_cand["affected_services"]

    breakdown = top_cand["evidence_breakdown"]
    assert "Initiated" in breakdown["temporal"]
    assert "postgres" in breakdown["metric"].lower()
    assert "database_timeout" in breakdown["log"]
    assert "acquire_connection" in breakdown["trace"] or "3200ms" in breakdown["trace"]
    assert "upstream dependency" in breakdown["topology"]


def test_scenario_bad_deployment(base_time):
    """
    Test Scenario 2: Bad Deployment
    Deployment on booking-api -> application error spike -> 5xx errors
    -> Bad deployment root cause ranks #1.
    """
    signals = [
        {
            "signal_id": "sig-dep-v24",
            "signal_type": "DEPLOYMENT",
            "service": "booking-api",
            "timestamp": base_time,
            "severity": "INFO",
            "metadata": {"version": "v2.4.1-rc1", "environment": "production"},
        },
        {
            "signal_id": "sig-api-err",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=60),
            "severity": "CRITICAL",
            "metadata": {"metric_name": "http_requests_5xx_rate", "value": 0.48},
        },
        {
            "signal_id": "sig-log-err",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=70),
            "severity": "ERROR",
            "message": "NullPointerException in routes/booking.py:112 after new feature flag enabled",
            "metadata": {"cluster_label": "service_exception"},
        },
    ]

    analyzer = RCAAnalyzer()
    result = analyzer.analyze({"group_key": "grp-deploy-001", "signals": signals})

    assert result["primary_confidence"] >= 0.70
    assert "deployment" in result["primary_root_cause"].lower()

    top_cand = result["candidates"][0]
    assert top_cand["candidate_type"] == "DEPLOYMENT"
    assert "v2.4.1-rc1" in top_cand["candidate_name"] or "booking-api" in top_cand["candidate_name"]


def test_scenario_redis_failure(base_time):
    """
    Test Scenario 3: Redis / Cache Failure
    Redis connection refused -> Cache miss spike -> API degradation
    -> Redis/Cache failure ranks #1.
    """
    signals = [
        {
            "signal_id": "sig-redis-err",
            "signal_type": "EVENT",
            "service": "cache-service",
            "timestamp": base_time,
            "severity": "CRITICAL",
            "message": "Redis connection refused: cluster node 10.0.3.1:6379 unavailable",
            "metadata": {"cluster_label": "cache_timeout", "cluster_category": "CACHE", "trace_id": "trace-cache-1"},
        },
        {
            "signal_id": "sig-cache-lat",
            "signal_type": "ANOMALY",
            "service": "cache-service",
            "timestamp": base_time + timedelta(seconds=10),
            "severity": "ERROR",
            "metadata": {
                "metric_name": "cache_miss_rate",
                "value": 0.99,
                "spans": [{"service": "cache-service", "span_name": "redis.get", "duration_ms": 1200.0, "status": "ERROR"}],
            },
        },
        {
            "signal_id": "sig-catalog-deg",
            "signal_type": "EVENT",
            "service": "catalog-api",
            "timestamp": base_time + timedelta(seconds=25),
            "severity": "WARNING",
            "message": "Catalog response latency elevated due to cache miss fallback",
        },
    ]

    analyzer = RCAAnalyzer()
    result = analyzer.analyze({"group_key": "grp-cache-001", "signals": signals})

    assert result["primary_confidence"] >= 0.70
    assert "redis" in result["primary_root_cause"].lower() or "cache" in result["primary_root_cause"].lower()
    top_cand = result["candidates"][0]
    assert top_cand["candidate_type"] in ["DEPENDENCY", "SERVICE"]


def test_scenario_memory_exhaustion(base_time):
    """
    Test Scenario 4: Memory / Resource Exhaustion
    Memory usage 98% -> GC pause anomaly -> OOM kill
    -> Memory/Resource exhaustion ranks #1.
    """
    signals = [
        {
            "signal_id": "sig-mem-spike",
            "signal_type": "ANOMALY",
            "service": "catalog-api",
            "timestamp": base_time,
            "severity": "CRITICAL",
            "metadata": {"metric_name": "jvm_memory_used_bytes", "value": 0.98},
        },
        {
            "signal_id": "sig-gc-pause",
            "signal_type": "ANOMALY",
            "service": "catalog-api",
            "timestamp": base_time + timedelta(seconds=15),
            "severity": "CRITICAL",
            "metadata": {"metric_name": "gc_pause_duration_ms", "value": 3800.0},
        },
        {
            "signal_id": "sig-oom-log",
            "signal_type": "EVENT",
            "service": "catalog-api",
            "timestamp": base_time + timedelta(seconds=25),
            "severity": "CRITICAL",
            "message": "Process terminated by kernel: Out of memory (OOM) killer invoked",
            "metadata": {"cluster_label": "resource_exhaustion"},
        },
    ]

    analyzer = RCAAnalyzer()
    result = analyzer.analyze({"group_key": "grp-oom-001", "signals": signals})

    assert result["primary_confidence"] >= 0.75
    assert "memory" in result["primary_root_cause"].lower() or "resource" in result["primary_root_cause"].lower()
    top_cand = result["candidates"][0]
    assert top_cand["candidate_type"] == "RESOURCE"


def test_scenario_ambiguous_and_unknown(base_time):
    """
    Test Scenario 5: Ambiguous / Insufficient Evidence
    Isolated, weak downstream symptoms without identifiable root cause
    -> Returns UNKNOWN with low confidence.
    """
    signals = [
        {
            "signal_id": "sig-noise-1",
            "signal_type": "EVENT",
            "service": "gateway",
            "timestamp": base_time,
            "severity": "INFO",
            "message": "Routine token renewal completed",
        }
    ]

    analyzer = RCAAnalyzer()
    result = analyzer.analyze({"group_key": "grp-noise-001", "signals": signals})

    assert result["primary_root_cause"] in ["UNKNOWN", "Insufficient evidence"]
    assert result["primary_confidence"] <= 0.35
    top_cand = result["candidates"][0]
    assert top_cand["candidate_type"] == "UNKNOWN"
    assert top_cand["evidence_breakdown"]["temporal"] == "No dominant temporal trigger identified across signals"


def test_top_3_candidates_and_breakdown(base_time):
    """Verify RCA produces up to Top-3 ranked candidates with structured evidence breakdown."""
    signals = [
        {
            "signal_id": "sig-db-1",
            "signal_type": "ANOMALY",
            "service": "postgres",
            "timestamp": base_time,
            "severity": "CRITICAL",
            "metadata": {"metric_name": "db_query_latency_ms", "value": 3000.0},
        },
        {
            "signal_id": "sig-dep-1",
            "signal_type": "DEPLOYMENT",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=10),
            "severity": "INFO",
            "metadata": {"version": "v1.9.0"},
        },
        {
            "signal_id": "sig-api-1",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": base_time + timedelta(seconds=30),
            "severity": "ERROR",
            "message": "HTTP 500 error in checkout",
        },
    ]

    analyzer = RCAAnalyzer()
    result = analyzer.analyze({"group_key": "grp-multi-001", "signals": signals})

    assert 1 <= len(result["candidates"]) <= 3
    for idx, c in enumerate(result["candidates"], start=1):
        assert c["rank"] == idx
        assert c["is_primary"] == (idx == 1)
        assert 0.0 <= c["confidence"] <= 1.0
        assert len(c["affected_services"]) >= 1
        assert "evidence_breakdown" in c
        breakdown = c["evidence_breakdown"]
        assert all(k in breakdown for k in ["temporal", "metric", "log", "trace", "topology", "deployment", "historical"])
