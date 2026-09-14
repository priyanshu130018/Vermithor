from datetime import datetime
import logging
from typing import List, Optional, Tuple
import httpx

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.log_intelligence.schemas.logs import SemanticSearchRequest
from backend.app.log_intelligence.search.semantic_search import SemanticSearchService
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType

logger = logging.getLogger(__name__)


class LogIntelligenceClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 4.0):
        settings = get_settings()
        self.base_url = (base_url or settings.LOG_INTELLIGENCE_SERVICE_URL).rstrip("/")
        self.timeout = timeout
        self.search_service = SemanticSearchService()

    def search_logs(
        self,
        query: str,
        top_k: int = 5,
        service: Optional[str] = None,
        environment: Optional[str] = None,
        severity: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[RetrievalResultItem], Optional[str]]:
        """Execute semantic log search."""
        # 1. Try in-process direct search first
        try:
            db = SessionLocal()
            try:
                req = SemanticSearchRequest(
                    query=query,
                    top_k=top_k,
                    service=service,
                    environment=environment,
                    severity=severity,
                    start_time=start_time,
                    end_time=end_time,
                )
                response = self.search_service.search(db, req)
                if response and response.results:
                    items: List[RetrievalResultItem] = []
                    for match in response.results:
                        src_id = str(match.source_event_id or match.log_id)
                        items.append(
                            RetrievalResultItem(
                                source_type=SourceType.LOG,
                                source_id=src_id,
                                title=f"Log: {match.category.value} on {match.service}",
                                content=match.message,
                                service=match.service,
                                environment=match.environment,
                                timestamp=match.timestamp,
                                similarity_score=float(match.similarity_score or 0.8),
                                citation=f"[LOG:{src_id}]",
                                metadata={
                                    "template": match.template,
                                    "category": match.category.value,
                                    "severity": match.severity,
                                },
                            )
                        )
                    return items, None
            finally:
                db.close()
        except Exception:
            pass

        # 2. HTTP fallback for mocked tests
        url = f"{self.base_url}/api/v1/logs/search"
        payload = {
            "query": query,
            "top_k": top_k,
            "service": service,
            "environment": environment,
            "severity": severity,
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    items = []
                    for match in data.get("results", []):
                        ts_val = match.get("timestamp")
                        ts = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00")) if ts_val else None
                        src_id = str(match.get("source_event_id") or match.get("log_id"))
                        items.append(
                            RetrievalResultItem(
                                source_type=SourceType.LOG,
                                source_id=src_id,
                                title=f"Log: {match.get('category')} on {match.get('service')}",
                                content=match.get("message", ""),
                                service=match.get("service"),
                                environment=match.get("environment"),
                                timestamp=ts,
                                similarity_score=float(match.get("similarity_score", 0.8)),
                                citation=f"[LOG:{src_id}]",
                                metadata={
                                    "template": match.get("template"),
                                    "category": match.get("category"),
                                    "severity": match.get("severity"),
                                },
                            )
                        )
                    return items, None
                else:
                    msg = f"Log Intelligence Service returned status {response.status_code}"
                    return [], msg
        except Exception as exc:
            msg = f"Log Intelligence Service unavailable: {exc}"
            return [], msg
