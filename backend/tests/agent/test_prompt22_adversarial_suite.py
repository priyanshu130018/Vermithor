"""
Prompt 22 Adversarial Robustness Test Suite.

Tests 9 critical edge/adversarial scenarios beyond frozen benchmark holdouts:
1. Fabricated evidence identifiers (Trace IDs, Metric IDs, Topology nodes).
2. Correct evidence from the wrong incident (Cross-incident boundary).
3. Historical evidence misrepresented as current direct telemetry.
4. Stale evidence (expired or outside observation window).
5. Missing deployment timestamps (graceful degradation without scoring crash).
6. OOM symptoms without memory exhaustion (discriminating nominal vs OOM).
7. Deployment immediately preceding an unrelated DNS outage (proper causal ranking).
8. Unauthorized, missing, or malformed organization identifiers (multi-tenant boundary).
9. Contradictory evidence requiring safe abstention.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.db.models import Investigation, Repair
from backend.app.agent.schemas.investigation import InvestigationStatus
from backend.app.agent.schemas.repair import RepairStatus, ValidationStatus, ApprovalStatus
from backend.app.agent.services.citation_validator import (
    CitationClassification,
    EvidenceCitationValidator,
)
from backend.app.common.security import create_access_token
from backend.app.main import app
from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.scoring import CandidateScorer
from backend.app.rca.evidence.deployment_evaluator import DeploymentEvidenceEvaluator


def test_adversarial_1_fabricated_evidence_identifiers():
    """Verify that fabricated trace IDs, metric names, and topology nodes cannot be validated through prefix matching."""
    known_telemetry = {"prom-cart-service-cpu_usage", "trace-cart-service-0001"}
    known_events = {"evt-INC-100-0001"}

    # Fabricated trace ID with 'trace-' prefix
    st, exp = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-TRACE-FABRICATED",
        source_type="JAEGER",
        source_id="trace-fabricated-fake-9999",
        service="cart-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
    )
    assert st == CitationClassification.MISSING_OR_UNRESOLVED
    assert "could not be resolved" in exp.lower()

    # Fabricated metric ID with 'prom-' prefix
    st_m, exp_m = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-PROM-FABRICATED",
        source_type="PROMETHEUS",
        source_id="prom-cart-service-nonexistent_metric",
        service="cart-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
    )
    assert st_m == CitationClassification.MISSING_OR_UNRESOLVED

    # Fabricated topology dependency
    st_t, exp_t = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-TOPO-FABRICATED",
        source_type="TOPOLOGY",
        source_id="topo-dep-fabricated-ghost-service",
        service="cart-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids=known_telemetry,
        known_event_ids=known_events,
    )
    assert st_t == CitationClassification.MISSING_OR_UNRESOLVED


def test_adversarial_2_correct_evidence_from_wrong_incident():
    """Verify that valid evidence from incident B is rejected when cited in incident A."""
    st, exp = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-VALID-IN-OTHER-INCIDENT",
        source_type="PROMETHEUS",
        source_id="prom-payment-latency",
        service="payment-service",
        tenant_id="vermithor",
        incident_key="INC-ACTIVE-CURRENT",
        known_telemetry_source_ids={"prom-payment-latency"},
        known_event_ids=set(),
        data={"incident_key": "INC-COMPLETED-PREVIOUS"},
    )
    assert st == CitationClassification.CROSS_INCIDENT
    assert "does not match active incident" in exp


def test_adversarial_3_historical_evidence_misrepresented_as_telemetry():
    """Verify that historical incident IDs or flagged historical items cannot be disguised as current telemetry."""
    # Misrepresented via source_id
    st1, exp1 = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-HIST-MISREP-1",
        source_type="PROMETHEUS",
        source_id="INC-HISTORICAL-2024-884",
        service="billing-api",
        tenant_id="vermithor",
        incident_key="INC-2026-001",
        known_telemetry_source_ids={"INC-HISTORICAL-2024-884"},
        known_event_ids=set(),
    )
    assert st1 == CitationClassification.CROSS_INCIDENT

    # Misrepresented via metadata flag
    st2, exp2 = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-HIST-MISREP-2",
        source_type="EVENT",
        source_id="evt-INC-2026-001-0001",
        service="billing-api",
        tenant_id="vermithor",
        incident_key="INC-2026-001",
        known_telemetry_source_ids=set(),
        known_event_ids={"evt-INC-2026-001-0001"},
        data={"is_historical": True},
    )
    assert st2 == CitationClassification.CROSS_INCIDENT


def test_adversarial_4_stale_evidence():
    """Verify that stale evidence is classified as STALE."""
    st, exp = EvidenceCitationValidator.validate_single_item(
        evidence_id="EV-STALE-01",
        source_type="PROMETHEUS",
        source_id="prom-cart-service-cpu_usage",
        service="cart-service",
        tenant_id="vermithor",
        incident_key="INC-100",
        known_telemetry_source_ids={"prom-cart-service-cpu_usage"},
        known_event_ids=set(),
        data={"is_stale": True},
    )
    assert st == CitationClassification.STALE
    assert "expired" in exp.lower() or "outside" in exp.lower()


def test_adversarial_5_missing_deployment_timestamps():
    """Verify that deployments with missing/null timestamps evaluate safely without crashing CandidateScorer."""
    evaluator = DeploymentEvidenceEvaluator()

    # Signals with missing deployment timestamp
    signals = [
        {
            "signal_id": "dep-null-time-01",
            "signal_type": "DEPLOYMENT",
            "service": "auth-service",
            "message": "Deploying release v2.4.0 (commit abcd123)",
            "timestamp": None,
            "metadata": {"environment": "production"},
        },
        {
            "signal_id": "anom-auth-latency",
            "signal_type": "ANOMALY",
            "service": "auth-service",
            "message": "Authentication latency degraded",
            "timestamp": "2026-10-21T05:00:00Z",
            "metadata": {"metric_name": "auth_latency_ms", "value": 1200.0},
        },
    ]

    results = evaluator.evaluate(signals=signals, candidate_service="auth-service")
    assert len(results) == 1
    assert results[0].timestamp is None
    assert results[0].score == 0.20
    assert "missing" in results[0].description.lower()

    # Verify CandidateScorer also handles null deployment timestamp without crashing
    generator = CandidateGenerator()
    scorer = CandidateScorer()
    candidates = generator.generate_candidates(signals)
    scored = scorer.score_candidates(candidates=candidates, signals=signals, edges=[])
    assert len(scored) > 0


def test_adversarial_6_oom_symptoms_without_memory_exhaustion():
    """Verify that service restarts without memory limit saturation do not diagnose OOM."""
    generator = CandidateGenerator()

    # Signals showing high error rate and restart, but memory usage is only 20%
    signals = [
        {
            "signal_id": "anom-err-rate",
            "signal_type": "ANOMALY",
            "service": "worker-pool",
            "timestamp": "2026-10-21T05:00:00Z",
            "severity": "CRITICAL",
            "metadata": {"metric_name": "http_5xx_rate", "value": 0.85},
        },
        {
            "signal_id": "evt-restart",
            "signal_type": "EVENT",
            "service": "worker-pool",
            "timestamp": "2026-10-21T05:01:00Z",
            "severity": "WARN",
            "message": "Worker pod restarted due to unhandled NullPointerException in job parser",
        },
        {
            "signal_id": "obs-mem",
            "signal_type": "METRIC_OBSERVATION",
            "service": "worker-pool",
            "timestamp": "2026-10-21T05:00:00Z",
            "metadata": {"metric_name": "container_memory_usage_bytes", "value": 214748364.0}, # ~200MB out of 4GB
        },
    ]

    candidates = generator.generate_candidates(signals)
    cand_names = [c["candidate_name"].lower() if isinstance(c, dict) else c.name.lower() for c in candidates]

    # Must NOT generate OOM candidate
    assert not any("memory exhaustion" in c or "oom" in c for c in cand_names), (
        f"Unexpected OOM candidate generated from non-memory crash: {cand_names}"
    )


def test_adversarial_7_deployment_preceding_unrelated_dns_outage():
    """Verify that a routine deployment preceding an explicit DNS resolution outage does not override DNS root cause."""
    generator = CandidateGenerator()
    scorer = CandidateScorer()

    signals = [
        {
            "signal_id": "evt-deploy-routine",
            "signal_type": "DEPLOYMENT",
            "service": "api-gateway",
            "timestamp": "2026-10-21T04:00:00Z", # 1 hour earlier
            "severity": "INFO",
            "message": "Routine deployment of static asset bundle v1.0.12",
        },
        {
            "signal_id": "anom-dns",
            "signal_type": "ANOMALY",
            "service": "api-gateway",
            "timestamp": "2026-10-21T05:00:00Z",
            "severity": "CRITICAL",
            "metadata": {"metric_name": "dns_lookup_failures_total", "value": 520.0},
        },
        {
            "signal_id": "evt-dns-err",
            "signal_type": "EVENT",
            "service": "api-gateway",
            "timestamp": "2026-10-21T05:00:30Z",
            "severity": "CRITICAL",
            "message": "CoreDNS SERVFAIL on resolving auth.internal.domain: connection refused to 10.96.0.10:53",
        },
    ]

    candidates = generator.generate_candidates(signals)
    ranked = scorer.score_candidates(
        candidates=candidates,
        signals=signals,
        edges=[],
    )

    leading = ranked[0]["candidate_name"].lower() if isinstance(ranked[0], dict) else ranked[0].name.lower()
    assert "dns" in leading, f"Expected DNS root cause to lead, but got: {leading}"


def test_adversarial_8_organization_authorization_boundaries(client: TestClient, db_session):
    """
    Verify fail-closed multi-tenant boundary enforcement:
    1. Missing org claim in JWT fails closed with 403.
    2. Malformed org claim (injection/traversal) fails closed with 403.
    3. Unauthorized org claim fails closed with 403.
    4. Cross-tenant repair approval fails closed with 403.
    5. Cross-tenant feedback fails closed with 404/403.
    """
    # 1. Missing org claim
    token_no_org = create_access_token({"sub": "anonymous-attacker"})
    resp_no_org = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-ADV-01"},
        headers={"Authorization": f"Bearer {token_no_org}"},
    )
    assert resp_no_org.status_code == 403
    assert "missing" in resp_no_org.json()["detail"].lower()

    # 2. Malformed org claim
    token_malformed = create_access_token({"sub": "path-traverser", "org_id": "../../../etc/passwd"})
    resp_mal = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-ADV-01"},
        headers={"Authorization": f"Bearer {token_malformed}"},
    )
    assert resp_mal.status_code == 403
    assert "malformed" in resp_mal.json()["detail"].lower()

    # 3. Unauthorized org claim
    token_unauth = create_access_token({"sub": "rogue-tenant", "org_id": "unauthorized-external-corp"})
    resp_unauth = client.post(
        "/api/v1/agent/investigations",
        json={"incident_key": "INC-ADV-01"},
        headers={"Authorization": f"Bearer {token_unauth}"},
    )
    assert resp_unauth.status_code == 403
    assert "not authorized" in resp_unauth.json()["detail"].lower()

    # 4. Cross-tenant repair approval
    rep_tenant_a = Repair(
        repair_key="REP-TENANT-A-01",
        org_id="tenant_alpha",
        investigation_key="INV-TENANT-A",
        incident_key="INC-TENANT-A",
        status=RepairStatus.AWAITING_APPROVAL.value,
        validation_status=ValidationStatus.VALIDATED.value,
        requires_human_approval=True,
        approval_status=ApprovalStatus.PENDING.value,
    )
    db_session.add(rep_tenant_a)
    db_session.commit()

    token_tenant_b = create_access_token({
        "sub": "engineer_bravo",
        "org_id": "internal", # 'internal' is in allowed_orgs, but differs from tenant_alpha
        "role": "sre_lead",
    })
    resp_cross_approve = client.post(
        f"/api/v1/agent/repairs/{rep_tenant_a.repair_key}/approve",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    assert resp_cross_approve.status_code == 403
    assert "multi-tenant isolation violation" in resp_cross_approve.json()["detail"].lower()

    # 5. Cross-tenant feedback submission
    inv_tenant_a = Investigation(
        investigation_key="INV-TENANT-A-FEEDBACK",
        org_id="tenant_alpha",
        incident_key="INC-TENANT-A",
        status=InvestigationStatus.COMPLETED.value,
        target_service="billing-api",
        environment="production",
        leading_hypothesis="Database connection pool exhaustion",
        confidence=0.90,
    )
    db_session.add(inv_tenant_a)
    db_session.commit()

    resp_cross_feedback = client.post(
        f"/api/v1/agent/investigations/{inv_tenant_a.investigation_key}/feedback",
        json={"feedback_status": "CONFIRMED"},
        headers={"Authorization": f"Bearer {token_tenant_b}"},
    )
    # Must fail because investigation does not belong to tenant B
    assert resp_cross_feedback.status_code in (403, 404)


def test_adversarial_9_contradictory_evidence_requires_abstention():
    """Verify that conflicting low-signal evidence abstains or produces low-confidence service degradation."""
    generator = CandidateGenerator()
    scorer = CandidateScorer()

    signals = [
        {
            "signal_id": "noise-1",
            "signal_type": "METRIC_OBSERVATION",
            "service": "data-pipeline",
            "timestamp": "2026-10-21T06:00:00Z",
            "metadata": {"metric_name": "cpu_usage", "value": 15.0},
        },
        {
            "signal_id": "noise-2",
            "signal_type": "METRIC_OBSERVATION",
            "service": "data-pipeline",
            "timestamp": "2026-10-21T06:01:00Z",
            "metadata": {"metric_name": "memory_usage", "value": 20.0},
        },
    ]

    candidates = generator.generate_candidates(signals)
    ranked = scorer.score_candidates(candidates=candidates, signals=signals, edges=[])
    assert len(ranked) >= 1
    # Confidence must remain conservative/low
    top_score = ranked[0]["score"] if isinstance(ranked[0], dict) else ranked[0].score
    assert top_score <= 0.60
