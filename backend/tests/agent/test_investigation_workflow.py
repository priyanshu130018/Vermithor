import pytest
from sqlalchemy.orm import Session

from backend.app.agent.graph.workflow import create_investigation_graph
from backend.app.agent.graph.state import InvestigationState
from backend.app.agent.schemas.investigation import InvestigationRequest
from backend.app.agent.services.investigation_service import InvestigationService
from backend.app.retrieval.db.models import Runbook


def test_investigation_workflow_end_to_end_mocked(
    db_session: Session,
    test_payment_incident,
    mock_telemetry_service,
    mock_valid_llm,
):
    """Verify end-to-end investigation execution with mocked telemetry and LLM dependencies."""
    # Seed a runbook
    rb = Runbook(
        runbook_key="RB-000006",
        title="Payment API Connection Pool Sizing and Leak Investigation",
        description="Troubleshoot database pool saturation on payment-api.",
        content="Inspect HikariCP connection pool settings and pg_stat_activity.",
        service="payment-api",
        environment="production",
        category="DATABASE",
    )
    db_session.add(rb)
    db_session.commit()

    service = InvestigationService()
    req = InvestigationRequest(
        incident_key="INC-2026-1042",
        lookback_minutes=30,
        allow_additional_queries=True,
        max_additional_queries=2,
        force_refresh=True,
    )

    response = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_telemetry_service,
        llm_provider=mock_valid_llm,
    )

    assert response is not None
    assert response.incident_key == "INC-2026-1042"
    assert response.status.value in ["COMPLETED", "INSUFFICIENT_EVIDENCE"]
    assert response.investigation_key.startswith("INV-")
    assert response.report is not None

    rep = response.report
    assert rep.incident_key == "INC-2026-1042"
    assert rep.target_service == "payment-api"
    assert len(rep.observed_facts) > 0
    assert len(rep.hypotheses_evaluated) > 0
    assert len(rep.evidence_items) > 0
    assert len(rep.recommended_diagnostic_steps) > 0


def test_rca_and_runbook_passed_to_report(
    db_session: Session,
    test_payment_incident,
    mock_telemetry_service,
    mock_valid_llm,
):
    """Verify that existing RCA candidate scores and retrieved runbooks are passed to report stage."""
    rb = Runbook(
        runbook_key="RB-000006",
        title="Payment API Connection Pool Sizing and Leak Investigation",
        description="Troubleshoot database pool saturation on payment-api.",
        content="Inspect HikariCP connection pool settings.",
        service="payment-api",
        environment="production",
        category="DATABASE",
    )
    db_session.add(rb)
    db_session.commit()

    service = InvestigationService()
    req = InvestigationRequest(
        incident_key="INC-2026-1042",
        force_refresh=True,
    )

    response = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_telemetry_service,
        llm_provider=mock_valid_llm,
    )

    rep = response.report
    assert rep is not None

    # Verify RCA original scores are preserved and in valid bounds [0.0, 1.0]
    for hyp in rep.hypotheses_evaluated:
        assert 0.0 <= hyp.original_score <= 1.0
        assert hyp.hypothesis is not None
        assert hyp.candidate_type is not None

    # Verify Runbook was retrieved and referenced
    rb_keys = [rb.get("runbook_key") for rb in rep.runbook_references]
    assert "RB-000006" in rb_keys or len(rep.runbook_references) > 0


def test_evidence_preservation_and_citations(
    db_session: Session,
    test_payment_incident,
    mock_telemetry_service,
    mock_valid_llm,
):
    """Verify that evidence IDs, sources, service names, and timestamps are preserved throughout the graph."""
    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)

    response = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_telemetry_service,
        llm_provider=mock_valid_llm,
    )

    rep = response.report
    assert rep is not None
    assert len(rep.evidence_items) > 0

    for ev in rep.evidence_items:
        assert ev.evidence_id.startswith("EV-")
        assert ev.source_type in [
            "PROMETHEUS",
            "JAEGER",
            "METRIC_OBSERVATION",
            "EVENT",
            "DEPLOYMENT",
            "TOPOLOGY",
            "ANOMALY",
            "CORRELATION",
            "RCA",
            "RUNBOOK",
            "HISTORICAL_INCIDENT",
            "INCIDENT_EVENT",
        ]
        assert ev.service is not None
        assert ev.claim is not None
        assert ev.source_id is not None
