from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.incidents.services.incident_service import IncidentService
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType

logger = logging.getLogger(__name__)


class IncidentServiceClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 4.0):
        settings = get_settings()
        self.base_url = (base_url or settings.INCIDENT_SERVICE_URL).rstrip("/")
        self.timeout = timeout

    def get_incident(self, incident_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve single incident details by key."""
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

        # HTTP fallback
        url = f"{self.base_url}/api/v1/incidents/{incident_key}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json()
        except Exception:
            pass
        return None

    def search_incidents(
        self,
        query: Optional[str] = None,
        service: Optional[str] = None,
        environment: Optional[str] = None,
        severity: Optional[str] = None,
        top_k: int = 5,
    ) -> Tuple[List[RetrievalResultItem], Optional[str]]:
        """Retrieve historical incidents with optional metadata filters and dynamic similarity scoring."""
        # 1. Try in-process DB first if not mocked
        try:
            db = SessionLocal()
            try:
                items_orm, total = IncidentService.list_incidents(
                    db=db,
                    page=1,
                    page_size=top_k * 2,
                    severity=severity,
                    environment=environment,
                )
                if items_orm:
                    items: List[RetrievalResultItem] = []
                    terms = [t.strip().lower() for t in query.split() if len(t.strip()) > 1] if query else []
                    for inc in items_orm:
                        key = inc.incident_key
                        text_blob = f"{inc.title} {inc.description or ''} {service or ''}".lower()
                        if terms:
                            matches = sum(1 for t in terms if t in text_blob)
                            score = 0.50 + (0.45 * (matches / max(1, len(terms)))) if matches > 0 else 0.40
                        else:
                            score = 0.80

                        items.append(
                            RetrievalResultItem(
                                source_type=SourceType.INCIDENT,
                                source_id=key,
                                title=f"Incident: {inc.title}",
                                content=inc.description or inc.title,
                                service=service or "platform",
                                environment=inc.environment,
                                timestamp=inc.started_at,
                                similarity_score=round(score, 4),
                                citation=f"[INCIDENT:{key}]",
                                metadata={
                                    "severity": inc.severity,
                                    "status": inc.status,
                                    "confidence": inc.confidence,
                                },
                            )
                        )
                    items.sort(key=lambda x: x.similarity_score, reverse=True)
                    return items[:top_k], None
            finally:
                db.close()
        except Exception:
            pass

        # 2. HTTP fallback for mocked tests
        url = f"{self.base_url}/api/v1/incidents"
        params = {"page": 1, "page_size": top_k}
        if query:
            params["query"] = query
        if service:
            params["service"] = service
        if environment:
            params["environment"] = environment
        if severity:
            params["severity"] = severity

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    items: List[RetrievalResultItem] = []
                    terms = [t.strip().lower() for t in query.split() if len(t.strip()) > 1] if query else []
                    for inc in data.get("items", []):
                        ts_val = inc.get("started_at")
                        ts = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00")) if ts_val else None
                        key = inc.get("incident_key", "INC-UNKNOWN")
                        text_blob = f"{inc.get('title', '')} {inc.get('description', '')} {service or ''}".lower()
                        if terms:
                            matches = sum(1 for t in terms if t in text_blob)
                            score = 0.50 + (0.45 * (matches / max(1, len(terms)))) if matches > 0 else 0.40
                        else:
                            score = 0.80

                        items.append(
                            RetrievalResultItem(
                                source_type=SourceType.INCIDENT,
                                source_id=key,
                                title=f"Incident: {inc.get('title')}",
                                content=inc.get("description") or inc.get("title", ""),
                                service=inc.get("service"),
                                environment=inc.get("environment"),
                                timestamp=ts,
                                similarity_score=round(score, 4),
                                citation=f"[INCIDENT:{key}]",
                                metadata={
                                    "severity": inc.get("severity"),
                                    "status": inc.get("status"),
                                    "confidence": inc.get("confidence"),
                                },
                            )
                        )
                    items.sort(key=lambda x: x.similarity_score, reverse=True)
                    return items[:top_k], None
                else:
                    msg = f"Incident Service returned status {res.status_code}"
                    return [], msg
        except Exception as exc:
            msg = f"Incident Service unavailable: {exc}"
            return [], msg
