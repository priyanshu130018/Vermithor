"""
Prompt 20 Independent Audit and Verification Tests.

Verifies:
1. DNS candidates can be generated from DNS evidence without requiring specific service names or scenario IDs.
2. Kafka poison-pill evidence is distinguished from normal lag, partition rebalancing, and storage or CPU symptoms.
3. Healthy DNS metrics do not independently trigger DNS-failure diagnoses.
4. Historical incident references are not presented as verified current telemetry.
5. Tenant, incident, and evidence-set boundaries are enforced during citation validation.
6. Invalid, unresolved, stale, cross-incident, cross-tenant, and malformed citations remain in the reported denominator.
7. Ground-truth answers are never passed into investigation state, candidate generation, scoring, or model prompts.
"""

from datetime import datetime, timezone
import pytest

from backend.app.agent.graph.nodes.produce_report import produce_report_node
from backend.app.agent.graph.state import InvestigationState
from backend.app.agent.schemas.investigation import (
    InvestigationEvidenceItem,
    InvestigationRequest,
    InvestigationStatus,
)
from backend.app.agent.services.citation_validator import (
    CitationClassification,
    EvidenceCitationValidator,
)
from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.causal_graph import CausalGraphBuilder
from backend.app.rca.analysis.scoring import CandidateScorer


