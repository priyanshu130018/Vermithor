from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.anomaly.db.models import MetricObservation
from backend.app.ingestion.db.models import Event
from backend.app.incidents.services.incident_service import IncidentService
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService

logger = logging.getLogger(__name__)


def gather_evidence_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    telemetry_service: Optional[TelemetryEvidenceService] = None,
) -> Dict[str, Any]:
    """
    Step 2: Gather metrics, traces, events, deployments, and topology evidence
    using Vermithor's existing telemetry and database interfaces.
    """
    target_svc = state.get("target_service", "unknown")
    environment = state.get("environment", "production")
    incident_key = state.get("incident_key", "UNKNOWN")
    lookback = state.get("lookback_minutes", 30)

    evidence_items: List[Dict[str, Any]] = list(state.get("collected_evidence", []))
    errors: List[str] = list(state.get("errors", []))
    raw_metrics: Dict[str, Any] = dict(state.get("raw_metrics", {}))
    raw_traces: List[Dict[str, Any]] = list(state.get("raw_traces", []))
    raw_events: List[Dict[str, Any]] = list(state.get("raw_events", []))
    deployments: List[Dict[str, Any]] = list(state.get("deployments", []))

    # Track seen IDs to prevent duplicate evidence
    seen_source_ids = {e.get("source_id") for e in evidence_items}

    # 1. Live Telemetry from Prometheus & Jaeger (via TelemetryEvidenceService)
    telem = telemetry_service or TelemetryEvidenceService()
    try:
        snapshot = telem.get_telemetry_snapshot(service=target_svc, lookback_minutes=lookback)
        prom_metrics = snapshot.get("sources", {}).get("prometheus", {}).get("metrics", {})
        jaeger_traces = snapshot.get("sources", {}).get("jaeger", {}).get("summaries", [])

        raw_metrics.update(prom_metrics)
        raw_traces.extend(jaeger_traces)

        # Ingest metrics as evidence items
        for name, data in prom_metrics.items():
            val = data.get("value")
            if val is not None:
                src_id = f"prom-{target_svc}-{name}"
                if src_id not in seen_source_ids:
                    seen_source_ids.add(src_id)
                    evidence_items.append({
                        "evidence_id": f"EV-PROM-{len(evidence_items) + 1}",
                        "source_type": "PROMETHEUS",
                        "source_id": src_id,
                        "service": target_svc,
                        "timestamp": snapshot.get("collected_at"),
                        "claim": f"Prometheus metric {name} = {val:.4f}",
                        "data": {"metric_name": name, "value": float(val), "query": data.get("query", "")},
                    })

        # Ingest traces as evidence items
        for tr in jaeger_traces:
            t_id = tr.get("trace_id", "")
            if t_id and t_id not in seen_source_ids:
                seen_source_ids.add(t_id)
                dur = tr.get("duration_ms", 0.0)
                err = tr.get("has_error", False)
                claim_txt = f"Jaeger trace {t_id[:16]} root={tr.get('root_operation')} dur={dur}ms error={err}"
                evidence_items.append({
                    "evidence_id": f"EV-TRACE-{len(evidence_items) + 1}",
                    "source_type": "JAEGER",
                    "source_id": t_id,
                    "service": tr.get("root_service") or target_svc,
                    "timestamp": tr.get("start_time"),
                    "claim": claim_txt,
                    "data": tr,
                })

    except Exception as exc:
        msg = f"Telemetry snapshot degraded for service '{target_svc}': {exc}"
        logger.warning(msg)
        errors.append(msg)

    # 2. Database Evidence: Metric Observations & Canonical Events (fallback if live snapshot returned empty)
    if db is not None:
        try:
            # Query observations for this service if no live metrics collected
            if not evidence_items:
                db_obs = list(
                    db.execute(
                        select(MetricObservation)
                        .where(MetricObservation.service == target_svc)
                        .order_by(MetricObservation.timestamp.desc())
                        .limit(50)
                    ).scalars().all()
                )
                for obs in db_obs:
                    if obs.observation_id not in seen_source_ids:
                        seen_source_ids.add(obs.observation_id)
                        evidence_items.append({
                            "evidence_id": f"EV-OBS-{len(evidence_items) + 1}",
                            "source_type": "METRIC_OBSERVATION",
                            "source_id": obs.observation_id,
                            "service": obs.service,
                            "timestamp": obs.timestamp.isoformat() if obs.timestamp else now.isoformat(),
                            "claim": f"Metric {obs.metric_name} observed at {obs.metric_value} {obs.unit}",
                            "data": {
                                "observation_id": obs.observation_id,
                                "metric_name": obs.metric_name,
                                "value": obs.metric_value,
                                "unit": obs.unit,
                            },
                        })

            # Query database events for this service if no live events collected
            if not raw_events:
                db_events = list(
                    db.execute(
                        select(Event)
                        .where(Event.service == target_svc)
                        .order_by(Event.timestamp.desc())
                        .limit(50)
                    ).scalars().all()
                )
                for evt in db_events:
                    if evt.event_id not in seen_source_ids:
                        seen_source_ids.add(evt.event_id)
                        raw_events.append({
                            "event_id": evt.event_id,
                            "event_type": evt.event_type,
                            "severity": evt.severity,
                            "message": evt.message,
                            "trace_id": evt.trace_id,
                            "timestamp": evt.timestamp.isoformat() if evt.timestamp else now.isoformat(),
                        })

                    is_deploy = evt.event_type == "DEPLOYMENT" or "deploy" in (evt.message or "").lower()
                    if is_deploy:
                        deployments.append({
                            "event_id": evt.event_id,
                            "service": evt.service,
                            "message": evt.message,
                            "timestamp": evt.timestamp.isoformat() if evt.timestamp else None,
                            "metadata": evt.metadata_json or {},
                        })

                    evidence_items.append({
                        "evidence_id": f"EV-EVT-{len(evidence_items) + 1}",
                        "source_type": "DEPLOYMENT" if is_deploy else "EVENT",
                        "source_id": evt.event_id,
                        "service": evt.service,
                        "timestamp": evt.timestamp.isoformat() if evt.timestamp else None,
                        "claim": f"[{evt.severity}] {evt.message}",
                        "data": {
                            "event_type": evt.event_type,
                            "severity": evt.severity,
                            "message": evt.message,
                            "trace_id": evt.trace_id,
                        },
                    })

            # Check for incident-associated events
            assoc_events = IncidentService.get_incident_events(db, incident_key) or []
            for a_evt in assoc_events:
                if a_evt.event_id not in seen_source_ids:
                    seen_source_ids.add(a_evt.event_id)
                    evidence_items.append({
                        "evidence_id": f"EV-INC-ASSOC-{len(evidence_items) + 1}",
                        "source_type": "INCIDENT_EVENT",
                        "source_id": a_evt.event_id,
                        "service": target_svc,
                        "timestamp": a_evt.created_at.isoformat() if a_evt.created_at else None,
                        "claim": f"Incident association: relation={a_evt.relation_type}, score={a_evt.score:.2f}",
                        "data": {"relation_type": a_evt.relation_type, "score": a_evt.score},
                    })

        except Exception as exc:
            msg = f"Database evidence query warning: {exc}"
            logger.warning(msg)
            errors.append(msg)

    # 3. Topology Evidence
    for dep in state.get("topology_dependencies", []):
        topo_id = f"topo-dep-{dep}"
        if topo_id not in seen_source_ids:
            seen_source_ids.add(topo_id)
            evidence_items.append({
                "evidence_id": f"EV-TOPO-{len(evidence_items) + 1}",
                "source_type": "TOPOLOGY",
                "source_id": topo_id,
                "service": target_svc,
                "timestamp": None,
                "claim": f"Architecture dependency: {target_svc} depends on downstream service '{dep}'",
                "data": {"dependent": target_svc, "dependency": dep},
            })

    logger.info(
        "Evidence gathering completed for %s: collected %d evidence items, %d errors",
        target_svc,
        len(evidence_items),
        len(errors),
    )

    return {
        "collected_evidence": evidence_items,
        "raw_metrics": raw_metrics,
        "raw_traces": raw_traces,
        "raw_events": raw_events,
        "deployments": deployments,
        "errors": errors,
    }
