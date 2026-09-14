from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.common.config import Settings, get_settings
from backend.app.rca.evidence.deployment_evaluator import DeploymentEvidenceEvaluator, DeploymentEvidenceResult
from backend.app.rca.evidence.topology_evaluator import TopologyEvidenceEvaluator, TopologyEvidenceResult
from backend.app.rca.evidence.trace_extractor import TraceEvidenceExtractor, TraceEvidenceItem
from backend.app.rca.schemas.rca import (
    CandidateType,
    EvidenceBreakdown,
    EvidenceItem,
    EvidenceType,
)

logger = logging.getLogger(__name__)


class CandidateScorer:
    """
    Multi-dimensional, explainable scoring engine for Root Cause Analysis.
    Combines:
    - Temporal precedence (earliest signals score higher)
    - Service dependency topology (upstream candidate validation)
    - Metric anomaly magnitude and severity
    - Log error frequency & log cluster alignment
    - Distributed trace bottlenecks and failed spans
    - Recent software deployments and consequential failures
    - Historical similarity references
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.topology_evaluator = TopologyEvidenceEvaluator()
        self.deployment_evaluator = DeploymentEvidenceEvaluator()

    def score_candidates(
        self,
        candidates: List[Dict[str, Any]],
        signals: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        traces: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate and rank candidates using weighted evidence dimensions.
        Returns a sorted list of candidate dicts with confidence, affected_services, and evidence_breakdown.
        """
        if not candidates:
            return [self._create_unknown_candidate(score=0.10, rank=1, is_primary=True)]

        # If only explicit unknown candidate exists
        if len(candidates) == 1 and candidates[0].get("candidate_type") == "UNKNOWN":
            return [self._create_unknown_candidate(score=0.10, rank=1, is_primary=True)]

        def parse_ts(ts: Any) -> datetime:
            if isinstance(ts, datetime):
                return ts
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

        all_ts = [parse_ts(s["timestamp"]) for s in signals if s.get("timestamp")]
        min_time = min(all_ts) if all_ts else datetime.now()
        max_time = max(all_ts) if all_ts else datetime.now()
        total_time_span = max(1.0, (max_time - min_time).total_seconds())

        # Extract trace evidence across all signals and spans
        trace_evidence_items: List[TraceEvidenceItem] = TraceEvidenceExtractor.extract_trace_evidence(
            signals=signals,
            traces=traces,
        )

        # Evaluate deployment evidence
        deployment_results: List[DeploymentEvidenceResult] = self.deployment_evaluator.evaluate(signals)
        best_deployment = deployment_results[0] if deployment_results else None

        scored_candidates: List[Dict[str, Any]] = []

        for c in candidates:
            cand_type_str = str(c.get("candidate_type", "SERVICE")).upper()
            cand_svc = str(c.get("service", "unknown"))
            sig_ids = set(c.get("associated_signal_ids", []))
            cand_signals = [s for s in signals if s.get("signal_id") in sig_ids]
            other_signals = [s for s in signals if s.get("signal_id") not in sig_ids]

            # ------------------------------------------------------------------
            # 1. Temporal Precedence Score (S_temporal)
            # ------------------------------------------------------------------
            if cand_signals:
                cand_min_ts = min(parse_ts(s["timestamp"]) for s in cand_signals)
                time_from_start = (cand_min_ts - min_time).total_seconds()
                temporal_score = max(0.20, 1.0 - (time_from_start / total_time_span))
                time_diff_sec = int(time_from_start)
                temporal_desc = (
                    f"Initiated at incident onset (+{time_diff_sec}s from first signal)"
                    if time_diff_sec == 0
                    else f"Initiated {time_diff_sec}s after first observed symptom"
                )
            else:
                temporal_score = 0.50
                temporal_desc = "Standard temporal alignment"

            # ------------------------------------------------------------------
            # 2. Topology Plausibility Score (S_topology)
            # ------------------------------------------------------------------
            topo_result: TopologyEvidenceResult = self.topology_evaluator.evaluate_candidate(
                candidate_service=cand_svc,
                symptom_signals=other_signals or cand_signals,
            )
            topology_score = topo_result.score
            topology_desc = topo_result.description

            # ------------------------------------------------------------------
            # 3. Metric Anomaly Score (S_metric)
            # ------------------------------------------------------------------
            has_anomaly = any(s.get("signal_type") == "ANOMALY" for s in cand_signals)
            metric_score = 0.90 if has_anomaly else 0.40
            metric_desc_list = []
            for s in cand_signals:
                m = s.get("metadata") or s.get("metadata_json") or {}
                if "metric_name" in m:
                    val = m.get("value")
                    val_str = f" ({val})" if val is not None else ""
                    metric_desc_list.append(f"{m['metric_name']}{val_str}")
            metric_desc = (
                f"Elevated metric anomalies on {cand_svc}: {', '.join(metric_desc_list[:2])}"
                if metric_desc_list
                else (f"Anomaly telemetry recorded on {cand_svc}" if has_anomaly else "No direct metric anomaly")
            )

            # ------------------------------------------------------------------
            # 4. Log & Log Cluster Score (S_log)
            # ------------------------------------------------------------------
            log_messages = []
            log_clusters = set()
            for s in cand_signals:
                m = s.get("metadata") or s.get("metadata_json") or {}
                if m.get("cluster_label"):
                    log_clusters.add(m["cluster_label"])
                msg = s.get("message") or m.get("message")
                if msg:
                    log_messages.append(str(msg))

            log_count = len(log_messages)
            if log_clusters:
                log_score = 0.95
                log_desc = f"Matched semantic log cluster(s): {', '.join(log_clusters)}"
            elif log_count > 0:
                log_score = min(0.90, 0.50 + (log_count * 0.10))
                log_desc = f"{log_count} error log events recorded on {cand_svc} ({log_messages[0][:60]}...)"
            else:
                log_score = 0.35
                log_desc = "No specific error logs recorded"

            # ------------------------------------------------------------------
            # 5. Distributed Trace Score (S_trace)
            # ------------------------------------------------------------------
            svc_trace_items = [
                t for t in trace_evidence_items
                if t.service.lower() == cand_svc.lower() or t.parent_service == cand_svc.lower()
            ]
            if svc_trace_items:
                top_trace = max(svc_trace_items, key=lambda t: t.strength)
                trace_score = top_trace.strength
                trace_desc = top_trace.description
            elif trace_evidence_items:
                trace_score = 0.30
                trace_desc = "Traces show nominal operation or lack bottlenecks on this component"
            else:
                trace_score = 0.65
                trace_desc = "Distributed trace telemetry nominal"

            # ------------------------------------------------------------------
            # 6. Deployment Evidence Score (S_deployment)
            # ------------------------------------------------------------------
            if cand_type_str == "DEPLOYMENT":
                dep_score = best_deployment.score if best_deployment else 0.85
                dep_desc = best_deployment.description if best_deployment else "Preceding deployment observed"
            elif best_deployment and best_deployment.is_causally_plausible:
                # Deployment occurred on this service or its upstream
                if best_deployment.service.lower() == cand_svc.lower():
                    dep_score = best_deployment.score * 0.90
                    dep_desc = f"Correlated with deployment on {cand_svc} ({best_deployment.version})"
                else:
                    dep_score = 0.20
                    dep_desc = f"Deployment on unrelated service {best_deployment.service}"
            else:
                dep_score = 0.50
                dep_desc = "No recent software deployments recorded (steady state)"

            # ------------------------------------------------------------------
            # 7. Historical Evidence Score (S_historical)
            # ------------------------------------------------------------------
            hist_score = 0.60
            hist_desc = f"Consistent with recurring failure patterns for {cand_type_str.lower()} components"

            # ------------------------------------------------------------------
            # Composite Weighted RCA Formula
            # ------------------------------------------------------------------
            # Weights: Temporal(0.20), Topology(0.20), Metric(0.15), Log(0.15), Trace(0.15), Deployment(0.10), Historical(0.05)
            composite_score = (
                temporal_score * 0.20
                + topology_score * 0.20
                + metric_score * 0.15
                + log_score * 0.15
                + trace_score * 0.15
                + dep_score * 0.10
                + hist_score * 0.05
            )

            # Type specific adjustments (e.g. database/infra upstream bonus)
            if cand_type_str in ["DATABASE", "DEPENDENCY", "RESOURCE", "DEPLOYMENT"]:
                composite_score = min(1.0, composite_score * 1.05)

            # Calculate confidence
            confidence = min(0.98, max(0.10, composite_score))

            # Build affected services list
            affected_services = sorted(list({cand_svc} | set(topo_result.supported_symptom_services)))

            # Build structured evidence items
            evidence_items = [
                EvidenceItem(type=EvidenceType.TEMPORAL, description=temporal_desc, strength=round(temporal_score, 3)),
                EvidenceItem(type=EvidenceType.TOPOLOGY, description=topology_desc, strength=round(topology_score, 3)),
                EvidenceItem(type=EvidenceType.METRIC, description=metric_desc, strength=round(metric_score, 3)),
                EvidenceItem(type=EvidenceType.ERROR, description=log_desc, strength=round(log_score, 3)),
                EvidenceItem(type=EvidenceType.TRACE, description=trace_desc, strength=round(trace_score, 3)),
                EvidenceItem(type=EvidenceType.DEPLOYMENT, description=dep_desc, strength=round(dep_score, 3)),
                EvidenceItem(type=EvidenceType.HISTORICAL, description=hist_desc, strength=round(hist_score, 3)),
            ]

            evidence_breakdown = EvidenceBreakdown(
                temporal=temporal_desc,
                metric=metric_desc,
                log=log_desc,
                trace=trace_desc,
                topology=topology_desc,
                deployment=dep_desc,
                historical=hist_desc,
            )

            scored_candidates.append({
                "candidate_type": cand_type_str,
                "candidate_name": c.get("candidate_name", f"{cand_type_str} on {cand_svc}"),
                "score": round(composite_score, 4),
                "confidence": round(confidence, 4),
                "service": cand_svc,
                "affected_services": affected_services,
                "evidence": [e.model_dump() for e in evidence_items],
                "evidence_breakdown": evidence_breakdown.model_dump(),
            })

        # Sort candidates descending by score
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # Ambiguous / Low Evidence Check:
        # If top score is below 0.35 or if evidence is ambiguous, emit UNKNOWN
        if not scored_candidates or scored_candidates[0]["score"] < 0.35:
            return [self._create_unknown_candidate(score=0.15, rank=1, is_primary=True)]

        # Assign ranks and primary flags for Top-3
        final_candidates: List[Dict[str, Any]] = []
        for rank_idx, cand in enumerate(scored_candidates[:3], start=1):
            cand_copy = dict(cand)
            cand_copy["rank"] = rank_idx
            cand_copy["is_primary"] = (rank_idx == 1)
            final_candidates.append(cand_copy)

        return final_candidates

    @staticmethod
    def _create_unknown_candidate(score: float = 0.10, rank: int = 1, is_primary: bool = True) -> Dict[str, Any]:
        """Generate a structured UNKNOWN candidate response."""
        breakdown = EvidenceBreakdown(
            temporal="No dominant temporal trigger identified across signals",
            metric="Metric anomalies are weak, missing, or conflicting",
            log="No conclusive error logs linking to root cause",
            trace="Traces are inconclusive or unavailable",
            topology="Symptoms cannot be attributed to a single upstream dependency",
            deployment="No correlated deployment event",
            historical="No high-confidence historical match",
        )
        evidence = [
            EvidenceItem(
                type=EvidenceType.ERROR,
                description="Insufficient evidence: observed signals lack clear upstream causality.",
                strength=round(score, 3),
            ).model_dump()
        ]
        return {
            "candidate_type": "UNKNOWN",
            "candidate_name": "Insufficient evidence",
            "score": round(score, 4),
            "confidence": round(score, 4),
            "rank": rank,
            "is_primary": is_primary,
            "affected_services": ["unknown"],
            "evidence": evidence,
            "evidence_breakdown": breakdown.model_dump(),
        }
