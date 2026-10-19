import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.anomaly.db.models import MetricObservation
from backend.app.ingestion.db.models import Event
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService

logger = logging.getLogger(__name__)


def gather_additional_evidence_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    telemetry_service: Optional[TelemetryEvidenceService] = None,
) -> Dict[str, Any]:
    """
    Step 8b: Execute bounded additional queries for unqueried downstream dependencies
    identified during completeness evaluation.
    """
    targets = state.get("additional_query_targets", [])
    lookback = state.get("lookback_minutes", 30)
    query_iter = state.get("query_iteration", 0) + 1
    evidence_items: List[Dict[str, Any]] = list(state.get("collected_evidence", []))
    errors: List[str] = list(state.get("errors", []))
    seen_ids = {e.get("source_id") for e in evidence_items}

    telem = telemetry_service or TelemetryEvidenceService()

    logger.info("Executing bounded additional query iteration %d for targets: %s", query_iter, targets)

    for target in targets:
        # 1. Query Prometheus / Jaeger for downstream target
        try:
            snapshot = telem.get_telemetry_snapshot(service=target, lookback_minutes=lookback)
            prom_metrics = snapshot.get("sources", {}).get("prometheus", {}).get("metrics", {})
            for name, data in prom_metrics.items():
                val = data.get("value")
                if val is not None:
                    src_id = f"downstream-prom-{target}-{name}"
                    if src_id not in seen_ids:
                        seen_ids.add(src_id)
                        evidence_items.append({
                            "evidence_id": f"EV-DOWNSTREAM-PROM-{len(evidence_items) + 1}",
                            "source_type": "PROMETHEUS",
                            "source_id": src_id,
                            "service": target,
                            "timestamp": snapshot.get("collected_at"),
                            "claim": f"Downstream dependency {target} metric {name} = {val:.4f}",
                            "data": {"metric_name": name, "value": float(val)},
                        })
        except Exception as exc:
            msg = f"Additional telemetry query to '{target}' unavailable: {exc}"
            logger.debug(msg)
            errors.append(msg)

        # 2. Query Database observations / events for downstream target
        if db is not None:
            try:
                obs_list = list(
                    db.execute(
                        select(MetricObservation)
                        .where(MetricObservation.service == target)
                        .order_by(MetricObservation.timestamp.desc())
                        .limit(20)
                    ).scalars().all()
                )
                for obs in obs_list:
                    if obs.observation_id not in seen_ids:
                        seen_ids.add(obs.observation_id)
                        evidence_items.append({
                            "evidence_id": f"EV-DOWNSTREAM-OBS-{len(evidence_items) + 1}",
                            "source_type": "METRIC_OBSERVATION",
                            "source_id": obs.observation_id,
                            "service": target,
                            "timestamp": obs.timestamp.isoformat() if obs.timestamp else None,
                            "claim": f"Downstream {target} observation: {obs.metric_name} = {obs.metric_value} {obs.unit}",
                            "data": {
                                "metric_name": obs.metric_name,
                                "value": obs.metric_value,
                                "unit": obs.unit,
                            },
                        })

                evt_list = list(
                    db.execute(
                        select(Event)
                        .where(Event.service == target)
                        .order_by(Event.timestamp.desc())
                        .limit(20)
                    ).scalars().all()
                )
                for evt in evt_list:
                    if evt.event_id not in seen_ids:
                        seen_ids.add(evt.event_id)
                        evidence_items.append({
                            "evidence_id": f"EV-DOWNSTREAM-EVT-{len(evidence_items) + 1}",
                            "source_type": "EVENT",
                            "source_id": evt.event_id,
                            "service": target,
                            "timestamp": evt.timestamp.isoformat() if evt.timestamp else None,
                            "claim": f"Downstream {target} [{evt.severity}]: {evt.message}",
                            "data": {"event_type": evt.event_type, "severity": evt.severity},
                        })

            except Exception as exc:
                msg = f"Additional database query to '{target}' error: {exc}"
                logger.debug(msg)
                errors.append(msg)

    return {
        "collected_evidence": evidence_items,
        "query_iteration": query_iter,
        "needs_additional_query": False,
        "additional_query_targets": [],
        "errors": errors,
    }
