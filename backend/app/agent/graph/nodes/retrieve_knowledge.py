import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.retrieval.repositories.runbook_repository import RunbookRepository
from backend.app.retrieval.retrieval.engine import RetrievalEngine
from backend.app.retrieval.schemas.retrieval import RetrievalQuery, SourceType

logger = logging.getLogger(__name__)


def retrieve_knowledge_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    retrieval_engine: Optional[RetrievalEngine] = None,
) -> Dict[str, Any]:
    """
    Step 6: Retrieve relevant operational runbooks and similar historical incidents
    using Vermithor's existing RetrievalEngine and RunbookRepository.
    """
    target_svc = state.get("target_service", "unknown")
    primary_cause = state.get("primary_root_cause", "")
    incident_key = state.get("incident_key", "UNKNOWN")
    collected_evidence: List[Dict[str, Any]] = list(state.get("collected_evidence", []))

    engine = retrieval_engine or RetrievalEngine()

    runbooks: List[Dict[str, Any]] = []
    similar_incidents: List[Dict[str, Any]] = []

    # Construct search query from incident context and primary root cause
    search_query = f"{target_svc} {primary_cause}".strip()

    if db is not None:
        # 1. Search Runbooks via RunbookRepository
        try:
            rb_items = RunbookRepository.search_runbooks(
                db=db,
                query=search_query,
                top_k=5,
                service=target_svc,
            )
            for item in rb_items:
                runbooks.append({
                    "runbook_key": item.source_id,
                    "title": item.title,
                    "service": item.service,
                    "content": item.content[:400] if item.content else "",
                    "similarity_score": item.similarity_score,
                })
        except Exception as exc:
            logger.warning("Error querying runbooks via RunbookRepository: %s", exc)

        # 2. Search Similar Incidents via RetrievalEngine
        try:
            retrieval_req = RetrievalQuery(
                query=search_query,
                service=target_svc,
                source_types=[SourceType.INCIDENT],
                top_k=3,
            )
            resp = engine.execute_query(db=db, req=retrieval_req)
            for res_item in resp.results:
                if res_item.source_id != incident_key:
                    similar_incidents.append({
                        "incident_key": res_item.source_id,
                        "title": res_item.title,
                        "score": res_item.final_score,
                        "content": res_item.content[:250] if res_item.content else "",
                    })
        except Exception as exc:
            logger.warning("Error querying similar incidents via RetrievalEngine: %s", exc)

    # 3. Add Runbooks as Evidence Items
    seen_ids = {e.get("source_id") for e in collected_evidence}
    for idx, rb in enumerate(runbooks[:3], start=1):
        rb_key = rb.get("runbook_key", f"RB-{idx}")
        if rb_key not in seen_ids:
            seen_ids.add(rb_key)
            collected_evidence.append({
                "evidence_id": f"EV-RB-{idx}",
                "source_type": "RUNBOOK",
                "source_id": rb_key,
                "service": rb.get("service") or target_svc,
                "timestamp": None,
                "claim": f"Runbook {rb_key}: '{rb.get('title')}' (Relevance: {rb.get('similarity_score', 0.0):.2f})",
                "data": rb,
            })

    # 4. Add Similar Incidents as Evidence Items
    for idx, sim in enumerate(similar_incidents[:2], start=1):
        sim_key = sim.get("incident_key", f"INC-SIM-{idx}")
        if sim_key not in seen_ids:
            seen_ids.add(sim_key)
            collected_evidence.append({
                "evidence_id": f"EV-SIM-{idx}",
                "source_type": "HISTORICAL_INCIDENT",
                "source_id": sim_key,
                "service": target_svc,
                "timestamp": None,
                "claim": f"Historical incident {sim_key}: '{sim.get('title')}' (Match score: {sim.get('score', 0.0):.2f})",
                "data": sim,
            })

    logger.info(
        "Knowledge retrieval completed: %d runbooks, %d similar incidents retrieved",
        len(runbooks),
        len(similar_incidents),
    )

    return {
        "runbooks": runbooks,
        "similar_incidents": similar_incidents,
        "collected_evidence": collected_evidence,
    }
