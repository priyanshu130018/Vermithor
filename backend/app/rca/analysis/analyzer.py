from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional

from backend.app.common.config import Settings, get_settings
from backend.app.common.telemetry import (
    RCA_ANALYSIS_DURATION_SECONDS,
    RCA_ANALYSIS_TOTAL,
    RCA_CANDIDATE_COUNT,
    RCA_UNKNOWN_TOTAL,
)
from backend.app.rca.analysis.candidate_generator import CandidateGenerator
from backend.app.rca.analysis.causal_graph import CausalGraphBuilder
from backend.app.rca.analysis.scoring import CandidateScorer

logger = logging.getLogger(__name__)


class RCAAnalyzer:
    """Orchestrates candidate generation, graph topology analysis, trace evidence, and root cause ranking."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.candidate_generator = CandidateGenerator()
        self.graph_builder = CausalGraphBuilder()
        self.scorer = CandidateScorer(self.settings)

    def analyze(self, group_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute full Root Cause Analysis workflow on a correlation group.

        Returns:
            Dict containing primary_root_cause, primary_confidence, candidates, edges, and causal_chain.
        """
        start_perf = time.perf_counter()
        signals: List[Dict[str, Any]] = group_data.get("signals", [])
        traces: Optional[List[Dict[str, Any]]] = group_data.get("traces")
        group_key = group_data.get("group_key", "unknown")

        logger.info("RCA analysis started for group '%s' with %d signals", group_key, len(signals))

        try:
            # 1. Candidate generation
            candidates = self.candidate_generator.generate_candidates(signals)
            logger.info("Generated %d root cause candidates for group '%s'", len(candidates), group_key)

            # 2. Causal graph construction
            edges, causal_chain = self.graph_builder.build_graph(signals)
            logger.info("Built causal graph with %d edges and %d chain nodes", len(edges), len(causal_chain))

            # 3. Multi-dimensional Candidate scoring and ranking (Trace + Deployment + Topology Aware)
            ranked_candidates = self.scorer.score_candidates(
                candidates=candidates,
                signals=signals,
                edges=edges,
                traces=traces,
            )

            # 4. Determine primary root cause and confidence
            if ranked_candidates:
                top = ranked_candidates[0]
                if top.get("candidate_type") == "UNKNOWN":
                    primary_root_cause = "Insufficient evidence"
                    primary_confidence = top.get("confidence", 0.10)
                    RCA_UNKNOWN_TOTAL.inc()
                else:
                    primary_root_cause = top.get("candidate_name", "Unknown Root Cause")
                    primary_confidence = top.get("confidence", 0.50)
            else:
                primary_root_cause = "Insufficient evidence"
                primary_confidence = 0.0
                RCA_UNKNOWN_TOTAL.inc()

            duration_sec = time.perf_counter() - start_perf
            RCA_ANALYSIS_TOTAL.labels(status="success").inc()
            RCA_ANALYSIS_DURATION_SECONDS.labels(status="success").observe(duration_sec)
            RCA_CANDIDATE_COUNT.observe(len(ranked_candidates))

            logger.info(
                "RCA completed for group '%s' in %.2fms: primary='%s', confidence=%.2f, candidates=%d",
                group_key,
                duration_sec * 1000.0,
                primary_root_cause,
                primary_confidence,
                len(ranked_candidates),
            )

            return {
                "primary_root_cause": primary_root_cause,
                "primary_confidence": primary_confidence,
                "candidates": ranked_candidates,
                "edges": edges,
                "causal_chain": causal_chain,
            }
        except Exception as exc:
            duration_sec = time.perf_counter() - start_perf
            RCA_ANALYSIS_TOTAL.labels(status="error").inc()
            RCA_ANALYSIS_DURATION_SECONDS.labels(status="error").observe(duration_sec)
            logger.error("RCA analysis failed for group '%s': %s", group_key, exc)
            raise
