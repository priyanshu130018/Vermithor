import logging
from typing import Any, Dict, List, Optional, Set
from backend.app.topology.service_graph import ServiceTopologyGraph, get_service_topology_graph

logger = logging.getLogger(__name__)


class TopologyEvidenceResult:
    """Evaluated topological plausibility and dependency paths."""

    def __init__(
        self,
        candidate_service: str,
        score: float,
        is_upstream_cause: bool,
        supported_symptom_services: List[str],
        dependency_paths: Dict[str, List[str]],
        description: str,
    ):
        self.candidate_service = candidate_service
        self.score = score
        self.is_upstream_cause = is_upstream_cause
        self.supported_symptom_services = supported_symptom_services
        self.dependency_paths = dependency_paths
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_service": self.candidate_service,
            "score": round(self.score, 4),
            "is_upstream_cause": self.is_upstream_cause,
            "supported_symptom_services": self.supported_symptom_services,
            "dependency_paths": self.dependency_paths,
            "description": self.description,
        }


class TopologyEvidenceEvaluator:
    """
    Validates causal propagation using known service dependency topologies.
    Verifies that suspected root cause services (e.g. databases, caches, core APIs)
    are legitimate dependencies of services exhibiting degraded symptoms.
    """

    def __init__(self, topology_graph: Optional[ServiceTopologyGraph] = None):
        self.topology = topology_graph or get_service_topology_graph()

    def evaluate_candidate(
        self,
        candidate_service: str,
        symptom_signals: List[Dict[str, Any]],
    ) -> TopologyEvidenceResult:
        """
        Evaluate if `candidate_service` can explain symptoms on all observed symptom services.
        """
        cand = candidate_service.lower()
        observed_services = {
            s.get("service", "").lower()
            for s in symptom_signals
            if s.get("service") and s.get("service", "").lower() != cand
        }

        if not observed_services:
            # All signals are on the candidate service itself
            return TopologyEvidenceResult(
                candidate_service=candidate_service,
                score=0.90,
                is_upstream_cause=True,
                supported_symptom_services=[candidate_service],
                dependency_paths={candidate_service: [candidate_service]},
                description=f"Candidate service '{candidate_service}' is the direct origin of observed signals.",
            )

        supported_services: List[str] = []
        paths: Dict[str, List[str]] = {}

        for symptom_svc in sorted(observed_services):
            if self.topology.is_dependency(cand, symptom_svc):
                supported_services.append(symptom_svc)
                path = self.topology.get_dependency_path(symptom_svc, cand)
                if path:
                    paths[symptom_svc] = path

        total_observed = len(observed_services)
        covered_count = len(supported_services)

        if covered_count == 0:
            # Candidate has no dependency path to any failing service
            return TopologyEvidenceResult(
                candidate_service=candidate_service,
                score=0.20,
                is_upstream_cause=False,
                supported_symptom_services=[],
                dependency_paths={},
                description=f"Topology check: No dependency path found from symptom services ({', '.join(sorted(observed_services))}) to '{candidate_service}'.",
            )

        coverage_ratio = covered_count / total_observed
        topo_score = 0.50 + (coverage_ratio * 0.50)  # 0.50 to 1.0

        path_summaries = []
        for svc, p in list(paths.items())[:2]:
            path_summaries.append(" -> ".join(p))

        desc = (
            f"Topology validated: '{candidate_service}' is upstream dependency for {covered_count}/{total_observed} "
            f"symptom services ({'; '.join(path_summaries)})."
        )

        return TopologyEvidenceResult(
            candidate_service=candidate_service,
            score=round(topo_score, 4),
            is_upstream_cause=True,
            supported_symptom_services=supported_services,
            dependency_paths=paths,
            description=desc,
        )
