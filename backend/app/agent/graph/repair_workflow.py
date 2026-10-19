import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from backend.app.agent.git.base import GitProvider
from backend.app.agent.git.factory import GitProviderFactory
from backend.app.agent.graph.nodes.repair.authorize_repository import authorize_repository_node
from backend.app.agent.graph.nodes.repair.await_approval import await_approval_node
from backend.app.agent.graph.nodes.repair.evaluate_result import evaluate_result_node
from backend.app.agent.graph.nodes.repair.form_code_hypothesis import form_code_hypothesis_node
from backend.app.agent.graph.nodes.repair.load_investigation import load_investigation_node
from backend.app.agent.graph.nodes.repair.locate_relevant_code import locate_relevant_code_node
from backend.app.agent.graph.nodes.repair.prepare_repair_artifact import prepare_repair_artifact_node
from backend.app.agent.graph.nodes.repair.propose_minimal_patch import propose_minimal_patch_node
from backend.app.agent.graph.nodes.repair.review_patch import review_patch_node
from backend.app.agent.graph.nodes.repair.run_isolated_validation import run_isolated_validation_node
from backend.app.agent.graph.nodes.repair.validate_evidence import validate_evidence_node
from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.runner.sandbox import IsolatedTestRunner
from backend.app.agent.schemas.repair import RepairStatus, ValidationStatus
from backend.app.common.config import Settings, get_settings
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def route_after_evidence_validation(state: RepairState) -> str:
    """Route to repository authorization if evidence is sufficient, else exit early."""
    if not state.get("has_sufficient_evidence", True):
        return "prepare_repair_artifact"
    return "authorize_repository"


def route_after_authorization(state: RepairState) -> str:
    """Route to code location if authorized, else exit early."""
    if not state.get("is_authorized", True):
        return "prepare_repair_artifact"
    return "locate_relevant_code"


def route_after_patch_review(state: RepairState) -> str:
    """Route to isolated validation if review passed; else retry or exit."""
    passed = state.get("patch_review_passed", True)
    iteration = state.get("iteration_count", 1)
    max_iter = state.get("max_iterations", 2)

    if not passed:
        if iteration < max_iter:
            return "propose_minimal_patch"
        return "prepare_repair_artifact"
    return "run_isolated_validation"


def route_after_evaluation(state: RepairState) -> str:
    """Route to patch refinement if tests failed and iterations remain; else prepare artifact."""
    val_status = state.get("validation_status", "")
    iteration = state.get("iteration_count", 1)
    max_iter = state.get("max_iterations", 2)

    if val_status == ValidationStatus.VALIDATION_FAILED.value and iteration < max_iter:
        return "propose_minimal_patch"
    return "prepare_repair_artifact"


def create_repair_graph(
    db: Optional[Session] = None,
    git_provider: Optional[GitProvider] = None,
    test_runner: Optional[IsolatedTestRunner] = None,
    llm_provider: Optional[LLMProvider] = None,
    settings: Optional[Settings] = None,
    user_identity: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> CompiledStateGraph:
    """
    Constructs and compiles the modular LangGraph AI Code Repair Agent workflow.
    Configures nodes with injected dependencies, bounded iteration limits, and
    mandatory human approval transitions.
    """
    provider = git_provider or GitProviderFactory.get_provider()
    runner = test_runner or IsolatedTestRunner(timeout_seconds=30.0)

    # Node wrappers capturing injected dependencies
    def node_load(state: RepairState) -> Dict[str, Any]:
        return load_investigation_node(state, db=db)

    def node_validate_ev(state: RepairState) -> Dict[str, Any]:
        return validate_evidence_node(state, settings=settings)

    def node_auth_repo(state: RepairState) -> Dict[str, Any]:
        return authorize_repository_node(state, git_provider=provider, user_identity=user_identity)

    def node_locate_code(state: RepairState) -> Dict[str, Any]:
        return locate_relevant_code_node(state, git_provider=provider)

    def node_hypothesis(state: RepairState) -> Dict[str, Any]:
        return form_code_hypothesis_node(state, llm_provider=llm_provider)

    def node_patch(state: RepairState) -> Dict[str, Any]:
        return propose_minimal_patch_node(state, llm_provider=llm_provider)

    def node_review(state: RepairState) -> Dict[str, Any]:
        return review_patch_node(state, settings=settings)

    def node_validate_run(state: RepairState) -> Dict[str, Any]:
        return run_isolated_validation_node(state, test_runner=runner, repo_root=repo_root, git_provider=provider)

    def node_eval_res(state: RepairState) -> Dict[str, Any]:
        return evaluate_result_node(state)

    def node_prepare(state: RepairState) -> Dict[str, Any]:
        return prepare_repair_artifact_node(state, git_provider=provider)

    def node_await_app(state: RepairState) -> Dict[str, Any]:
        return await_approval_node(state)

    # Initialize StateGraph
    workflow = StateGraph(RepairState)

    # Add nodes
    workflow.add_node("load_investigation", node_load)
    workflow.add_node("validate_evidence", node_validate_ev)
    workflow.add_node("authorize_repository", node_auth_repo)
    workflow.add_node("locate_relevant_code", node_locate_code)
    workflow.add_node("form_code_hypothesis", node_hypothesis)
    workflow.add_node("propose_minimal_patch", node_patch)
    workflow.add_node("review_patch", node_review)
    workflow.add_node("run_isolated_validation", node_validate_run)
    workflow.add_node("evaluate_result", node_eval_res)
    workflow.add_node("prepare_repair_artifact", node_prepare)
    workflow.add_node("await_approval", node_await_app)

    # Linear flow until evidence validation
    workflow.add_edge(START, "load_investigation")
    workflow.add_edge("load_investigation", "validate_evidence")

    # Conditional branch after evidence validation
    workflow.add_conditional_edges(
        "validate_evidence",
        route_after_evidence_validation,
        {
            "authorize_repository": "authorize_repository",
            "prepare_repair_artifact": "prepare_repair_artifact",
        },
    )

    # Conditional branch after repository authorization
    workflow.add_conditional_edges(
        "authorize_repository",
        route_after_authorization,
        {
            "locate_relevant_code": "locate_relevant_code",
            "prepare_repair_artifact": "prepare_repair_artifact",
        },
    )

    # Code inspection to patch generation
    workflow.add_edge("locate_relevant_code", "form_code_hypothesis")
    workflow.add_edge("form_code_hypothesis", "propose_minimal_patch")
    workflow.add_edge("propose_minimal_patch", "review_patch")

    # Conditional branch after patch review (syntax / security checks)
    workflow.add_conditional_edges(
        "review_patch",
        route_after_patch_review,
        {
            "run_isolated_validation": "run_isolated_validation",
            "propose_minimal_patch": "propose_minimal_patch",
            "prepare_repair_artifact": "prepare_repair_artifact",
        },
    )

    workflow.add_edge("run_isolated_validation", "evaluate_result")

    # Conditional branch after test evaluation (bounded iteration on failure)
    workflow.add_conditional_edges(
        "evaluate_result",
        route_after_evaluation,
        {
            "propose_minimal_patch": "propose_minimal_patch",
            "prepare_repair_artifact": "prepare_repair_artifact",
        },
    )

    # Mandatory human approval boundary before END
    workflow.add_edge("prepare_repair_artifact", "await_approval")
    workflow.add_edge("await_approval", END)

    logger.info("Compiled LangGraph AI Code Repair StateGraph successfully")
    return workflow.compile()
