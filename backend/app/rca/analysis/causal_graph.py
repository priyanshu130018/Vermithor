from datetime import datetime
from typing import Any, Dict, List, Tuple


class CausalGraphBuilder:
    """Constructs directed causal propagation graphs and linear incident causal chains."""

    @classmethod
    def build_graph(
        cls,
        signals: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Build directed causal edges and structured causal chain nodes from ordered signals.

        Returns:
            Tuple[List[Dict], List[Dict]]: (causal_edges, causal_chain)
        """
        if not signals:
            return [], []

        # Sort chronologically
        def parse_ts(ts: Any) -> datetime:
            if isinstance(ts, datetime):
                return ts
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

        sorted_signals = sorted(signals, key=lambda s: parse_ts(s.get("timestamp")))

        edges: List[Dict[str, Any]] = []
        seen_edges = set()

        for i in range(len(sorted_signals)):
            for j in range(i + 1, len(sorted_signals)):
                s1 = sorted_signals[i]
                s2 = sorted_signals[j]

                s1_id = s1.get("signal_id", "s1")
                s2_id = s2.get("signal_id", "s2")

                edge_key = (s1_id, s2_id)
                if edge_key in seen_edges:
                    continue

                relationship, score, desc = cls._classify_relationship(s1, s2)
                seen_edges.add(edge_key)

                edges.append({
                    "source_signal_id": s1_id,
                    "target_signal_id": s2_id,
                    "relationship": relationship,
                    "score": score,
                    "evidence": {
                        "description": desc,
                        "time_delta_seconds": abs((parse_ts(s2["timestamp"]) - parse_ts(s1["timestamp"])).total_seconds()),
                    },
                })

        # Assemble linear causal chain
        causal_chain: List[Dict[str, Any]] = []
        total_nodes = len(sorted_signals)

        for idx, s in enumerate(sorted_signals):
            sig_type = s.get("signal_type", "EVENT")
            service = s.get("service", "unknown")
            sig_id = s.get("signal_id", "unknown")
            metadata = s.get("metadata") or s.get("metadata_json") or {}
            metric_name = metadata.get("metric_name") or metadata.get("event_type") or sig_type

            if idx == 0:
                role = "possible_trigger" if sig_type == "DEPLOYMENT" else "primary_degradation"
            elif idx == total_nodes - 1:
                role = "downstream_effect"
            else:
                role = "propagation_step"

            causal_chain.append({
                "signal_id": sig_id,
                "signal_type": sig_type,
                "service": service,
                "role": role,
                "timestamp": parse_ts(s.get("timestamp")).isoformat(),
                "description": f"{sig_type} on {service} ({metric_name})",
            })

        return edges, causal_chain

    @classmethod
    def _classify_relationship(
        cls,
        s1: Dict[str, Any],
        s2: Dict[str, Any],
    ) -> Tuple[str, float, str]:
        """Classify relationship between earlier signal s1 and subsequent signal s2."""
        s1_type = s1.get("signal_type", "EVENT")
        s2_type = s2.get("signal_type", "EVENT")
        s1_srv = s1.get("service", "")
        s2_srv = s2.get("service", "")

        # 1. Deployment Trigger
        if s1_type == "DEPLOYMENT":
            return (
                "DEPLOYMENT_TRIGGER",
                0.85,
                f"Deployment on {s1_srv} preceded {s2_type} on {s2_srv}",
            )

        # 2. Metric anomaly to error on same service
        if s1_type == "ANOMALY" and s2_type == "EVENT" and s1_srv.lower() == s2_srv.lower():
            return (
                "METRIC_TO_ERROR",
                0.90,
                f"Metric anomaly on {s1_srv} cascaded into service error",
            )

        # 3. Cross-service propagation
        if s1_srv.lower() != s2_srv.lower():
            return (
                "SERVICE_PROPAGATION",
                0.75,
                f"Degradation propagated across service boundary from {s1_srv} to {s2_srv}",
            )

        # 4. Standard temporal precedence
        return (
            "TEMPORAL_PRECEDENCE",
            0.60,
            f"Precursor signal ({s1_type}) preceded downstream symptom ({s2_type})",
        )
