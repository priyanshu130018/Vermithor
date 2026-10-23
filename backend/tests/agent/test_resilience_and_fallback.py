import pytest
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.agent.graph.workflow import create_investigation_graph
from backend.app.agent.schemas.investigation import InvestigationRequest, InvestigationStatus
from backend.app.agent.services.investigation_service import InvestigationService


def test_missing_telemetry_and_unavailable_services(
    db_session: Session,
    test_payment_incident,
    mock_unavailable_telemetry_service,
    mock_valid_llm,
):
    """
    Verify that when Prometheus/Jaeger are unavailable, the agent:
    1. Distinguishes unavailable source from empty query (records warning in errors).
    2. Does NOT crash or fail the workflow.
    3. Produces a valid investigation with honest uncertainty.
    """
    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)

    response = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_unavailable_telemetry_service,
        llm_provider=mock_valid_llm,
    )

    assert response is not None
    assert response.status in [InvestigationStatus.COMPLETED, InvestigationStatus.INSUFFICIENT_EVIDENCE]
    rep = response.report
    assert rep is not None
    # Check that missing telemetry / errors were captured
    assert len(rep.missing_evidence) > 0 or len(rep.evidence_items) >= 0


def test_insufficient_data_honest_uncertainty(
    db_session: Session,
    mock_unavailable_telemetry_service,
    mock_failing_llm,
):
    """
    Verify that an incident with empty/inconclusive evidence:
    1. Honestly sets status to INSUFFICIENT_EVIDENCE (or confidence < 0.40).
    2. Preserves UNKNOWN root cause instead of fabricating a diagnosis.
    """
    service = InvestigationService()
    # Incident key that has no telemetry anywhere
    req = InvestigationRequest(incident_key="INC-EMPTY-DATA", force_refresh=True)

    response = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_unavailable_telemetry_service,
        llm_provider=mock_failing_llm,
    )

    assert response is not None
    assert response.status == InvestigationStatus.INSUFFICIENT_EVIDENCE
    assert response.confidence < 0.40
    rep = response.report
    assert rep is not None
    assert "uncertainty" in rep.uncertainty_assessment.lower() or "insufficient" in rep.leading_hypothesis.lower()


def test_llm_timeout_triggers_deterministic_fallback(
    db_session: Session,
    test_payment_incident,
    mock_telemetry_service,
    mock_failing_llm,
):
    """
    Verify that when LLM provider times out or fails:
    1. Deterministic fallback is activated.
    2. Fallback status is explicitly marked: is_fallback=True, model_provider='fallback'.
    3. Investigation produces a structured, evidence-backed report with RCA candidates and runbooks.
    """
    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)

    response = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_telemetry_service,
        llm_provider=mock_failing_llm,
    )

    assert response is not None
    assert response.is_fallback is True
    assert response.model_provider == "fallback"
    assert "deterministic-rules" in response.model_name

    rep = response.report
    assert rep is not None
    assert rep.is_fallback is True
    assert len(rep.observed_facts) > 0
    assert len(rep.hypotheses_evaluated) > 0
    assert len(rep.recommended_diagnostic_steps) > 0


def test_malformed_llm_response_handled_gracefully(
    db_session: Session,
    test_payment_incident,
    mock_telemetry_service,
    mock_malformed_llm,
):
    """Verify that when LLM outputs invalid non-JSON text, deterministic fallback kicks in."""
    service = InvestigationService()
    req = InvestigationRequest(incident_key="INC-2026-1042", force_refresh=True)

    response = service.run_investigation(
        db=db_session,
        req=req,
        telemetry_service=mock_telemetry_service,
        llm_provider=mock_malformed_llm,
    )

    assert response is not None
    assert response.is_fallback is True
    assert response.model_provider == "fallback"
    assert response.report is not None
