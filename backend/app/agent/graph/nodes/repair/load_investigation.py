import logging
from typing import Any, Dict
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation
from backend.app.agent.graph.repair_state import RepairState

logger = logging.getLogger(__name__)


def load_investigation_node(state: RepairState, db: Session) -> Dict[str, Any]:
    """
    Retrieve completed investigation using investigation_key (or ID).
    Extracts leading hypothesis, confidence, target service, and evidence citations.
    """
    inv_key = state.get("investigation_key", "")
    logger.info("Repair Agent node: load_investigation for key '%s'", inv_key)

    inv_filter = Investigation.investigation_key == inv_key
    try:
        import uuid
        val_uuid = uuid.UUID(inv_key)
        inv_filter = (Investigation.investigation_key == inv_key) | (Investigation.id == val_uuid)
    except (ValueError, AttributeError):
        pass

    inv = db.query(Investigation).filter(inv_filter).first()

    if not inv:
        logger.warning("Investigation '%s' not found in database", inv_key)
        return {
            "status": "FAILED",
            "error_message": f"Investigation '{inv_key}' does not exist",
            "has_sufficient_evidence": False,
        }

    report = inv.report_json or {}
    evidence_items = inv.evidence_json or []
    citations = [
        item.get("description", str(item)) if isinstance(item, dict) else str(item)
        for item in evidence_items
    ]
    if not citations and "observed_facts" in report:
        citations = report.get("observed_facts", [])

    return {
        "incident_key": inv.incident_key,
        "target_service": inv.target_service,
        "investigation_report": report,
        "confidence": inv.confidence,
        "evidence_citations": citations,
        "status": "INSPECTING_CODE",
    }
