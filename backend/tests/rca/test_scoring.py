from datetime import datetime, timezone
from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.causal_graph import CausalGraphBuilder
from backend.app.rca.analysis.scoring import CandidateScorer


def test_database_degradation_ranking_scenario():
    """Test standard production failure cascade where Database degradation is correctly ranked as primary root cause."""
    signals = [
        {
            "signal_id": "dep-001",
            "signal_type": "DEPLOYMENT",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:00:00Z",
            "severity": "INFO",
            "metadata": {"version": "v2.1.0"},
            "relationship_score": 0.75,
        },
        {
            "signal_id": "anom-db-001",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:01:30Z",
            "severity": "HIGH",
            "metadata": {"metric_name": "db_query_latency"},
            "relationship_score": 0.90,
        },
        {
            "signal_id": "err-pool-001",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:02:00Z",
            "severity": "ERROR",
            "message": "database connection pool exhausted",
            "relationship_score": 0.88,
        },
        {
            "signal_id": "anom-api-001",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:02:20Z",
            "severity": "HIGH",
            "metadata": {"metric_name": "request_latency"},
            "relationship_score": 0.85,
        },
        {
            "signal_id": "err-500-001",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:02:30Z",
            "severity": "ERROR",
            "message": "HTTP 500 Internal Server Error",
            "relationship_score": 0.80,
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    edges, _ = CausalGraphBuilder.build_graph(signals)
    scorer = CandidateScorer()

    ranked = scorer.score_candidates(candidates, signals, edges)

    assert len(ranked) >= 2
    # Verify primary candidate
    primary = ranked[0]
    assert primary["is_primary"] is True
    assert primary["rank"] == 1
    assert primary["candidate_type"] in ["DATABASE", "DEPLOYMENT"]
    assert primary["score"] >= 0.70

    # Ensure downstream symptoms rank below upstream causes
    types_in_order = [c["candidate_type"] for c in ranked]
    assert "DATABASE" in types_in_order


def test_downstream_symptom_not_top_cause():
    """Verify that late downstream symptoms (e.g. HTTP 500) rank below upstream causes."""
    signals = [
        {
            "signal_id": "anom-db-001",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:00:00Z",
            "severity": "HIGH",
            "metadata": {"metric_name": "db_latency"},
            "relationship_score": 0.90,
        },
        {
            "signal_id": "err-500-001",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:05:00Z",
            "severity": "CRITICAL",
            "message": "HTTP 500 Server Error",
            "relationship_score": 0.70,
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    edges, _ = CausalGraphBuilder.build_graph(signals)
    scorer = CandidateScorer()

    ranked = scorer.score_candidates(candidates, signals, edges)
    assert ranked[0]["candidate_type"] == "DATABASE"
    assert ranked[0]["is_primary"] is True
