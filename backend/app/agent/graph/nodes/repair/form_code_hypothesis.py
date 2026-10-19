import json
import logging
from typing import Any, Dict, Optional

from backend.app.agent.graph.repair_state import RepairState
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def form_code_hypothesis_node(
    state: RepairState,
    llm_provider: Optional[LLMProvider] = None,
) -> Dict[str, Any]:
    """
    Synthesize inspected code with incident telemetry to form a code-level defect explanation.
    Connects the observed symptoms (e.g. pool saturation, acquisition timeout) to code structures.
    Uses deterministic fallback when LLM is unavailable or fails.
    """
    incident_key = state.get("incident_key", "")
    target_service = state.get("target_service", "unknown")
    citations = state.get("evidence_citations") or []
    inspected_files = state.get("inspected_files") or {}
    report = state.get("investigation_report") or {}
    leading_hyp = report.get("leading_hypothesis") or "Service failure under load"

    is_fallback = False
    model_provider_name = "unknown"
    model_name = None

    # Check LLM availability
    use_llm = llm_provider is not None and llm_provider.is_available()
    if use_llm:
        model_provider_name = llm_provider.get_provider_name()
        model_name = llm_provider.get_model_name()

        # Build prompt
        files_summary = "\n\n".join(
            [f"--- File: {path} ---\n{content[:2000]}" for path, content in inspected_files.items()]
        )
        prompt = f"""You are Vermithor's AI Code Repair Agent. Analyze the incident evidence and inspected source files to identify the code-level defect.

INCIDENT KEY: {incident_key}
TARGET SERVICE: {target_service}
LEADING HYPOTHESIS: {leading_hyp}
EVIDENCE OBSERVED:
{chr(10).join(f"- {c}" for c in citations[:8])}

INSPECTED SOURCE FILES:
{files_summary}

Respond in STRICT JSON with the following keys:
{{
  "suspected_defect": "Precise technical explanation of the defect in code causing the incident",
  "expected_behavior": "What the code should do instead",
  "potential_regressions": ["List of potential functional or performance regressions to guard against"],
  "security_implications": ["Security or isolation risks associated with changing this code"]
}}
"""
        try:
            raw_response = llm_provider.generate(prompt)
            # Parse JSON
            cleaned = raw_response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            parsed = json.loads(cleaned)
            return {
                "suspected_defect": parsed.get("suspected_defect", ""),
                "expected_behavior": parsed.get("expected_behavior", ""),
                "potential_regressions": parsed.get("potential_regressions", []),
                "security_implications": parsed.get("security_implications", []),
                "model_provider": model_provider_name,
                "model_name": model_name,
                "is_fallback": False,
            }
        except Exception as exc:
            logger.warning("LLM hypothesis formulation failed (%s); triggering deterministic fallback", exc)
            is_fallback = True

    # Deterministic fallback behavior
    is_fallback = True
    model_provider_name = "deterministic_fallback"
    model_name = "rules-engine-v1"

    # Grounded fallback reasoning based on telemetry evidence
    if "pool" in leading_hyp.lower() or any("pool" in c.lower() or "connection" in c.lower() for c in citations):
        defect = (
            f"Database connection pool configuration or transaction handling in '{target_service}' "
            "exhausts pool capacity under concurrent requests due to low maximum pool limits or "
            "missing connection release during transaction error handling."
        )
        expected = "Connection pool allocates sufficient capacity and ensures all acquired connections are promptly released."
        regressions = ["Increased database memory utilization if pool size exceeds database connection limits"]
        security_impl = ["Ensure connection string and credentials are not hardcoded or logged in pool diagnostics"]
    elif "deployment" in leading_hyp.lower():
        defect = (
            f"Recent deployment in '{target_service}' introduced regression in request handler or resource configuration."
        )
        expected = "Service handles request lifecycle without resource exhaustion."
        regressions = ["Incompatibility with legacy client payloads"]
        security_impl = ["Preserve authentication middleware and request validation"]
    else:
        defect = f"Resource exhaustion or unhandled exception in '{target_service}' leading to latency and error cascade."
        expected = "Service returns fast error or recovers cleanly under degraded conditions."
        regressions = ["Potential timeouts on dependent upstream services"]
        security_impl = ["Ensure error messages do not leak internal stack traces to callers"]

    return {
        "suspected_defect": defect,
        "expected_behavior": expected,
        "potential_regressions": regressions,
        "security_implications": security_impl,
        "model_provider": model_provider_name,
        "model_name": model_name,
        "is_fallback": is_fallback,
    }
