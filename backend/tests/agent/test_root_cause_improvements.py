from datetime import datetime, timezone
import pytest

from backend.app.agent.graph.nodes.produce_report import produce_report_node
from backend.app.agent.graph.state import InvestigationState
from backend.app.agent.schemas.investigation import InvestigationStatus
from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.causal_graph import CausalGraphBuilder
from backend.app.rca.analysis.scoring import CandidateScorer


def test_disambiguate_stale_deployment_vs_db_pool():
    """
    Scenario SCN-01 pattern:
    Stale deployment occurred 20 minutes prior to database pool saturation.
    Causal scoring must penalize the stale deployment and rank the database connection
    pool exhaustion as Top-1.
    """
    signals = [
        {
            "signal_id": "dep-stale-01",
            "signal_type": "DEPLOYMENT",
            "service": "order-service",
            "timestamp": "2026-10-20T09:50:00Z",
            "severity": "INFO",
            "metadata": {"version": "v2.4.0"},
        },
        {
            "signal_id": "anom-db-pool-01",
            "signal_type": "ANOMALY",
            "service": "order-service",
            "timestamp": "2026-10-20T10:10:00Z",
            "severity": "CRITICAL",
            "metadata": {
                "metric_name": "db_connection_pool_utilization",
                "value": 0.98,
                "threshold": 0.85,
            },
        },
        {
            "signal_id": "err-pool-exhausted-01",
            "signal_type": "EVENT",
            "service": "order-service",
            "timestamp": "2026-10-20T10:10:15Z",
            "severity": "ERROR",
            "message": "database connection pool exhausted: could not acquire connection within timeout",
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_types = [c["candidate_type"] for c in candidates]
    assert "DATABASE" in cand_types
    assert "DEPLOYMENT" in cand_types

    edges, _ = CausalGraphBuilder.build_graph(signals)
    scorer = CandidateScorer()
    scored = scorer.score_candidates(candidates, signals, edges)

    assert len(scored) >= 1
    top_candidate = scored[0]
    assert top_candidate["candidate_type"] == "DATABASE"
    assert "Database connection pool exhaustion" in top_candidate["candidate_name"]
    assert top_candidate["score"] > 0.50


def test_downstream_partner_timeout_candidate():
    """
    Scenario SCN-06 pattern:
    HTTPClientPool / external partner timeout logs must be categorized as
    DEPENDENCY: Downstream dependency timeout, not DATABASE degradation.
    """
    signals = [
        {
            "signal_id": "err-downstream-01",
            "signal_type": "EVENT",
            "service": "payment-gateway",
            "timestamp": "2026-10-20T10:00:00Z",
            "severity": "ERROR",
            "message": "HTTPClientPool connection timeout calling partner gateway external endpoint 504 Gateway Timeout",
        },
        {
            "signal_id": "anom-latency-01",
            "signal_type": "ANOMALY",
            "service": "payment-gateway",
            "timestamp": "2026-10-20T10:00:05Z",
            "severity": "HIGH",
            "metadata": {
                "metric_name": "http_request_duration_seconds",
                "value": 15.2,
                "threshold": 2.0,
            },
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_types = [c["candidate_type"] for c in candidates]
    assert "DEPENDENCY" in cand_types
    assert "DATABASE" not in cand_types

    dep_candidate = next(c for c in candidates if c["candidate_type"] == "DEPENDENCY")
    assert "Downstream dependency timeout" in dep_candidate["candidate_name"]


def test_storage_disk_exhaustion_candidate():
    """
    Scenario SCN-09 pattern:
    Disk full, enospc, and filesystem partition errors must generate
    RESOURCE: Disk space exhaustion, not Memory exhaustion.
    """
    signals = [
        {
            "signal_id": "err-disk-01",
            "signal_type": "EVENT",
            "service": "indexing-service",
            "timestamp": "2026-10-20T11:00:00Z",
            "severity": "FATAL",
            "message": "ENOSPC: no space left on device, disk full on /var/data partition buffer flush failed",
        },
        {
            "signal_id": "anom-disk-01",
            "signal_type": "ANOMALY",
            "service": "indexing-service",
            "timestamp": "2026-10-20T11:00:10Z",
            "severity": "CRITICAL",
            "metadata": {
                "metric_name": "disk_space_utilization",
                "value": 0.99,
                "threshold": 0.85,
            },
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_types = [c["candidate_type"] for c in candidates]
    assert "RESOURCE" in cand_types

    disk_cand = next(c for c in candidates if c["candidate_type"] == "RESOURCE")
    assert "Disk space exhaustion" in disk_cand["candidate_name"]


def test_authentication_failure_candidate():
    """
    Scenario SCN-10 pattern:
    JWT key rotation and unauthorized 401 logs must produce
    DEPENDENCY: Authentication failure, not Redis cache failure.
    """
    signals = [
        {
            "signal_id": "err-auth-01",
            "signal_type": "EVENT",
            "service": "api-gateway",
            "timestamp": "2026-10-20T12:00:00Z",
            "severity": "ERROR",
            "message": "JWT signature verification failed: unauthorized 401 invalid bearer token, JWKS key id not found in cached keyset",
        },
        {
            "signal_id": "anom-401-01",
            "signal_type": "ANOMALY",
            "service": "api-gateway",
            "timestamp": "2026-10-20T12:00:05Z",
            "severity": "HIGH",
            "metadata": {
                "metric_name": "http_401_rate",
                "value": 0.45,
                "threshold": 0.05,
            },
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_types = [c["candidate_type"] for c in candidates]
    assert "DEPENDENCY" in cand_types
    assert "CACHE" not in cand_types

    auth_cand = next(c for c in candidates if c["candidate_type"] == "DEPENDENCY")
    assert "Authentication failure" in auth_cand["candidate_name"]


def test_nominal_telemetry_insufficient_evidence_abstention():
    """
    Scenario SCN-11 pattern:
    When telemetry is completely nominal (0 anomalies, 0 error logs, no deployment),
    the system must abstain and produce INSUFFICIENT_EVIDENCE status.
    """
    signals = [
        {
            "signal_id": "sig-nom-01",
            "signal_type": "METRIC",
            "service": "auth-service",
            "timestamp": "2026-10-20T13:00:00Z",
            "severity": "INFO",
            "metadata": {"cpu_utilization": 0.25, "memory_utilization": 0.40},
        },
        {
            "signal_id": "sig-nom-02",
            "signal_type": "EVENT",
            "service": "auth-service",
            "timestamp": "2026-10-20T13:00:30Z",
            "severity": "INFO",
            "message": "Routine health check succeeded",
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "UNKNOWN"
    assert "Insufficient evidence" in candidates[0]["candidate_name"]

    # Verify produce_report_node converts this into INSUFFICIENT_EVIDENCE status
    state: InvestigationState = {
        "incident_key": "INC-NOMINAL-TEST",
        "hypotheses": [
            {
                "hypothesis_id": "hyp-unknown",
                "candidate_name": candidates[0]["candidate_name"],
                "candidate_type": "UNKNOWN",
                "confidence": 0.10,
                "evidence": [],
                "affected_services": ["auth-service"],
            }
        ],
        "evidence": [],
        "iteration_count": 1,
        "investigation_complete": True,
        "confidence_threshold": 0.70,
        "target_service": "auth-service",
        "environment": "production",
        "telemetry_evidence": {},
        "rca_result": None,
        "runbooks": [],
        "missing_evidence": [],
        "report": None,
        "status": InvestigationStatus.INVESTIGATING,
    }

    result = produce_report_node(state)
    assert result["status"] in (InvestigationStatus.INSUFFICIENT_EVIDENCE, InvestigationStatus.INSUFFICIENT_EVIDENCE.value)
    assert "Insufficient" in result["final_report"]["leading_hypothesis"]


def test_multi_signal_ambiguity_inconclusive_abstention():
    """
    Scenario SCN-12 pattern:
    Multiple weak competing signals without a dominant anomaly should yield
    an inconclusive candidate with low confidence and mark INSUFFICIENT_EVIDENCE.
    """
    signals = [
        {
            "signal_id": "sig-weak-1",
            "signal_type": "EVENT",
            "service": "service-a",
            "timestamp": "2026-10-20T14:00:00Z",
            "severity": "WARNING",
            "message": "Minor transient retry on connection",
        },
        {
            "signal_id": "sig-weak-2",
            "signal_type": "EVENT",
            "service": "service-b",
            "timestamp": "2026-10-20T14:00:02Z",
            "severity": "WARNING",
            "message": "Mild cache latency increase",
        },
    ]

    candidates = [
        {
            "candidate_type": "SERVICE",
            "candidate_name": "Transient warning on service-a",
            "service": "service-a",
            "associated_signal_ids": ["sig-weak-1"],
            "evidence": [],
        },
        {
            "candidate_type": "SERVICE",
            "candidate_name": "Transient warning on service-b",
            "service": "service-b",
            "associated_signal_ids": ["sig-weak-2"],
            "evidence": [],
        },
    ]

    edges, _ = CausalGraphBuilder.build_graph(signals)
    scorer = CandidateScorer()
    scored = scorer.score_candidates(candidates, signals, edges)

    assert len(scored) == 1
    assert scored[0]["candidate_type"] == "UNKNOWN"
    assert "Inconclusive" in scored[0]["candidate_name"]
    assert scored[0]["confidence"] <= 0.40

    # Verify produce_report_node marks status as INSUFFICIENT_EVIDENCE
    state: InvestigationState = {
        "incident_key": "INC-AMBIGUOUS-TEST",
        "hypotheses": scored,
        "evidence": [],
        "iteration_count": 1,
        "investigation_complete": True,
        "confidence_threshold": 0.70,
        "target_service": "service-a",
        "environment": "production",
        "telemetry_evidence": {},
        "rca_result": None,
        "runbooks": [],
        "missing_evidence": [],
        "report": None,
        "status": InvestigationStatus.INVESTIGATING,
    }

    result = produce_report_node(state)
    assert result["status"] == InvestigationStatus.INSUFFICIENT_EVIDENCE


def test_causal_graph_bounding_prevents_quadratic_explosion():
    """
    Ensure CausalGraphBuilder bounds input signals to 50 and edges to 100,
    guaranteeing deterministic O(1) upper-bounded performance under telemetry floods.
    """
    large_signal_set = []
    base_time = 1700000000
    for i in range(120):
        large_signal_set.append({
            "signal_id": f"flood-sig-{i:03d}",
            "signal_type": "EVENT" if i % 2 == 0 else "ANOMALY",
            "service": f"microservice-{(i % 5):02d}",
            "timestamp": datetime.fromtimestamp(base_time + i * 2, tz=timezone.utc).isoformat(),
            "severity": "HIGH" if i % 3 == 0 else "INFO",
            "message": f"Telemetry event payload iteration {i}",
        })

    edges, chain = CausalGraphBuilder.build_graph(large_signal_set)

    assert len(edges) <= 100
    assert len(chain) <= 50



def test_coredns_resolution_failure_candidate():
    """
    Scenario PILOT-CASE-04 pattern:
    CoreDNS UDP timeout and elevated DNS latency must generate
    CoreDNS resolution failure, not a downstream partner gateway outage.
    """
    signals = [
        {
            "signal_id": "anom-dns-lat-01",
            "signal_type": "ANOMALY",
            "service": "checkout-api",
            "timestamp": "2026-10-20T11:10:00Z",
            "severity": "CRITICAL",
            "metadata": {
                "metric_name": "dns_resolution_latency_ms",
                "value": 2800.0,
                "threshold": 500.0,
            },
        },
        {
            "signal_id": "err-coredns-01",
            "signal_type": "EVENT",
            "service": "checkout-api",
            "timestamp": "2026-10-20T11:11:00Z",
            "severity": "WARN",
            "message": "CoreDNS: Resolving partner-pay.external.net via upstream UDP 10.96.0.10:53 timed out",
        },
        {
            "signal_id": "err-connect-01",
            "signal_type": "EVENT",
            "service": "checkout-api",
            "timestamp": "2026-10-20T11:12:00Z",
            "severity": "ERROR",
            "message": "ConnectTimeoutException: Timeout resolving partner-pay.external.net (CoreDNS drop)",
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_names = [c["candidate_name"] for c in candidates]
    assert any("CoreDNS resolution failure" in name for name in cand_names)

    edges, _ = CausalGraphBuilder.build_graph(signals)
    scorer = CandidateScorer()
    scored = scorer.score_candidates(candidates, signals, edges)

    top_cand = scored[0]
    assert "CoreDNS resolution failure" in top_cand["candidate_name"]
    assert top_cand["score"] >= 0.85


def test_kafka_poison_pill_vs_consumer_lag():
    """
    Scenario PILOT-CASE-08 pattern:
    1. A poison-pill deserialization exception combined with lag must produce
       'Kafka consumer stall caused by poison pill'.
    2. Consumer lag alone with nominal processing must produce
       'Kafka consumer lag backlog' without poison pill accusation.
    """
    # 1. Poison-pill test
    poison_signals = [
        {
            "signal_id": "anom-lag-01",
            "signal_type": "ANOMALY",
            "service": "fulfillment-stream",
            "timestamp": "2026-10-20T11:10:00Z",
            "severity": "CRITICAL",
            "metadata": {
                "metric_name": "kafka_consumer_lag_records",
                "value": 48000.0,
                "threshold": 1000.0,
            },
        },
        {
            "signal_id": "err-deserial-01",
            "signal_type": "EVENT",
            "service": "fulfillment-stream",
            "timestamp": "2026-10-20T11:12:00Z",
            "severity": "ERROR",
            "message": "DeserializationException: Malformed JSON payload at offset 1294101; poison pill blocking consumer thread",
        },
    ]

    poison_cands = CandidateGenerator.generate_candidates(poison_signals)
    poison_names = [c["candidate_name"] for c in poison_cands]
    assert any("poison pill" in name.lower() for name in poison_names)

    scorer = CandidateScorer()
    poison_scored = scorer.score_candidates(poison_cands, poison_signals, [])
    assert "poison pill" in poison_scored[0]["candidate_name"].lower()
    assert poison_scored[0]["score"] >= 0.85

    # 2. Nominal lag test (no poison pill)
    lag_only_signals = [
        {
            "signal_id": "anom-lag-02",
            "signal_type": "ANOMALY",
            "service": "fulfillment-stream",
            "timestamp": "2026-10-20T11:10:00Z",
            "severity": "HIGH",
            "metadata": {
                "metric_name": "kafka_consumer_lag_records",
                "value": 15000.0,
                "threshold": 1000.0,
            },
        },
        {
            "signal_id": "evt-rebal-01",
            "signal_type": "EVENT",
            "service": "fulfillment-stream",
            "timestamp": "2026-10-20T11:11:00Z",
            "severity": "INFO",
            "message": "ConsumerCoordinator: Successfully joined group notification-group; partitions assigned",
        },
    ]

    lag_cands = CandidateGenerator.generate_candidates(lag_only_signals)
    lag_scored = scorer.score_candidates(lag_cands, lag_only_signals, [])
    assert "poison" not in lag_scored[0]["candidate_name"].lower()
    assert "lag backlog" in lag_scored[0]["candidate_name"].lower()


def test_dns_negative_control_discrimination():
    """
    Negative Control: Outbound HTTP 504 from partner gateway with nominal DNS resolution.
    Must diagnose Downstream dependency timeout, NOT DNS failure.
    """
    signals = [
        {
            "signal_id": "anom-timeout-01",
            "signal_type": "ANOMALY",
            "service": "checkout-gateway",
            "timestamp": "2026-10-20T14:10:00Z",
            "severity": "HIGH",
            "metadata": {
                "metric_name": "http_client_request_timeout_ratio",
                "value": 0.65,
                "threshold": 0.10,
            },
        },
        {
            "signal_id": "nom-dns-01",
            "signal_type": "METRIC",
            "service": "checkout-gateway",
            "timestamp": "2026-10-20T14:10:00Z",
            "severity": "INFO",
            "metadata": {
                "metric_name": "dns_resolution_latency_ms",
                "value": 1.8,
            },
        },
        {
            "signal_id": "err-504-01",
            "signal_type": "EVENT",
            "service": "checkout-gateway",
            "timestamp": "2026-10-20T14:12:00Z",
            "severity": "ERROR",
            "message": "HTTP 504 Gateway Timeout received from external partner payment provider https://api.stripe.com",
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    scorer = CandidateScorer()
    scored = scorer.score_candidates(candidates, signals, [])

    top_cand = scored[0]
    assert "Downstream dependency timeout" in top_cand["candidate_name"]
    assert "dns" not in top_cand["candidate_name"].lower()
    assert "coredns" not in top_cand["candidate_name"].lower()


def test_evidence_citation_validator_strictness():
    """
    Verifies that EvidenceCitationValidator strictly:
    1. Accepts valid direct telemetry citations.
    2. Rejects cross-tenant citations.
    3. Identifies cross-incident historical RAG references.
    4. Rejects malformed IDs.
    5. Accounts for uncited material without silently removing difficult citations.
    """
    from backend.app.agent.services.citation_validator import (
        EvidenceCitationValidator,
        CitationClassification,
    )

    evidence_items = [
        {
            "evidence_id": "EV-PROM-1",
            "source_type": "PROMETHEUS",
            "source_id": "prom-svc-cpu",
            "service": "order-service",
            "claim": "High CPU utilization = 0.95",
            "data": {"org_id": "tenant-alpha", "incident_key": "INC-100"},
        },
        {
            "evidence_id": "EV-X-TENANT",
            "source_type": "PROMETHEUS",
            "source_id": "prom-other-db",
            "service": "order-service",
            "claim": "Database utilization = 0.99",
            "data": {"org_id": "tenant-beta", "incident_key": "INC-100"},
        },
        {
            "evidence_id": "EV-SIM-1",
            "source_type": "HISTORICAL_INCIDENT",
            "source_id": "INC-HISTORICAL-999",
            "service": "order-service",
            "claim": "Historical similar incident from last year",
            "data": {"org_id": "tenant-alpha", "incident_key": "INC-HISTORICAL-999"},
        },
        {
            "evidence_id": "BAD_ID",
            "source_type": "PROMETHEUS",
            "source_id": "prom-malformed",
            "service": "order-service",
            "claim": "Malformed ID without EV- prefix",
            "data": {},
        },
    ]

    hypotheses = [
        {
            "hypothesis": "CPU saturation",
            "supporting_evidence_ids": ["EV-PROM-1"],
        }
    ]

    audit = EvidenceCitationValidator.audit_investigation(
        evidence_items=evidence_items,
        hypotheses=hypotheses,
        tenant_id="tenant-alpha",
        incident_key="INC-100",
        raw_telemetry={"metrics": [{"metric_name": "cpu", "service": "svc"}]},
    )

    assert audit["total_citations_evaluated"] == 4
    assert audit["valid_citations_count"] == 1
    assert audit["invalid_citations_count"] == 3
    assert audit["breakdown"]["valid"] == 1
    assert audit["breakdown"]["cross_tenant"] == 1
    assert audit["breakdown"]["cross_incident"] == 1
    assert audit["breakdown"]["malformed"] == 1
    assert audit["breakdown"]["missing_or_unresolved"] == 0
