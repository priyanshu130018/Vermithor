import logging
from typing import Any, Dict, Optional
import httpx

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.correlation.services.correlation_service import CorrelationService

logger = logging.getLogger(__name__)


class CorrelationServiceClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 5.0):
        settings = get_settings()
        self.is_custom_url = base_url is not None
        self.base_url = (base_url or settings.CORRELATION_SERVICE_URL).rstrip("/")
        self.timeout = timeout

    def get_correlation_group(self, group_key: str) -> Optional[Dict[str, Any]]:
        """Fetch correlation group data and its associated signals."""
        # 1. HTTP call (supports test monkeypatching and microservices)
        url = f"{self.base_url}/api/v1/correlations/groups/{group_key}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
        except Exception as exc:
            logger.debug("HTTP call for correlation group '%s' failed: %s", group_key, exc)
            if self.is_custom_url:
                return None

        # 2. In-process direct database lookup fallback
        try:
            db = SessionLocal()
            try:
                group = CorrelationService.get_group(db, group_key)
                if group:
                    signals = [
                        {
                            "signal_id": s.signal_id,
                            "signal_type": s.signal_type,
                            "service": s.service,
                            "environment": s.environment,
                            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                            "severity": s.severity,
                            "source_reference": s.source_reference,
                            "metadata": s.metadata_json or {},
                        }
                        for s in group.signals
                    ]
                    return {
                        "group_key": group.group_key,
                        "environment": group.environment,
                        "primary_service": group.primary_service,
                        "started_at": group.started_at.isoformat() if group.started_at else None,
                        "ended_at": group.ended_at.isoformat() if group.ended_at else None,
                        "correlation_score": group.correlation_score,
                        "status": group.status,
                        "reasons": group.reasons or [],
                        "incident_key": group.incident_key,
                        "signals": signals,
                    }
            finally:
                db.close()
        except Exception:
            pass
        return None
