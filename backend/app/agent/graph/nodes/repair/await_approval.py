import logging
from typing import Any, Dict

from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.schemas.repair import ApprovalStatus, RepairStatus

logger = logging.getLogger(__name__)


def await_approval_node(state: RepairState) -> Dict[str, Any]:
    """
    Enforce the mandatory human-in-the-loop review boundary.
    The agent explicitly transitions to AWAITING_APPROVAL and ceases autonomous action.
    Autonomous merging, deployment, or production modification is strictly prevented.
    """
    current_status = state.get("status")
    repair_key = state.get("repair_key", "")

    # If the workflow already exited early due to failure/insufficient evidence, preserve that state
    if current_status in (
        RepairStatus.INSUFFICIENT_EVIDENCE.value,
        RepairStatus.UNAUTHORIZED.value,
        RepairStatus.FAILED.value,
    ):
        return {}

    logger.info("Repair %s transitioned to AWAITING_APPROVAL. Awaiting explicit human review.", repair_key)

    return {
        "status": RepairStatus.AWAITING_APPROVAL.value,
        "requires_human_approval": True,
        "approval_status": ApprovalStatus.PENDING.value,
    }
