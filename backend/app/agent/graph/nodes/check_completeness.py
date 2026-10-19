import logging
from typing import Any, Dict, List

from backend.app.agent.graph.state import InvestigationState

logger = logging.getLogger(__name__)


def check_completeness_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Step 8: Check investigation completeness. Determines whether essential evidence is missing
    and whether a bounded additional query can resolve ambiguities, enforcing iteration limits.
    """
    query_iter = state.get("query_iteration", 0)
    max_iter = state.get("max_query_iterations", 2)
    primary_conf = state.get("primary_confidence", 0.0)
    primary_cause = (state.get("primary_root_cause") or "").lower()
    missing_evidence = state.get("missing_evidence", [])
    deps = state.get("topology_dependencies", [])
    evidence = state.get("collected_evidence", [])

    # Check services already queried
    queried_services = {e.get("service") for e in evidence if e.get("service")}

    # Candidate downstream targets that have not yet been queried
    unqueried_deps = [d for d in deps if d not in queried_services]

    # Needs additional query if iteration budget remains AND (low confidence OR downstream dependency implicated)
    needs_query = False
    targets: List[str] = []

    if query_iter < max_iter:
        # Check if database or cache is suspected but direct telemetry wasn't queried
        if ("database" in primary_cause or "postgres" in primary_cause) and "postgres" in unqueried_deps:
            needs_query = True
            targets.append("postgres")
        elif ("redis" in primary_cause or "cache" in primary_cause) and ("redis" in unqueried_deps or "cache-service" in unqueried_deps):
            needs_query = True
            targets.append("redis" if "redis" in unqueried_deps else "cache-service")
        elif primary_conf < 0.60 and unqueried_deps:
            needs_query = True
            targets.append(unqueried_deps[0])

    if needs_query:
        logger.info(
            "Investigation incomplete: triggering bounded query iteration %d/%d for targets %s",
            query_iter + 1,
            max_iter,
            targets,
        )
    else:
        logger.info(
            "Investigation complete: proceeding to final report (iterations used: %d/%d, confidence: %.2f)",
            query_iter,
            max_iter,
            primary_conf,
        )

    return {
        "needs_additional_query": needs_query,
        "additional_query_targets": targets,
    }
