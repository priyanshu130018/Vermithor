import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.incidents.services.incident_service import IncidentService
from backend.app.topology.service_graph import ServiceTopologyGraph

logger = logging.getLogger(__name__)


def infer_service_from_incident(title: str, description: Optional[str] = None) -> str:
    """Infer primary service from incident metadata if not explicitly provided."""
    import re
    text = f"{title or ''} {description or ''}".lower()

    # Check for explicit bracket tag like [payment-api] or [booking-api]
    match = re.search(r"\[([a-z0-9_-]+)\]", text)
    if match:
        tag = match.group(1).strip()
        if tag and tag not in ("incident", "sev1", "sev2", "sev3", "critical", "major", "production", "staging"):
            return tag

    if "payment" in text:
        return "payment-api"
    if "booking" in text:
        return "booking-api"
    if "catalog" in text:
        return "catalog-api"
    if "auth" in text:
        return "auth-service"
    if "cache" in text or "redis" in text:
        return "cache-service"
    if "database" in text or "postgres" in text:
        return "postgres"
    if "checkout" in text:
        return "checkout-api"
    if "worker" in text or "queue" in text or "celery" in text:
        return "worker"
    return "vermithor-backend"


def initialize_investigation_node(state: InvestigationState, db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Step 1: Validate incident identifier, establish bounded investigation time window,
    and resolve service topology context.
    """
    incident_key = state.get("incident_key")
    if not incident_key:
        raise ValueError("Investigation requires a non-empty incident_key")

    logger.info("Initializing LangGraph investigation for incident: %s", incident_key)

    incident = None
    if db is not None:
        incident = IncidentService.get_incident_by_key(db, incident_key)

    title = incident.title if incident else f"Incident {incident_key}"
    description = incident.description if incident else ""
    environment = incident.environment if incident else state.get("environment", "production")
    severity = incident.severity if incident else state.get("severity", "SEV1")
    incident_id = str(incident.id) if incident else None

    target_svc = state.get("target_service")
    if not target_svc or target_svc in ("unknown", "vermithor-backend"):
        if db is not None and incident_key:
            try:
                from sqlalchemy import select
                from backend.app.ingestion.db.models import Event
                evt_svc = db.execute(
                    select(Event.service).where(Event.event_id.like(f"%{incident_key}%")).limit(1)
                ).scalar_one_or_none()
                if evt_svc and evt_svc != "unknown":
                    target_svc = evt_svc
            except Exception as exc:
                logger.debug("Could not resolve service from incident events: %s", exc)

    if not target_svc or target_svc in ("unknown", "vermithor-backend"):
        target_svc = infer_service_from_incident(title, description)

    lookback = state.get("lookback_minutes", 30)

    now = datetime.now(timezone.utc)
    if incident and incident.started_at:
        inc_start = incident.started_at
        if inc_start.tzinfo is None:
            inc_start = inc_start.replace(tzinfo=timezone.utc)
        win_start = inc_start - timedelta(minutes=lookback)
        win_end = (incident.ended_at.replace(tzinfo=timezone.utc) if incident.ended_at else inc_start + timedelta(minutes=20))
    else:
        win_start = now - timedelta(minutes=lookback)
        win_end = now

    # Service Topology Resolution
    topology = ServiceTopologyGraph()
    deps = list(topology.get_all_dependencies(target_svc))
    dependents = list(topology.get_all_dependents(target_svc))

    return {
        "incident_key": incident_key,
        "incident_id": incident_id,
        "incident_title": title,
        "target_service": target_svc,
        "environment": environment,
        "severity": severity,
        "lookback_minutes": lookback,
        "window_start": win_start.isoformat(),
        "window_end": win_end.isoformat(),
        "topology_dependencies": deps,
        "topology_dependents": dependents,
        "status": "INVESTIGATING",
        "query_iteration": state.get("query_iteration", 0),
        "max_query_iterations": state.get("max_query_iterations", 2),
        "needs_additional_query": False,
        "additional_query_targets": [],
        "errors": state.get("errors", []),
        "collected_evidence": state.get("collected_evidence", []),
    }
