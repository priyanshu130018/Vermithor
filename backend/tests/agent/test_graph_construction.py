import pytest
from backend.app.agent.graph.workflow import create_investigation_graph, should_query_more
from backend.app.agent.graph.state import InvestigationState


def test_investigation_graph_compilation():
    """Verify that the LangGraph StateGraph builds and compiles without errors."""
    graph = create_investigation_graph()
    assert graph is not None
    # Check node keys
    nodes = list(graph.nodes.keys())
    expected_nodes = [
        "initialize",
        "gather_evidence",
        "evaluate_anomalies",
        "correlate_evidence",
        "generate_rca",
        "retrieve_knowledge",
        "evaluate_hypotheses",
        "check_completeness",
        "gather_additional",
        "produce_report",
    ]
    for expected in expected_nodes:
        assert expected in nodes, f"Node '{expected}' missing from graph"


def test_conditional_transition_logic():
    """Verify conditional transition routing logic."""
    # When needs_query is True and query_iteration < max_query_iterations
    state1: InvestigationState = {
        "needs_additional_query": True,
        "query_iteration": 0,
        "max_query_iterations": 2,
    }
    assert should_query_more(state1) == "gather_additional"

    # When query_iteration has reached max limit
    state2: InvestigationState = {
        "needs_additional_query": True,
        "query_iteration": 2,
        "max_query_iterations": 2,
    }
    assert should_query_more(state2) == "produce_report"

    # When needs_query is False
    state3: InvestigationState = {
        "needs_additional_query": False,
        "query_iteration": 0,
        "max_query_iterations": 2,
    }
    assert should_query_more(state3) == "produce_report"


def test_graph_max_iteration_termination():
    """Verify that graph terminates deterministically and does not enter infinite loops."""
    graph = create_investigation_graph()

    # Initial state with query_iteration already at max
    initial_state: InvestigationState = {
        "investigation_id": "INV-TEST-001",
        "incident_key": "INC-TEST-001",
        "incident_title": "Test Saturation",
        "target_service": "payment-api",
        "lookback_minutes": 15,
        "query_iteration": 2,
        "max_query_iterations": 2,
        "needs_additional_query": False,
        "additional_query_targets": [],
        "collected_evidence": [],
        "errors": [],
    }

    result = graph.invoke(initial_state)
    assert result is not None
    assert "final_report" in result
    assert result.get("status") in ["COMPLETED", "INSUFFICIENT_EVIDENCE"]
