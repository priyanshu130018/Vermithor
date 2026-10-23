from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from backend.app.topology.service_graph import ServiceTopologyGraph, get_service_topology_graph

logger = logging.getLogger(__name__)


class DeploymentEvidenceResult:
    """Evaluated deployment evidence metrics and reasoning."""

    def __init__(
        self,
        deployment_signal_id: str,
        service: str,
        version: str,
        timestamp: datetime,
        score: float,
        time_delta_seconds: float,
        is_causally_plausible: bool,
        description: str,
        post_deploy_anomalies: List[str],
    ):
        self.deployment_signal_id = deployment_signal_id
        self.service = service
        self.version = version
        self.timestamp = timestamp
        self.score = score
        self.time_delta_seconds = time_delta_seconds
        self.is_causally_plausible = is_causally_plausible
        self.description = description
        self.post_deploy_anomalies = post_deploy_anomalies

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployment_signal_id": self.deployment_signal_id,
            "service": self.service,
            "version": self.version,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "score": round(self.score, 4),
            "time_delta_seconds": round(self.time_delta_seconds, 1),
            "is_causally_plausible": self.is_causally_plausible,
            "description": self.description,
            "post_deploy_anomalies": self.post_deploy_anomalies,
        }


class DeploymentEvidenceEvaluator:
    """
    Evaluates whether recent software deployments are causally related to operational failures.
    Factors:
    1. Temporal proximity: Did the deployment occur 0-10 minutes prior to symptom onset?
    2. Service scope: Is the deployed service directly failing or an upstream dependency?
    3. Consequential degradation: Did errors, latency, or anomalies spike immediately post-deploy?
    """

    def __init__(self, topology_graph: Optional[ServiceTopologyGraph] = None):
        self.topology = topology_graph or get_service_topology_graph()

    def evaluate(
        self,
        signals: List[Dict[str, Any]],
        candidate_service: Optional[str] = None,
    ) -> List[DeploymentEvidenceResult]:
        """
        Scan signals for deployment events and evaluate causal strength against symptom signals.
        """
        def parse_ts(ts: Any) -> Optional[datetime]:
            if ts is None:
                return None
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts
            try:
                d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if d.tzinfo is None:
                    return d.replace(tzinfo=timezone.utc)
                return d
            except (ValueError, TypeError):
                return None

        deployment_signals = [s for s in signals if s.get("signal_type") == "DEPLOYMENT"]
        if not deployment_signals:
            return []

        non_deployment_signals = [s for s in signals if s.get("signal_type") != "DEPLOYMENT"]
        results: List[DeploymentEvidenceResult] = []

        for dep in deployment_signals:
            dep_id = dep.get("signal_id", "unknown")
            dep_svc = dep.get("service", "unknown")
            dep_ts = parse_ts(dep.get("timestamp"))
            dep_meta = dep.get("metadata") or dep.get("metadata_json") or {}
            version = dep_meta.get("version") or dep_meta.get("release") or "latest"

            if dep_ts is None:
                results.append(
                    DeploymentEvidenceResult(
                        deployment_signal_id=dep_id,
                        service=dep_svc,
                        version=version,
                        timestamp=None,
                        score=0.20,
                        time_delta_seconds=-1.0,
                        is_causally_plausible=False,
                        description=f"Deployment '{version}' on {dep_svc} has missing or unparseable timestamp; temporal correlation inconclusive.",
                        post_deploy_anomalies=[],
                    )
                )
                continue

            # Check post-deployment symptom signals
            post_deploy_signals = []
            for s in non_deployment_signals:
                s_ts = parse_ts(s.get("timestamp"))
                if s_ts is None:
                    continue
                delta_sec = (s_ts - dep_ts).total_seconds()
                if 0 <= delta_sec <= 900:  # within 15 mins after deployment
                    post_deploy_signals.append((s, delta_sec))

            if not post_deploy_signals:
                # Deployment occurred after symptoms or outside correlation window
                results.append(
                    DeploymentEvidenceResult(
                        deployment_signal_id=dep_id,
                        service=dep_svc,
                        version=version,
                        timestamp=dep_ts,
                        score=0.10,
                        time_delta_seconds=-1.0,
                        is_causally_plausible=False,
                        description=f"Deployment '{version}' on {dep_svc} occurred outside failure window.",
                        post_deploy_anomalies=[],
                    )
                )
                continue

            # Earliest symptom after deployment
            earliest_delta = min(item[1] for item in post_deploy_signals)
            mins_before = max(0, int(earliest_delta / 60))

            # 1. Temporal Score
            if earliest_delta <= 120:  # within 2 mins
                time_score = 1.0
            elif earliest_delta <= 360:  # within 6 mins
                time_score = 0.85
            elif earliest_delta <= 600:  # within 10 mins
                time_score = 0.60
            else:
                time_score = 0.30

            # 2. Service Plausibility Score
            # Target matching candidate service or dependent services
            svc_score = 0.40
            affected_svcs = {s.get("service", "").lower() for s, _ in post_deploy_signals if s.get("service")}
            if candidate_service and dep_svc.lower() == candidate_service.lower():
                svc_score = 1.0
            elif dep_svc.lower() in affected_svcs:
                svc_score = 0.95
            elif any(self.topology.is_dependency(dep_svc, aff_svc) for aff_svc in affected_svcs):
                svc_score = 0.80

            # 3. Degradation Severity Score
            has_critical = any(
                str(s.get("severity", "")).upper() in ["CRITICAL", "HIGH", "ERROR"]
                for s, _ in post_deploy_signals
            )
            has_anomaly = any(s.get("signal_type") == "ANOMALY" for s, _ in post_deploy_signals)
            deg_score = 1.0 if (has_critical and has_anomaly) else (0.75 if (has_critical or has_anomaly) else 0.50)

            # Causally plausible only if accompanied by actual errors or anomalies within the window
            is_causal = (has_critical or has_anomaly) and (earliest_delta <= 900)

            # Combined weighted score
            deployment_score = (time_score * 0.45) + (svc_score * 0.35) + (deg_score * 0.20)
            if not is_causal:
                deployment_score = min(0.35, deployment_score * 0.40)
            else:
                deployment_score = min(1.0, max(0.05, deployment_score))

            anomaly_descs = [
                f"{s.get('signal_type')}:{s.get('service')} (+{int(delta)}s)"
                for s, delta in post_deploy_signals[:3]
            ]

            desc = (
                f"{version} deployed on {dep_svc} {mins_before}m prior to degradation; "
                f"followed by {len(post_deploy_signals)} failure signals on {', '.join(sorted(affected_svcs)[:3])}."
                if is_causal else f"Routine deployment '{version}' on {dep_svc} lacking consequential failure spikes."
            )

            results.append(
                DeploymentEvidenceResult(
                    deployment_signal_id=dep_id,
                    service=dep_svc,
                    version=version,
                    timestamp=dep_ts,
                    score=deployment_score,
                    time_delta_seconds=earliest_delta,
                    is_causally_plausible=is_causal,
                    description=desc,
                    post_deploy_anomalies=anomaly_descs if is_causal else [],
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results