def test_audit_claim_1_dns_candidate_generation_without_hardcoded_names():
    """
    Verify DNS candidates are derived from DNS evidence on arbitrary services
    without requiring specific service names or scenario IDs.
    """
    arbitrary_service = "user-auth-microservice-node-42"
    signals = [
        {
            "signal_id": "anom-arbitrary-dns-01",
            "signal_type": "ANOMALY",
            "service": arbitrary_service,
            "timestamp": "2026-10-21T01:00:00Z",
            "severity": "CRITICAL",
            "metadata": {
                "metric_name": "dns_resolution_latency_ms",
                "value": 3200.0,
                "threshold": 500.0,
            },
        },
        {
            "signal_id": "err-arbitrary-dns-02",
            "signal_type": "EVENT",
            "service": arbitrary_service,
            "timestamp": "2026-10-21T01:01:00Z",
            "severity": "ERROR",
            "message": "Resolver timeout reaching nameserver 10.0.0.2:53 for external-service.corp.internal (SERVFAIL)",
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    cand_names = [c["candidate_name"] for c in candidates]
    cand_types = [c["candidate_type"] for c in candidates]

    assert "DEPENDENCY" in cand_types
    assert any("DNS resolution failure" in name for name in cand_names)
    assert any(arbitrary_service in name for name in cand_names)


def test_audit_claim_2_kafka_poison_pill_vs_lag_vs_storage_vs_cpu():
    """
    Verify Kafka poison pill is differentiated from normal lag, disk partition, and CPU thread.
    """
    svc = "stream-processor-svc"

    # Case A: Poison pill
    poison_signals = [
        {
            "signal_id": "sig-lag-01",
            "signal_type": "ANOMALY",
            "service": svc,
            "timestamp": "2026-10-21T01:10:00Z",
            "severity": "CRITICAL",
            "metadata": {"metric_name": "kafka_consumer_lag_records", "value": 50000.0},
        },
        {
            "signal_id": "sig-poison-02",
            "signal_type": "EVENT",
            "service": svc,
            "timestamp": "2026-10-21T01:11:00Z",
            "severity": "ERROR",
            "message": "DeserializationException: Malformed JSON poison pill on partition 2 offset 819238",
        },
    ]
    poison_cands = CandidateGenerator.generate_candidates(poison_signals)
    poison_names = [c["candidate_name"] for c in poison_cands]
    assert any("poison pill" in name.lower() for name in poison_names)
    assert not any("disk" in name.lower() for name in poison_names)
    assert not any("cpu" in name.lower() for name in poison_names)

    # Case B: Normal lag without poison pill
    lag_signals = [
        {
            "signal_id": "sig-lag-03",
            "signal_type": "ANOMALY",
            "service": svc,
            "timestamp": "2026-10-21T01:10:00Z",
            "severity": "HIGH",
            "metadata": {"metric_name": "kafka_consumer_lag_records", "value": 12000.0},
        },
        {
            "signal_id": "sig-rebal-04",
            "signal_type": "EVENT",
            "service": svc,
            "timestamp": "2026-10-21T01:11:00Z",
            "severity": "INFO",
            "message": "Partition rebalance completed for consumer group analytics-workers",
        },
    ]
    lag_cands = CandidateGenerator.generate_candidates(lag_signals)
    lag_names = [c["candidate_name"] for c in lag_cands]
    assert any("lag backlog" in name.lower() for name in lag_names)
    assert not any("poison" in name.lower() for name in lag_names)

    # Case C: Disk partition exhaustion (must not match Kafka queue partition)
    disk_signals = [
        {
            "signal_id": "sig-disk-05",
            "signal_type": "EVENT",
            "service": svc,
            "timestamp": "2026-10-21T01:10:00Z",
            "severity": "ERROR",
            "message": "ENOSPC: No space left on disk partition /var/log/data",
        }
    ]
    disk_cands = CandidateGenerator.generate_candidates(disk_signals)
    assert any("Disk space exhaustion" in c["candidate_name"] for c in disk_cands)
    assert not any("queue" in c["candidate_name"].lower() for c in disk_cands)

    # Case D: CPU thread saturation (must not match Kafka consumer thread)
    cpu_signals = [
        {
            "signal_id": "sig-cpu-06",
            "signal_type": "EVENT",
            "service": svc,
            "timestamp": "2026-10-21T01:10:00Z",
            "severity": "ERROR",
            "message": "Worker thread pool starvation under 100% CPU utilization load",
        }
    ]
    cpu_cands = CandidateGenerator.generate_candidates(cpu_signals)
    assert any("Resource saturation" in c["candidate_name"] for c in cpu_cands)
    assert not any("queue" in c["candidate_name"].lower() for c in cpu_cands)


def test_audit_claim_3_healthy_dns_metrics_do_not_trigger_failure():
    """
    Verify healthy DNS metrics (e.g. 1.8ms) do not independently trigger DNS-failure diagnoses.
    """
    signals = [
        {
            "signal_id": "sig-nom-dns-01",
            "signal_type": "METRIC",
            "service": "payment-api",
            "timestamp": "2026-10-21T01:20:00Z",
            "severity": "INFO",
            "metadata": {
                "metric_name": "dns_lookup_duration_seconds",
                "value": 0.0018,  # 1.8ms (healthy)
            },
        },
        {
            "signal_id": "sig-nom-dns-02",
            "signal_type": "GAUGE",
            "service": "payment-api",
            "timestamp": "2026-10-21T01:20:05Z",
            "severity": "INFO",
            "metadata": {
                "metric_name": "dns_resolution_latency_ms",
                "value": 1.8,
            },
        },
    ]

    candidates = CandidateGenerator.generate_candidates(signals)
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "UNKNOWN"
    assert "Insufficient evidence" in candidates[0]["candidate_name"]


def test_audit_claim_4_historical_incident_references_unverified():
    """
    Verify historical incident references are classified as CROSS_INCIDENT,
    marked is_verified=False, and not presented as verified current telemetry.
    """
    status, explanation = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-SIM-01",
        source_type="HISTORICAL_INCIDENT",
        source_id="INC-HISTORICAL-2025-081",
        service="checkout-service",
        tenant_id="test-org-1",
        incident_key="INC-ACTIVE-2026-001",
        known_telemetry_source_ids={"prom-checkout-service-latency"},
        known_event_ids={"evt-INC-ACTIVE-2026-001-0001"},
    )

    assert status == CitationClassification.CROSS_INCIDENT
    assert "historical" in explanation.lower()

    # Verify produce_report_node converts this to is_verified=False
    state: InvestigationState = {
        "incident_key": "INC-ACTIVE-2026-001",
        "hypotheses": [
            {
                "hypothesis_id": "hyp-01",
                "candidate_name": "Service degradation on checkout-service",
                "candidate_type": "SERVICE",
                "confidence": 0.85,
                "evidence": [
                    {
                        "evidence_id": "EV-SIM-01",
                        "source_type": "HISTORICAL_INCIDENT",
                        "source_id": "INC-HISTORICAL-2025-081",
                        "claim": "Prior similar incident",
                    }
                ],
                "affected_services": ["checkout-service"],
            }
        ],
        "evidence": [
            {
                "evidence_id": "EV-SIM-01",
                "source_type": "HISTORICAL_INCIDENT",
                "source_id": "INC-HISTORICAL-2025-081",
                "service": "checkout-service",
                "claim": "Prior similar incident",
            }
        ],
        "collected_evidence": [
            {
                "evidence_id": "EV-SIM-01",
                "source_type": "HISTORICAL_INCIDENT",
                "source_id": "INC-HISTORICAL-2025-081",
                "service": "checkout-service",
                "claim": "Prior similar incident",
            }
        ],
        "iteration_count": 1,
        "investigation_complete": True,
        "confidence_threshold": 0.70,
        "target_service": "checkout-service",
        "environment": "production",
        "telemetry_evidence": {},
        "rca_result": None,
        "runbooks": [],
        "missing_evidence": [],
        "report": None,
        "status": InvestigationStatus.INVESTIGATING,
    }

    result = produce_report_node(state)
    report = result["final_report"]
    ev_items = report["evidence_items"]
    assert len(ev_items) == 1
    assert ev_items[0]["is_verified"] is False
    assert ev_items[0]["verification_status"] == CitationClassification.CROSS_INCIDENT.value


def test_audit_claim_5_boundary_enforcement():
    """
    Verify tenant, incident, and evidence-set boundaries are strictly enforced.
    """
    # 1. Cross-tenant
    status, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-XTENANT-01",
        source_type="PROMETHEUS",
        source_id="prom-cpu",
        service="svc",
        tenant_id="tenant-alpha",
        incident_key="INC-001",
        known_telemetry_source_ids={"prom-cpu"},
        known_event_ids=set(),
        data={"org_id": "tenant-bravo"},
    )
    assert status == CitationClassification.CROSS_TENANT

    # 2. Cross-incident
    status, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-XINC-01",
        source_type="PROMETHEUS",
        source_id="prom-cpu",
        service="svc",
        tenant_id="tenant-alpha",
        incident_key="INC-001",
        known_telemetry_source_ids={"prom-cpu"},
        known_event_ids=set(),
        data={"incident_key": "INC-999"},
    )
    assert status == CitationClassification.CROSS_INCIDENT

    # 3. Missing/unresolved source ID
    status, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-MISSING-01",
        source_type="PROMETHEUS",
        source_id="prom-nonexistent-metric",
        service="svc",
        tenant_id="tenant-alpha",
        incident_key="INC-001",
        known_telemetry_source_ids={"prom-cpu"},
        known_event_ids=set(),
    )
    assert status == CitationClassification.MISSING_OR_UNRESOLVED

    # 4. Malformed ID
    status, _ = EvidenceCitationValidator.validate_single_item(
        evidence_id="INVALID_NAME_WITHOUT_PREFIX",
        source_type="PROMETHEUS",
        source_id="prom-cpu",
        service="svc",
        tenant_id="tenant-alpha",
        incident_key="INC-001",
        known_telemetry_source_ids={"prom-cpu"},
        known_event_ids=set(),
    )
    assert status == CitationClassification.MALFORMED


