from datetime import datetime
import logging
from typing import Any, Dict, Optional
import httpx

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.incidents.schemas.incident import (
    IncidentCreate,
    IncidentEventCreate,
    IncidentRelationType,
    IncidentSeverity,
)
from backend.app.incidents.services.incident_service import IncidentService

logger = logging.getLogger(__name__)


class IncidentServiceClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 5.0):
        settings = get_settings()
        self.is_custom_url = base_url is not None
        self.base_url = (base_url or settings.INCIDENT_SERVICE_URL).rstrip("/")
        self.timeout = timeout

    def create_incident(
        self,
        title: str,
        description: str,
        severity: str,
        environment: str,
        started_at: datetime,
        confidence: float,
    ) -> Optional[str]:
        """Create a new incident entity."""
        sev_map = {
            "CRITICAL": "SEV1",
            "SEV1": "SEV1",
            "HIGH": "SEV2",
            "SEV2": "SEV2",
            "ERROR": "SEV2",
            "WARNING": "SEV3",
            "SEV3": "SEV3",
            "MEDIUM": "SEV3",
            "LOW": "SEV4",
            "SEV4": "SEV4",
            "INFO": "SEV4",
            "NONE": "SEV4",
        }
        incident_severity = sev_map.get(severity.upper(), "SEV3")

        # 1. HTTP call (supports mocked tests and decoupled microservices)
        url = f"{self.base_url}/api/v1/incidents"
        payload = {
            "title": title[:255],
            "description": description,
            "severity": incident_severity,
            "environment": environment,
            "started_at": started_at.isoformat() if hasattr(started_at, "isoformat") else started_at,
            "confidence": round(confidence, 2),
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                if response.status_code in (200, 201):
                    return response.json().get("incident_key")
        except Exception as exc:
            logger.debug("HTTP call for create_incident failed: %s", exc)
            if self.is_custom_url:
                return None

        # 2. In-process direct database lookup fallback
        try:
            db = SessionLocal()
            try:
                incident_in = IncidentCreate(
                    title=title[:255],
                    description=description,
                    severity=IncidentSeverity(incident_severity),
                    environment=environment,
                    started_at=started_at,
                    confidence=round(confidence, 2),
                )
                incident = IncidentService.create_incident(db, incident_in)
                return incident.incident_key
            finally:
                db.close()
        except Exception:
            pass
        return None

    def attach_event_evidence(
        self,
        incident_key: str,
        event_id: str,
        relation_type: str = "PRIMARY_SIGNAL",
        score: Optional[float] = None,
    ) -> bool:
        """Attach an external event ID as evidence to an existing incident."""
        # 1. HTTP call (supports mocked tests and decoupled microservices)
        url = f"{self.base_url}/api/v1/incidents/{incident_key}/events"
        payload = {
            "event_id": event_id,
            "relation_type": relation_type,
            "score": score,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                if response.status_code in [200, 201]:
                    return True
        except Exception as exc:
            logger.debug("HTTP call for attach_event_evidence failed: %s", exc)
            if self.is_custom_url:
                return False

        # 2. In-process direct database lookup fallback
        try:
            db = SessionLocal()
            try:
                rel = (
                    IncidentRelationType(relation_type)
                    if relation_type in IncidentRelationType.__members__ or relation_type in [e.value for e in IncidentRelationType]
                    else IncidentRelationType.PRIMARY_SIGNAL
                )
                event_in = IncidentEventCreate(
                    event_id=event_id,
                    relation_type=rel,
                    score=score,
                )
                assoc, created = IncidentService.add_event_to_incident(db, incident_key, event_in)
                if assoc:
                    return True
            finally:
                db.close()
        except Exception:
            pass
        return False
