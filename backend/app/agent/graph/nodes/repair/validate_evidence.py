import logging
from typing import Any, Dict, Optional

from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.schemas.repair import RepairStatus

logger = logging.getLogger(__name__)


def validate_evidence_node(state: RepairState, settings: Optional[Any] = None) -> Dict[str, Any]:
    """
    Confirm that the source investigation has sufficient confidence and actionable
    telemetry evidence to justify inspecting source code and generating repairs.
    Enforces configurable thresholds and strict grounding.
    """
    confidence = state.get("confidence", 0.0)
    report = state.get("investigation_report") or {}
    evidence_citations = state.get("evidence_citations") or []
    inv_status = str(report.get("status") or "").upper()
    uncertainty = str(report.get("uncertainty_assessment") or "").lower()

    # Configurable threshold defaulting to 0.50
    threshold = 0.50
    if settings and hasattr(settings, "AGENT_REPAIR_CONFIDENCE_THRESHOLD"):
        threshold = float(settings.AGENT_REPAIR_CONFIDENCE_THRESHOLD)

    # Threshold for actionable investigation report
    is_insufficient = (
        confidence < threshold
        or inv_status in ("INSUFFICIENT_EVIDENCE", "FAILED")
        or len(evidence_citations) == 0
        or ("insufficient" in uncertainty and confidence < 0.65)
        or ("ambiguous" in uncertainty and confidence < 0.65)
        or ("unverified" in uncertainty and confidence < 0.55)
    )

    if is_insufficient:
        logger.info(
            "Evidence validation failed: confidence=%.2f (threshold=%.2f), citations=%d, status=%s. Halting repair workflow.",
            confidence,
            threshold,
            len(evidence_citations),
            inv_status,
        )
        return {
            "has_sufficient_evidence": False,
            "requires_human_approval": False,
            "status": RepairStatus.INSUFFICIENT_EVIDENCE.value,
            "error_message": (
                f"Investigation evidence is inconclusive (confidence: {confidence:.2f} < threshold: {threshold:.2f}, "
                f"status: '{inv_status or 'UNKNOWN'}', citations: {len(evidence_citations)}). "
                "Halting repair to prevent speculative or ungrounded code modifications."
            ),
        }

    logger.info("Investigation evidence validated successfully with confidence=%.2f (threshold=%.2f)", confidence, threshold)
    return {
        "has_sufficient_evidence": True,
        "status": RepairStatus.INSPECTING_CODE.value,
    }
