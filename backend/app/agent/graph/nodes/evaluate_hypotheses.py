from datetime import datetime, timezone
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.agent.prompts.investigation_prompt import InvestigationPromptBuilder
from backend.app.agent.schemas.investigation import DiagnosticStep, HypothesisEvaluation
from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory

logger = logging.getLogger(__name__)


def _extract_json_from_llm(raw_text: str) -> Optional[Dict[str, Any]]:
    """Robustly parse JSON object from LLM response string."""
    if not raw_text or not isinstance(raw_text, str):
        return None
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.debug("Failed to parse JSON directly: %s", exc)
    return None


def _build_deterministic_evaluation(state: InvestigationState) -> Dict[str, Any]:
    """
    Deterministic rule-based evaluation fallback when LLM is offline, times out, or fails.
    Preserves original RCA scores, links verified evidence IDs, and provides safe diagnostic steps.
    """
    target_svc = state.get("target_service", "unknown")
    evidence = state.get("collected_evidence", [])
    rca_candidates = state.get("rca_candidates", [])
    runbooks = state.get("runbooks", [])
    primary_cause = state.get("primary_root_cause") or "Insufficient evidence"
    primary_conf = state.get("primary_confidence", 0.0)

    # 1. Observed Facts from verified evidence
    observed_facts: List[str] = []
    for ev in evidence:
        ev_id = ev.get("evidence_id", "")
        claim = ev.get("claim", "")
        stype = ev.get("source_type", "")
        if stype in ["METRIC_OBSERVATION", "PROMETHEUS", "EVENT", "ANOMALY", "JAEGER"]:
            observed_facts.append(f"[{ev_id}] {claim}")
    if not observed_facts:
        observed_facts = [f"No direct telemetry anomalies observed for service {target_svc}"]

    # 2. Inferred Relationships
    inferred_relationships: List[str] = []
    deployments = state.get("deployments", [])
    if deployments:
        dep = deployments[0]
        inferred_relationships.append(
            f"Deployment event ({dep.get('event_id', 'dep')}) preceded incident symptoms by temporal sequencing"
        )
    for edge in state.get("causal_edges", []):
        inferred_relationships.append(
            f"Causal link: {edge.get('source')} -> {edge.get('target')} (weight={edge.get('weight', 0.0):.2f})"
        )
    if not inferred_relationships:
        inferred_relationships.append(f"Direct causal association with {target_svc}")

    # 3. Hypotheses Evaluated (strictly preserving original scores)
    hypotheses_evaluated: List[Dict[str, Any]] = []
    for idx, cand in enumerate(rca_candidates, start=1):
        c_name = cand.get("candidate_name", "Unknown")
        c_type = cand.get("candidate_type", "UNKNOWN")
        c_score = float(cand.get("confidence", 0.0))

        if c_score >= 0.70 and idx == 1:
            calibrated = "CONFIRMED" if len(evidence) >= 3 else "PLAUSIBLE"
        elif c_score >= 0.40:
            calibrated = "PLAUSIBLE"
        elif c_type == "UNKNOWN":
            calibrated = "INCONCLUSIVE"
        else:
            calibrated = "DISPROVEN" if c_score < 0.20 else "INCONCLUSIVE"

        # Match supporting evidence
        sup_ids = [
            e["evidence_id"]
            for e in evidence
            if (c_type.lower() in e.get("claim", "").lower())
            or (c_name.lower() in e.get("claim", "").lower())
            or ("RCA" in e.get("source_type", ""))
        ]

        hypotheses_evaluated.append({
            "hypothesis": c_name,
            "candidate_type": c_type,
            "original_score": c_score,
            "calibrated_status": calibrated,
            "supporting_evidence_ids": sup_ids[:5],
            "contradicting_evidence_ids": [],
            "reasoning": f"Grounded in Vermithor RCA multi-dimensional evaluation score of {c_score:.4f}.",
        })

    # 4. Confirmed Findings vs Unknowns
    confirmed_findings: List[str] = []
    is_uncertain_cause = any(
        k in primary_cause.lower()
        for k in ("insufficient", "inconclusive", "unknown", "transient", "ambiguous")
    )
    if primary_conf >= 0.70 and not is_uncertain_cause:
        confirmed_findings.append(f"{primary_cause} confirmed by telemetry evidence on {target_svc}.")
    else:
        confirmed_findings.append(f"Root cause inconclusive on {target_svc}: insufficient or ambiguous telemetry to confirm single origin.")

    # 5. Missing Evidence
    missing_evidence: List[str] = []
    deps = state.get("topology_dependencies", [])
    if deps and state.get("query_iteration", 0) == 0:
        missing_evidence.append(f"Downstream dependency telemetry for {', '.join(deps)} not yet correlated.")
    if not any("TRACE" in e.get("source_type", "") for e in evidence):
        missing_evidence.append("Distributed trace spans unavailable or not captured during window.")

    # 6. Uncertainty Assessment
    if primary_conf >= 0.85:
        uncertainty = f"Low uncertainty: High-confidence RCA alignment ({primary_conf:.1%}) backed by multiple telemetry signals."
    elif primary_conf >= 0.50:
        uncertainty = f"Moderate uncertainty: RCA candidate identified ({primary_conf:.1%}), but corroborating trace telemetry is limited."
    else:
        uncertainty = "High uncertainty: Symptoms observed without definitive upstream or downstream causal evidence."

    # 7. Recommended Diagnostic Steps (strictly diagnostic, requires human review)
    diagnostic_steps: List[Dict[str, Any]] = []
    if "database" in primary_cause.lower() or "postgres" in primary_cause.lower() or "pool" in primary_cause.lower():
        diagnostic_steps.append({
            "action": "Inspect pg_stat_activity for idle-in-transaction connection leaks and query active pool usage",
            "target_service": "postgres",
            "rationale": "Grounded in Database Connection Pool Exhaustion procedure (RB-000001 / RB-000006)",
            "priority": "HIGH",
            "requires_human_approval": True,
        })
        diagnostic_steps.append({
            "action": "Check application connection pool configuration (HikariCP / SQLAlchemy max_overflow and pool_timeout)",
            "target_service": target_svc,
            "rationale": "Verify whether connection pool sizing matches incoming request concurrency",
            "priority": "HIGH",
            "requires_human_approval": True,
        })
    elif "deploy" in primary_cause.lower():
        diagnostic_steps.append({
            "action": "Compare application error logs and latency delta immediately before and after deployment",
            "target_service": target_svc,
            "rationale": "Grounded in Faulty Deployment Rollback procedure (RB-000004)",
            "priority": "HIGH",
            "requires_human_approval": True,
        })
    else:
        diagnostic_steps.append({
            "action": f"Review detailed error logs and metric dashboard for {target_svc}",
            "target_service": target_svc,
            "rationale": "Standard triage to isolate failing component",
            "priority": "MEDIUM",
            "requires_human_approval": True,
        })

    alternative_explanations: List[str] = [
        c["candidate_name"]
        for c in rca_candidates[1:4]
        if c.get("candidate_name") != primary_cause
    ]

    fallback_record = {
        "provider": "fallback",
        "actual_model_id": "deterministic-rules (non-LLM)",
        "task": "investigation",
        "request_latency_ms": 0.0,
        "request_latency_seconds": 0.0,
        "fallback_status": True,
        "errors": state.get("errors", ["Fallback engaged"])[-1] if state.get("errors") else "Deterministic fallback engaged",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    existing_records = list(state.get("model_call_records", []))
    existing_records.append(fallback_record)

    return {
        "observed_facts": observed_facts,
        "inferred_relationships": inferred_relationships,
        "confirmed_findings": confirmed_findings,
        "hypotheses_evaluated": hypotheses_evaluated,
        "alternative_explanations": alternative_explanations,
        "missing_evidence": missing_evidence,
        "contradictory_evidence": [],
        "uncertainty_assessment": f"[Deterministic Rule-Based Fallback (Non-LLM)] {uncertainty}",
        "recommended_diagnostic_steps": diagnostic_steps,
        "is_fallback": True,
        "llm_provider": "fallback",
        "llm_model": "deterministic-rules (non-LLM)",
        "model_call_records": existing_records,
    }


def evaluate_hypotheses_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    llm_provider: Optional[LLMProvider] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """
    Step 7: Evaluate gathered evidence against candidate hypotheses using the configured cloud LLM,
    routed specifically to HF_INVESTIGATION_MODEL with automatic deterministic fallback if offline,
    times out, or credits are exhausted.
    """
    cfg = settings or get_settings()
    provider = llm_provider
    if provider is None:
        try:
            try:
                provider = ProviderFactory.get_provider(cfg, task="investigation")
            except TypeError:
                provider = ProviderFactory.get_provider(cfg)
        except Exception as exc:
            logger.warning("Could not initialize investigation LLM provider: %s", exc)
            provider = None

    incident_key = state.get("incident_key", "UNKNOWN")
    title = state.get("incident_title", f"Incident {incident_key}")
    target_svc = state.get("target_service", "unknown")
    environment = state.get("environment", "production")
    time_window = {"start": state.get("window_start", ""), "end": state.get("window_end", "")}
    evidence = state.get("collected_evidence", [])
    rca_candidates = state.get("rca_candidates", [])
    runbooks = state.get("runbooks", [])
    deps = state.get("topology_dependencies", [])
    call_records = list(state.get("model_call_records", []))

    # Check if LLM provider is available and allowed under Pilot Data Governance
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
        logger.info(
            "Pilot data governance: external LLM dispatch blocked for org '%s' (allow_external_llm=False). Using deterministic evaluation.",
            org_id,
        )
        use_llm = False

    if use_llm:
        try:
            prompt = InvestigationPromptBuilder.build_evaluation_prompt(
                incident_key=incident_key,
                title=title,
                service=target_svc,
                environment=environment,
                time_window=time_window,
                evidence_items=evidence,
                rca_candidates=rca_candidates,
                runbooks=runbooks,
                topology_deps=deps,
            )
            raw_response = ""
            call_rec: Optional[Dict[str, Any]] = None

            if hasattr(provider, "generate_with_telemetry"):
                raw_response, call_rec = provider.generate_with_telemetry(prompt, task="investigation")
            else:
                t0 = time.perf_counter()
                raw_response = provider.generate(prompt)
                lat = time.perf_counter() - t0
                call_rec = {
                    "provider": provider.get_provider_name(),
                    "actual_model_id": provider.get_model_name(),
                    "task": "investigation",
                    "request_latency_ms": round(lat * 1000.0, 2),
                    "request_latency_seconds": round(lat, 4),
                    "fallback_status": False,
                    "errors": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            if call_rec:
                call_records.append(call_rec)

            parsed = _extract_json_from_llm(raw_response)

            if parsed and "hypotheses_evaluated" in parsed:
                # Ensure diagnostic steps require human approval
                diag_steps = parsed.get("recommended_diagnostic_steps", [])
                for step in diag_steps:
                    step["requires_human_approval"] = True

                logger.info("LLM successfully evaluated hypotheses for incident %s", incident_key)
                return {
                    "observed_facts": parsed.get("observed_facts", []),
                    "inferred_relationships": parsed.get("inferred_relationships", []),
                    "confirmed_findings": parsed.get("confirmed_findings", []),
                    "hypotheses_evaluated": parsed.get("hypotheses_evaluated", []),
                    "alternative_explanations": parsed.get("alternative_explanations", []),
                    "missing_evidence": parsed.get("missing_evidence", []),
                    "contradictory_evidence": parsed.get("contradictory_evidence", []),
                    "uncertainty_assessment": parsed.get("uncertainty_assessment", "Evaluated by AI model"),
                    "recommended_diagnostic_steps": diag_steps,
                    "is_fallback": False,
                    "llm_provider": provider.get_provider_name(),
                    "llm_model": provider.get_model_name(),
                    "model_call_records": call_records,
                }
            else:
                logger.warning("LLM response did not parse into required schema. Falling back to deterministic rules.")
                state_errors = state.get("errors", [])
                state_errors.append("LLM response schema validation failure")
                state["errors"] = state_errors
        except Exception as exc:
            logger.warning("LLM generation failed: %s. Falling back to deterministic rules.", exc)
            state_errors = state.get("errors", [])
            state_errors.append(f"LLM failure: {exc}")
            state["errors"] = state_errors
            if provider and hasattr(provider, "get_call_history"):
                hist = provider.get_call_history()
                if hist:
                    call_records.append(hist[-1])

    # Deterministic Fallback Execution
    logger.info("Executing deterministic fallback evaluation for %s", incident_key)
    state["model_call_records"] = call_records
    return _build_deterministic_evaluation(state)
