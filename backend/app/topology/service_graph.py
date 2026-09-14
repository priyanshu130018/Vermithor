import logging
from typing import Dict, List, Optional, Set, Tuple
import networkx as nx

logger = logging.getLogger(__name__)


class ServiceTopologyGraph:
    """
    Maintains a directed dependency graph of microservices, databases, caches, and external systems.
    Edges represent dependencies: (A, B) means Service A depends on Service B.
    Therefore, failure in B propagates upstream to A.
    """

    def __init__(self, edges: Optional[List[Tuple[str, str]]] = None):
        self.graph = nx.DiGraph()
        default_edges = [
            ("gateway", "auth-service"),
            ("gateway", "booking-api"),
            ("gateway", "catalog-api"),
            ("booking-api", "payment-service"),
            ("booking-api", "cache-service"),
            ("booking-api", "postgres"),
            ("payment-service", "postgres"),
            ("catalog-api", "cache-service"),
            ("catalog-api", "postgres"),
            ("auth-service", "postgres"),
            ("cache-service", "redis"),
            ("backup-worker", "postgres"),
        ]
        edges_to_add = edges if edges is not None else default_edges
        for src, dst in edges_to_add:
            self.add_dependency(src.lower(), dst.lower())

    def add_dependency(self, dependent: str, dependency: str) -> None:
        """Register that `dependent` calls/depends upon `dependency`."""
        self.graph.add_edge(dependent.lower(), dependency.lower())

    def has_service(self, service: str) -> bool:
        """Check if service node exists in topology graph."""
        return self.graph.has_node(service.lower())

    def is_dependency(self, candidate_root_cause: str, symptom_service: str) -> bool:
        """
        Check if `candidate_root_cause` is a direct or transitive dependency of `symptom_service`.
        If True, a failure in `candidate_root_cause` can plausibly cause symptoms in `symptom_service`.
        """
        cand = candidate_root_cause.lower()
        symptom = symptom_service.lower()

        if cand == symptom:
            return True

        if not self.graph.has_node(symptom) or not self.graph.has_node(cand):
            # Check for common infrastructure mappings (e.g. database / db -> postgres)
            if cand in ["database", "db"] and self.is_dependency("postgres", symptom):
                return True
            if cand in ["cache", "redis"] and self.is_dependency("redis", symptom):
                return True
            return False

        return nx.has_path(self.graph, symptom, cand)

    def get_dependency_path(self, symptom_service: str, candidate_root_cause: str) -> List[str]:
        """Return the shortest dependency path from symptom_service to candidate_root_cause."""
        symptom = symptom_service.lower()
        cand = candidate_root_cause.lower()

        if cand in ["database", "db"] and not self.graph.has_node(cand):
            cand = "postgres"
        if cand in ["cache", "redis"] and not self.graph.has_node(cand):
            cand = "redis"

        if not self.graph.has_node(symptom) or not self.graph.has_node(cand):
            return []

        try:
            return nx.shortest_path(self.graph, symptom, cand)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_all_dependencies(self, service: str) -> Set[str]:
        """Get all downstream components that `service` directly or indirectly relies upon."""
        svc = service.lower()
        if not self.graph.has_node(svc):
            return set()
        return nx.descendants(self.graph, svc)

    def get_all_dependents(self, service: str) -> Set[str]:
        """Get all upstream services that depend on `service` (affected if `service` fails)."""
        svc = service.lower()
        if not self.graph.has_node(svc):
            return set()
        return nx.ancestors(self.graph, svc)


_default_topology_graph: Optional[ServiceTopologyGraph] = None


def get_service_topology_graph() -> ServiceTopologyGraph:
    """Singleton getter for default ServiceTopologyGraph."""
    global _default_topology_graph
    if _default_topology_graph is None:
        _default_topology_graph = ServiceTopologyGraph()
    return _default_topology_graph
