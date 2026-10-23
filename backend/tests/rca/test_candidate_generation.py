from backend.app.rca.analysis.candidate_generator import CandidateGenerator


def test_database_candidate_generation():
    """Test that database latency and connection pool signals produce a DATABASE candidate."""
    signals = [
        {
            "signal_id": "anom-db-001",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:01:30Z",
            "severity": "HIGH",
            "metadata": {"metric_name": "db_query_latency"},
        },
        {
            "signal_id": "err-pool-001",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:02:00Z",
            "severity": "ERROR",
            "message": "database connection pool exhausted",
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_types = [c["candidate_type"] for c in candidates]
    assert "DATABASE" in cand_types
    db_cand = next(c for c in candidates if c["candidate_type"] == "DATABASE")
    assert any(term in db_cand["candidate_name"] for term in ("Database degradation on booking-api", "Database connection pool exhaustion on booking-api"))
    assert len(db_cand["evidence"]) > 0


def test_deployment_candidate_generation():
    """Test that a deployment signal produces a DEPLOYMENT candidate."""
    signals = [
        {
            "signal_id": "dep-001",
            "signal_type": "DEPLOYMENT",
            "service": "checkout-api",
            "timestamp": "2026-08-29T12:00:00Z",
            "severity": "INFO",
            "metadata": {"version": "v3.0.1"},
        },
        {
            "signal_id": "anom-001",
            "signal_type": "ANOMALY",
            "service": "checkout-api",
            "timestamp": "2026-08-29T12:02:00Z",
            "severity": "CRITICAL",
            "metadata": {"metric_name": "request_latency"},
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_types = [c["candidate_type"] for c in candidates]
    assert "DEPLOYMENT" in cand_types
    dep_cand = next(c for c in candidates if c["candidate_type"] == "DEPLOYMENT")
    assert "Recent deployment on checkout-api" in dep_cand["candidate_name"]


def test_infrastructure_candidate_generation():
    """Test that CPU/Memory saturation signals produce an INFRASTRUCTURE candidate."""
    signals = [
        {
            "signal_id": "anom-cpu-001",
            "signal_type": "ANOMALY",
            "service": "worker-service",
            "timestamp": "2026-08-29T12:00:00Z",
            "severity": "HIGH",
            "metadata": {"metric_name": "cpu_utilization_saturation"},
        }
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_types = [c["candidate_type"] for c in candidates]
    assert "INFRASTRUCTURE" in cand_types


def test_insufficient_evidence_for_isolated_symptom():
    """Test that a solitary downstream HTTP error without upstream signals returns Insufficient evidence."""
    signals = [
        {
            "signal_id": "err-500",
            "signal_type": "EVENT",
            "service": "gateway-api",
            "timestamp": "2026-08-29T12:00:00Z",
            "severity": "ERROR",
            "message": "HTTP 500 Internal Server Error",
        }
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "UNKNOWN"
    assert candidates[0]["candidate_name"] == "Insufficient evidence"
