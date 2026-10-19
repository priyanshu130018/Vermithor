import logging
from typing import Any, Dict

from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.schemas.repair import RepairStatus, ValidationStatus

logger = logging.getLogger(__name__)


def evaluate_result_node(state: RepairState) -> Dict[str, Any]:
    """
    Evaluate the validation outcome:
    - VALIDATED: all tests passed cleanly.
    - VALIDATION_FAILED: tests executed but one or more assertions failed.
    - VALIDATION_BLOCKED: environment, runner, or dependencies were missing.
    """
    val_status_str = state.get("validation_status") or ValidationStatus.PENDING.value
    val_result = state.get("validation_result") or {}
    iteration = state.get("iteration_count", 1)
    max_iter = state.get("max_iterations", 2)

    logger.info("Evaluating validation result: %s (iteration %d of %d)", val_status_str, iteration, max_iter)

    if val_status_str == ValidationStatus.VALIDATED.value:
        return {
            "status": RepairStatus.VALIDATED.value,
            "error_message": None,
        }
    elif val_status_str == ValidationStatus.VALIDATION_FAILED.value:
        error_msg = val_result.get("error_message") or "Tests executed in sandbox but failed"
        return {
            "status": RepairStatus.VALIDATION_FAILED.value,
            "error_message": error_msg,
        }
    elif val_status_str == ValidationStatus.VALIDATION_BLOCKED.value:
        error_msg = val_result.get("error_message") or "Test environment was blocked or missing runner"
        return {
            "status": RepairStatus.VALIDATION_BLOCKED.value,
            "error_message": error_msg,
        }

    return {
        "status": RepairStatus.VALIDATION_FAILED.value,
        "error_message": "Unknown test execution state",
    }
