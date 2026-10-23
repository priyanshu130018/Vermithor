from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.agent.schemas.investigation import (
    DiagnosticStep,
    HypothesisEvaluation,
    InvestigationEvidenceItem,
    InvestigationReport,
    InvestigationStatus,
)

logger = logging.getLogger(__name__)


def produce_report_node(state: InvestigationState, db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Step 9: Compile the structured, evidence-backed final investigation report.
    Validates evidence grounding, distinguishes fact from inference, and establishes final status.
    """
    inv_id = state.get("investigation_id") or f"INV-{state.get('incident_key', 'UNKNOWN')}"
    incident_key = state.get("incident_key", "UNKNOWN")
    title = state.get("incident_title", f"Incident {incident_key}")
    target_svc = state.get("target_service", "unknown")
    environment = state.get("environment", "production")
    time_window = {
        "start": state.get("window_start", ""),
        "end": state.get("window_end", ""),
        "lookback_minutes": state.get("lookback_minutes", 30),
    }

    leading_cause = state.get("primary_root_cause") or "Insufficient evidence"
    conf = float(state.get("primary_confidence", 0.0))
    is_fallback = bool(state.get("is_fallback", False))
    provider = state.get("llm_provider", "unknown")
    model = state.get("llm_model")
    if is_fallback:
        provider = "fallback"
        model = "deterministic-rules (non-LLM)"

    from backend.app.observability.security.safe_client import redact_sensitive_text, redact_sensitive_data
    from backend.app.agent.services.citation_validator import EvidenceCitationValidator, CitationClassification

    # Format evidence items into typed schemas with sensitive credential and PII redaction and strict citation validation
    raw_evidence = state.get("collected_evidence", [])
    tenant_id = state.get("org_id", "default_org")
    known_src_ids = {str(e.get("source_id", "")).strip() for e in raw_evidence if e.get("source_id")}
    evidence_items: List[InvestigationEvidenceItem] = []

    for ev in raw_evidence:
        ev_id = ev.get("evidence_id", "EV-UNKNOWN")
        stype = ev.get("source_type", "UNKNOWN")
        sid = str(ev.get("source_id", ""))
        svc = ev.get("service") or target_svc

        classification, _ = EvidenceCitationValidator.validate_single_item(
            evidence_id=ev_id,
            source_type=stype,
            source_id=sid,
            service=svc,
            tenant_id=tenant_id,
            incident_key=incident_key,
            known_telemetry_source_ids=known_src_ids,
            known_event_ids=set(),
            data=ev.get("data") or {},
        )
        is_verified = (classification == CitationClassification.VALID)

        evidence_items.append(
            InvestigationEvidenceItem(
                evidence_id=ev_id,
                source_type=stype,
                source_id=sid,
                service=svc,
                timestamp=ev.get("timestamp"),
                claim=redact_sensitive_text(ev.get("claim", "")),
                data=redact_sensitive_data(ev.get("data", {})),
                is_verified=is_verified,
                verification_status=classification.value,
            )
        )

    # Format hypotheses into typed schemas with sensitive credential and PII redaction
    raw_hypotheses = state.get("hypotheses_evaluated", [])
    hypotheses: List[HypothesisEvaluation] = []
    for h in raw_hypotheses:
        hypotheses.append(
            HypothesisEvaluation(
                hypothesis=redact_sensitive_text(h.get("hypothesis", "Unknown")),
                candidate_type=h.get("candidate_type", "UNKNOWN"),
                original_score=float(h.get("original_score", 0.0)),
                calibrated_status=h.get("calibrated_status", "INCONCLUSIVE"),
                supporting_evidence_ids=h.get("supporting_evidence_ids", []),
                contradicting_evidence_ids=h.get("contradicting_evidence_ids", []),
                reasoning=redact_sensitive_text(h.get("reasoning", "")),
            )
        )

    # Format diagnostic steps (strictly requiring human approval)
    raw_steps = state.get("recommended_diagnostic_steps", [])
    diag_steps: List[DiagnosticStep] = []
    for step in raw_steps:
        diag_steps.append(
            DiagnosticStep(
                action=step.get("action", "Inspect component metrics"),
                target_service=step.get("target_service") or target_svc,
                rationale=step.get("rationale", "Diagnostic triage"),
                priority=step.get("priority", "MEDIUM"),
                requires_human_approval=True,
            )
        )

    # Determine final investigation status
    telemetry_signals = [e for e in raw_evidence if e.get("source_type") not in ("CORRELATION", "RCA")]
    is_uncertain_cause = any(
        k in leading_cause.lower()
        for k in ("insufficient", "inconclusive", "unknown", "transient", "ambiguous")
    )
    if conf < 0.45 or is_uncertain_cause or len(telemetry_signals) == 0:
        final_status = InvestigationStatus.INSUFFICIENT_EVIDENCE
    else:
        final_status = InvestigationStatus.COMPLETED

    report = InvestigationReport(
        investigation_id=inv_id,
        incident_key=incident_key,
        title=title,
        target_service=target_svc,
        environment=environment,
        time_window=time_window,
        observed_facts=state.get("observed_facts", []),
        inferred_relationships=state.get("inferred_relationships", []),
        leading_hypothesis=leading_cause,
        hypothesis_confidence=conf,
        hypotheses_evaluated=hypotheses,
        alternative_explanations=state.get("alternative_explanations", []),
        confirmed_findings=state.get("confirmed_findings", []),
        missing_evidence=state.get("missing_evidence", []),
        contradictory_evidence=state.get("contradictory_evidence", []),
        uncertainty_assessment=state.get("uncertainty_assessment", ""),
        recommended_diagnostic_steps=diag_steps,
        runbook_references=state.get("runbooks", []),
        evidence_items=evidence_items,
        model_provider=provider,
        model_name=model,
        is_fallback=is_fallback,
        model_call_records=state.get("model_call_records", []),
        review_assessment=state.get("review_assessment"),
    )

    logger.info(
        "Final investigation report compiled for %s: status=%s, leading='%s', conf=%.2f, fallback=%s",
        incident_key,
        final_status.value,
        leading_cause,
        conf,
        is_fallback,
    )

    return {
        "final_report": report.model_dump(mode="json"),
        "status": final_status.value,
        "leading_hypothesis": leading_cause,
        "primary_confidence": conf,
        "is_fallback": is_fallback,
        "llm_provider": provider,
        "llm_model": model,
        "model_call_records": state.get("model_call_records", []),
    }
