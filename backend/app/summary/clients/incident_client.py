import logging
from typing import Any, Dict, Optional
import httpx

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.incidents.services.incident_service import IncidentService

logger = logging.getLogger(__name__)


class IncidentClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 4.0):
        settings = get_settings()
        self.base_url = (base_url or settings.INCIDENT_SERVICE_URL).rstrip("/")
        self.timeout = timeout

    def get_incident(self, incident_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve full incident details by key."""
        # 1. In-process direct lookup
        try:
            db = SessionLocal()
            try:
                inc = IncidentService.get_incident_by_key(db, incident_key)
                if inc:
                    return {
                        "id": str(inc.id),
                        "incident_key": inc.incident_key,
                        "title": inc.title,
                        "description": inc.description,
                        "severity": inc.severity,
                        "status": inc.status,
                        "environment": inc.environment,
                        "confidence": inc.confidence,
                        "started_at": inc.started_at.isoformat() if inc.started_at else None,
                        "ended_at": inc.ended_at.isoformat() if inc.ended_at else None,
                    }
            finally:
                db.close()
        except Exception:
            pass

        # 2. HTTP fallback for mocked tests
        url = f"{self.base_url}/api/v1/incidents/{incident_key}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json()
        except Exception:
            pass
        return None
