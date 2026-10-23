from datetime import datetime, timezone
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory

logger = logging.getLogger(__name__)


def _extract_citation_ids(text: str) -> List[str]:
    """Extract cited evidence identifiers (e.g. EV-METRIC-01, EV-001) from text."""
    if not text:
        return []
    return re.findall(r"\[([A-Za-z0-9_\-]+)\]", text)


def review_report_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    llm_provider: Optional[LLMProvider] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Step 10: Review and verify final investigation report against evidence catalog and safety boundaries.
    Routes to configured HF_REVIEW_MODEL (or fallback deterministic verification).
    Records provider, model ID, task='report_review', client-observed latency, and fallback status.
    """
    cfg = settings or get_settings()
    provider = llm_provider
    if provider is None:
        try:
            try:
                provider = ProviderFactory.get_provider(cfg, task="report_review")
            except TypeError:
                provider = ProviderFactory.get_provider(cfg)
        except Exception as exc:
            logger.warning("Could not initialize report review LLM provider: %s", exc)
            provider = None

    incident_key = state.get("incident_key", "UNKNOWN")
    final_report = dict(state.get("final_report") or {})
    raw_evidence = state.get("collected_evidence", [])
    valid_ev_ids: Set[str] = {
        str(e.get("evidence_id", "")).strip() for e in raw_evidence if e.get("evidence_id")
    }

    call_records = list(state.get("model_call_records", []))

    # 1. Deterministic Citation & Evidence Grounding Audit
    cited_ids: Set[str] = set()
    observed_facts = final_report.get("observed_facts", [])
    for fact in observed_facts:
        for cid in _extract_citation_ids(str(fact)):
            cited_ids.add(cid)

    hypotheses = final_report.get("hypotheses_evaluated", [])
    for h in hypotheses:
        if isinstance(h, dict):
            for sid in h.get("supporting_evidence_ids", []):
                cited_ids.add(str(sid).strip())

    total_citations = len(cited_ids)
    valid_citations = len([cid for cid in cited_ids if cid in valid_ev_ids])
    invalid_citations = [cid for cid in cited_ids if cid not in valid_ev_ids]
    citation_validity_rate = (valid_citations / total_citations) if total_citations > 0 else 1.0

    # 2. Unsupported Claim Detection
    unsupported_claims: List[str] = []
    for fact in observed_facts:
        cids = _extract_citation_ids(str(fact))
        if not cids:
            unsupported_claims.append(str(fact))
    unsupported_claim_rate = (
        len(unsupported_claims) / len(observed_facts) if observed_facts else 0.0
    )

    # 3. Operational Safety Boundary Check (strictly require human approval)
    diag_steps = final_report.get("recommended_diagnostic_steps", [])
    all_require_approval = all(
        isinstance(s, dict) and s.get("requires_human_approval", True) is True
        for s in diag_steps
    )

    # 4. Attempt Cloud LLM Review if authorized and available
    org_id = state.get("org_id") or "vermithor"
    allow_external_llm = state.get("allow_external_llm", False)
    pol_found = False
    if db is not None:
        try:
            from backend.app.agent.db.models import PilotGovernancePolicy
            pol = db.query(PilotGovernancePolicy).filter(PilotGovernancePolicy.org_id == org_id).first()
            if pol:
                allow_external_llm = pol.allow_external_llm
                pol_found = True
        except Exception:
            pass

    use_llm = provider is not None and provider.is_available()
    provider_name = (provider.get_provider_name() if provider else "").lower()
    is_mock_or_local = any(k in provider_name for k in ("mock", "local", "deterministic", "fallback"))
    if use_llm and pol_found and not allow_external_llm and not is_mock_or_local:
        logger.info("Pilot data governance: external LLM review blocked for org '%s'.", org_id)
        use_llm = False

    review_assessment: Dict[str, Any] = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "total_citations_checked": total_citations,
        "valid_citations_count": valid_citations,
        "citation_validity_rate": round(citation_validity_rate, 4),
        "invalid_citations": invalid_citations,
        "unsupported_claims_count": len(unsupported_claims),
        "unsupported_claim_rate": round(unsupported_claim_rate, 4),
        "safety_boundaries_enforced": all_require_approval,
        "review_passed": bool(citation_validity_rate >= 0.80 and all_require_approval),
        "review_model": "deterministic-rules (non-LLM)",
        "is_fallback": True,
    }

    if use_llm:
        try:
            prompt = (
                f"You are Vermithor's Incident Report Reviewer.\n"
                f"Review this investigation report for incident {incident_key}.\n"
                f"Evidence IDs available: {sorted(list(valid_ev_ids))[:20]}\n"
                f"Citations present in report: {sorted(list(cited_ids))}\n"
                f"Check for hallucinated citations, ungrounded claims, or missing human approval flags.\n"
                f"Respond in JSON: {{\"review_summary\": \"...\", \"passed\": true/false, \"confidence\": 0.95}}"
            )
            raw_review = ""
            call_rec: Optional[Dict[str, Any]] = None

            if hasattr(provider, "generate_with_telemetry"):
                raw_review, call_rec = provider.generate_with_telemetry(prompt, task="report_review")
            else:
                t0 = time.perf_counter()
                raw_review = provider.generate(prompt)
                lat = time.perf_counter() - t0
                call_rec = {
                    "provider": provider.get_provider_name(),
                    "actual_model_id": provider.get_model_name(),
                    "task": "report_review",
                    "request_latency_ms": round(lat * 1000.0, 2),
                    "request_latency_seconds": round(lat, 4),
                    "fallback_status": False,
                    "errors": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            if call_rec:
                call_records.append(call_rec)

            review_assessment["review_model"] = provider.get_model_name()
            review_assessment["is_fallback"] = False
            review_assessment["llm_critique"] = raw_review[:300]
            logger.info("Cloud LLM completed report review for %s", incident_key)
        except Exception as exc:
            logger.warning("Cloud LLM review failed (%s). Retaining deterministic review.", exc)
            fallback_rec = {
                "provider": "fallback",
                "actual_model_id": "deterministic-rules (non-LLM)",
                "task": "report_review",
                "request_latency_ms": 0.0,
                "request_latency_seconds": 0.0,
                "fallback_status": True,
                "errors": str(exc),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            call_records.append(fallback_rec)
    else:
        fallback_rec = {
            "provider": "fallback",
            "actual_model_id": "deterministic-rules (non-LLM)",
            "task": "report_review",
            "request_latency_ms": 0.0,
            "request_latency_seconds": 0.0,
            "fallback_status": True,
            "errors": "Deterministic verification active (non-LLM)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        call_records.append(fallback_rec)

    # Attach review assessment and updated model call records to final report
    final_report["review_assessment"] = review_assessment
    final_report["model_call_records"] = call_records

    return {
        "final_report": final_report,
        "review_assessment": review_assessment,
        "model_call_records": call_records,
    }
