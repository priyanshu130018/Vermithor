import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.anomaly.db.models import AnomalyResult, MetricObservation
from backend.app.anomaly.services.anomaly_service import AnomalyService

logger = logging.getLogger(__name__)


def evaluate_anomalies_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    anomaly_service: Optional[AnomalyService] = None,
) -> Dict[str, Any]:
    """
    Step 3: Evaluate anomalies by reusing Vermithor's existing AnomalyService
    and persisted AnomalyResult records.
    """
    target_svc = state.get("target_service", "unknown")
    collected_evidence: List[Dict[str, Any]] = list(state.get("collected_evidence", []))
    anomalies: List[Dict[str, Any]] = list(state.get("anomalies", []))
    seen_anomaly_obs = {a.get("observation_id") for a in anomalies}
    seen_evidence_ids = {e.get("source_id") for e in collected_evidence}

    service = anomaly_service or AnomalyService()

    if db is not None:
        try:
            # 1. Fetch all existing persisted anomaly results for target service
            obs_ids = [
                e["source_id"]
                for e in collected_evidence
                if e.get("source_type") == "METRIC_OBSERVATION"
            ]

            for obs_id in obs_ids:
                existing_anoms = AnomalyService.get_anomalies_for_observation(db, obs_id)

                if not existing_anoms:
                    # Run existing detector on unanalyzed observation
                    obs_record = db.execute(
                        select(MetricObservation).where(MetricObservation.observation_id == obs_id)
                    ).scalar_one_or_none()
                    if obs_record:
                        existing_anoms = service.analyze_observation(db, obs_record)

                for anom in existing_anoms:
                    if anom.is_anomaly and obs_id not in seen_anomaly_obs:
                        seen_anomaly_obs.add(obs_id)
                        anom_dict = {
                            "observation_id": anom.observation_id,
                            "detector": anom.detector,
                            "severity": anom.severity,
                            "score": anom.anomaly_score,
                            "reason": anom.reason,
                            "deviation": anom.deviation,
                            "expected_value": anom.expected_value,
                        }
                        anomalies.append(anom_dict)

                        src_id = f"anom-{obs_id}"
                        if src_id not in seen_evidence_ids:
                            seen_evidence_ids.add(src_id)
                            collected_evidence.append({
                                "evidence_id": f"EV-ANOM-{len(collected_evidence) + 1}",
                                "source_type": "ANOMALY",
                                "source_id": src_id,
                                "service": target_svc,
                                "timestamp": None,
                                "claim": f"Anomaly detected by {anom.detector} (score={anom.anomaly_score:.2f}, sev={anom.severity}): {anom.reason}",
                                "data": anom_dict,
                            })

        except Exception as exc:
            logger.warning("Error evaluating anomalies via AnomalyService: %s", exc)

    logger.info("Anomaly evaluation completed: %d confirmed anomalies identified", len(anomalies))

    return {
        "anomalies": anomalies,
        "collected_evidence": collected_evidence,
    }
