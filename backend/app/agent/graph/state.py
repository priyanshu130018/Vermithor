from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class InvestigationState(TypedDict, total=False):
    """
    Validated, typed state schema for the Vermithor LangGraph AI Incident Investigation Agent.
    Compatible with LangGraph 1.2+ StateGraph.
    Tracks all evidence, hypotheses, knowledge, errors, and diagnostic outcomes.
    """
    # Incident & Investigation Identifiers
    investigation_id: str
    incident_key: str
    incident_id: Optional[str]
    incident_title: str
    target_service: str
    environment: str
    severity: str

    # Bounded Time Window
    lookback_minutes: int
    window_start: str
    window_end: str

    # Collected Observability Telemetry & Topology Evidence
    collected_evidence: List[Dict[str, Any]]
    raw_metrics: Dict[str, Any]
    raw_traces: List[Dict[str, Any]]
    raw_events: List[Dict[str, Any]]
    deployments: List[Dict[str, Any]]
    topology_dependencies: List[str]
    topology_dependents: List[str]

    # Anomaly Detection & Correlation State
    anomalies: List[Dict[str, Any]]
    correlation_group_key: Optional[str]
    correlation_score: float
    correlation_reasons: List[str]

    # Root Cause Analysis (RCA) Hypotheses & Causal Graph
    rca_candidates: List[Dict[str, Any]]
    causal_chain: List[Dict[str, Any]]
    causal_edges: List[Dict[str, Any]]
    primary_root_cause: Optional[str]
    primary_confidence: float
    leading_hypothesis: Optional[str]

    # Retrieved Supporting Knowledge (RAG & Historical Incidents)
    runbooks: List[Dict[str, Any]]
    similar_incidents: List[Dict[str, Any]]

    # Evidence Evaluation & Hypothesis Testing
    hypotheses_evaluated: List[Dict[str, Any]]
    observed_facts: List[str]
    inferred_relationships: List[str]
    confirmed_findings: List[str]
    missing_evidence: List[str]
    contradictory_evidence: List[str]
    uncertainty_assessment: str
    recommended_diagnostic_steps: List[Dict[str, Any]]

    # Investigation Completeness & Bounded Query Control
    query_iteration: int
    max_query_iterations: int
    needs_additional_query: bool
    additional_query_targets: List[str]

    # Model & Execution Metadata
    llm_provider: str
    llm_model: Optional[str]
    is_fallback: bool
    status: str
    errors: List[str]
    model_call_records: List[Dict[str, Any]]
    review_assessment: Optional[Dict[str, Any]]

    # Final Structured Report Output
    final_report: Optional[Dict[str, Any]]
