import logging
from typing import Any, Callable, Dict, Optional
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from backend.app.agent.graph.nodes.check_completeness import check_completeness_node
from backend.app.agent.graph.nodes.correlate_evidence import correlate_evidence_node
from backend.app.agent.graph.nodes.evaluate_anomalies import evaluate_anomalies_node
from backend.app.agent.graph.nodes.evaluate_hypotheses import evaluate_hypotheses_node
from backend.app.agent.graph.nodes.gather_additional import gather_additional_evidence_node
from backend.app.agent.graph.nodes.gather_evidence import gather_evidence_node
from backend.app.agent.graph.nodes.generate_rca import generate_rca_node
from backend.app.agent.graph.nodes.initialize import initialize_investigation_node
from backend.app.agent.graph.nodes.produce_report import produce_report_node
from backend.app.agent.graph.nodes.retrieve_knowledge import retrieve_knowledge_node
from backend.app.agent.graph.state import InvestigationState
from backend.app.anomaly.services.anomaly_service import AnomalyService
from backend.app.common.config import Settings, get_settings
from backend.app.correlation.services.correlation_service import CorrelationService
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService
from backend.app.rca.analysis.analyzer import RCAAnalyzer
from backend.app.retrieval.retrieval.engine import RetrievalEngine
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def should_query_more(state: InvestigationState) -> str:
    """Conditional transition router: directs to bounded additional query or final report."""
    needs_query = state.get("needs_additional_query", False)
    query_iter = state.get("query_iteration", 0)
    max_iter = state.get("max_query_iterations", 2)

    if needs_query and query_iter < max_iter:
        return "gather_additional"
    return "produce_report"


def create_investigation_graph(
    db: Optional[Session] = None,
    telemetry_service: Optional[TelemetryEvidenceService] = None,
    anomaly_service: Optional[AnomalyService] = None,
    correlation_service: Optional[CorrelationService] = None,
    rca_analyzer: Optional[RCAAnalyzer] = None,
    retrieval_engine: Optional[RetrievalEngine] = None,
    llm_provider: Optional[LLMProvider] = None,
    settings: Optional[Settings] = None,
) -> CompiledStateGraph:
    """
    Constructs and compiles the modular LangGraph AI Incident Investigation Agent workflow.
    Configures nodes with injected service dependencies and enforces bounded conditional cycles.
    """
    cfg = settings or get_settings()

    # Node wrappers capturing injected dependencies
    def node_initialize(state: InvestigationState) -> Dict[str, Any]:
        return initialize_investigation_node(state, db=db)

    def node_gather(state: InvestigationState) -> Dict[str, Any]:
        return gather_evidence_node(state, db=db, telemetry_service=telemetry_service)

    def node_anomalies(state: InvestigationState) -> Dict[str, Any]:
        return evaluate_anomalies_node(state, db=db, anomaly_service=anomaly_service)

    def node_correlate(state: InvestigationState) -> Dict[str, Any]:
        return correlate_evidence_node(state, db=db, correlation_service=correlation_service)

    def node_rca(state: InvestigationState) -> Dict[str, Any]:
        return generate_rca_node(state, db=db, rca_analyzer=rca_analyzer)

    def node_knowledge(state: InvestigationState) -> Dict[str, Any]:
        return retrieve_knowledge_node(state, db=db, retrieval_engine=retrieval_engine)

    def node_evaluate(state: InvestigationState) -> Dict[str, Any]:
        return evaluate_hypotheses_node(state, db=db, llm_provider=llm_provider, settings=cfg)

    def node_completeness(state: InvestigationState) -> Dict[str, Any]:
        return check_completeness_node(state)

    def node_additional(state: InvestigationState) -> Dict[str, Any]:
        return gather_additional_evidence_node(state, db=db, telemetry_service=telemetry_service)

    def node_report(state: InvestigationState) -> Dict[str, Any]:
        return produce_report_node(state, db=db)

    # Initialize StateGraph with typed investigation state
    workflow = StateGraph(InvestigationState)

    # Add processing nodes
    workflow.add_node("initialize", node_initialize)
    workflow.add_node("gather_evidence", node_gather)
    workflow.add_node("evaluate_anomalies", node_anomalies)
    workflow.add_node("correlate_evidence", node_correlate)
    workflow.add_node("generate_rca", node_rca)
    workflow.add_node("retrieve_knowledge", node_knowledge)
    workflow.add_node("evaluate_hypotheses", node_evaluate)
    workflow.add_node("check_completeness", node_completeness)
    workflow.add_node("gather_additional", node_additional)
    workflow.add_node("produce_report", node_report)

    # Linear investigation edges
    workflow.add_edge(START, "initialize")
    workflow.add_edge("initialize", "gather_evidence")
    workflow.add_edge("gather_evidence", "evaluate_anomalies")
    workflow.add_edge("evaluate_anomalies", "correlate_evidence")
    workflow.add_edge("correlate_evidence", "generate_rca")
    workflow.add_edge("generate_rca", "retrieve_knowledge")
    workflow.add_edge("retrieve_knowledge", "evaluate_hypotheses")
    workflow.add_edge("evaluate_hypotheses", "check_completeness")

    # Conditional branching for bounded evidence iteration
    workflow.add_conditional_edges(
        "check_completeness",
        should_query_more,
        {
            "gather_additional": "gather_additional",
            "produce_report": "produce_report",
        },
    )

    # Re-evaluate hypotheses with gathered additional evidence
    workflow.add_edge("gather_additional", "evaluate_hypotheses")

    # Termination
    workflow.add_edge("produce_report", END)

    logger.info("Compiled LangGraph Investigation StateGraph successfully")
    return workflow.compile()