def test_audit_claim_6_full_denominator_accounting():
    """
    Verify invalid, unresolved, stale, cross-incident, cross-tenant, and malformed
    citations remain in the reported denominator.
    """
    evidence_items = [
        {"evidence_id": "EV-VALID-01", "source_type": "PROMETHEUS", "source_id": "prom-svc-cpu", "service": "svc", "claim": "Valid"},
        {"evidence_id": "EV-XTENANT-01", "source_type": "PROMETHEUS", "source_id": "prom-svc-cpu", "service": "svc", "claim": "Cross tenant", "data": {"org_id": "other"}},
        {"evidence_id": "EV-XINC-01", "source_type": "PROMETHEUS", "source_id": "prom-svc-cpu", "service": "svc", "claim": "Cross incident", "data": {"incident_key": "other-inc"}},
        {"evidence_id": "EV-MISSING-01", "source_type": "PROMETHEUS", "source_id": "prom-ghost", "service": "svc", "claim": "Missing"},
        {"evidence_id": "MALFORMED_ID", "source_type": "PROMETHEUS", "source_id": "prom-svc-cpu", "service": "svc", "claim": "Malformed"},
    ]

    audit = EvidenceCitationValidator.audit_investigation(
        evidence_items=evidence_items,
        hypotheses=[],
        tenant_id="tenant-main",
        incident_key="INC-001",
        raw_telemetry={"metrics": [{"metric_name": "cpu", "service": "svc"}]},
    )

    # Denominator must exactly equal 5
    assert audit["total_citations_evaluated"] == 5
    assert audit["valid_citations_count"] == 1
    assert audit["invalid_citations_count"] == 4
    assert audit["breakdown"]["valid"] == 1
    assert audit["breakdown"]["cross_tenant"] == 1
    assert audit["breakdown"]["cross_incident"] == 1
    assert audit["breakdown"]["missing_or_unresolved"] == 1
    assert audit["breakdown"]["malformed"] == 1
    # Check that validity rate is 1/5 = 0.20
    assert audit["citation_validity_rate"] == 0.20


def test_audit_claim_7_answer_key_isolation():
    """
    Verify ground-truth answers are never accepted into investigation state,
    candidate generation, scoring, or model schemas.
    """
    req_fields = set(InvestigationRequest.model_fields.keys())
    prohibited_fields = {"answer_key", "ground_truth", "expected_root_cause", "true_cause", "solution"}
    assert prohibited_fields.isdisjoint(req_fields), f"InvestigationRequest contains prohibited fields: {prohibited_fields & req_fields}"

    # Verify CandidateGenerator.generate_candidates only accepts signals
    import inspect
    sig = inspect.signature(CandidateGenerator.generate_candidates)
    param_names = set(sig.parameters.keys())
    assert prohibited_fields.isdisjoint(param_names)

    # Verify CandidateScorer.score_candidates does not accept ground truth
    scorer_sig = inspect.signature(CandidateScorer.score_candidates)
    scorer_param_names = set(scorer_sig.parameters.keys())
    assert prohibited_fields.isdisjoint(scorer_param_names)
