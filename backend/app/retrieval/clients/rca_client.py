from datetime import datetime
import logging
from typing import List, Optional, Tuple
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.rca.db.models import RCAAnalysis
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType

logger = logging.getLogger(__name__)


class RCAServiceClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 4.0):
        settings = get_settings()
        self.base_url = (base_url or settings.RCA_SERVICE_URL).rstrip("/")
        self.timeout = timeout

    def search_rca_reports(
        self,
        group_key: Optional[str] = None,
        min_confidence: Optional[float] = None,
        top_k: int = 5,
    ) -> Tuple[List[RetrievalResultItem], Optional[str]]:
        """Retrieve historical RCA reports."""
        # 1. HTTP call (supports test monkeypatching and microservices)
        url = f"{self.base_url}/api/v1/rca"
        params = {"page": 1, "page_size": top_k}
        if group_key:
            params["group_key"] = group_key
        if min_confidence is not None:
            params["min_confidence"] = min_confidence

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    items = []
                    for report in data.get("items", []):
                        ts_val = report.get("started_at")
                        ts = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00")) if ts_val else None
                        key = report.get("analysis_key", "RCA-UNKNOWN")
                        root_cause = report.get("primary_root_cause", "")
                        candidates_summary = ", ".join(
                            [f"{c.get('candidate_name')} ({c.get('score'):.2f})" for c in report.get("candidates", [])[:3]]
                        )
                        content = f"Primary Root Cause: {root_cause}. Top Candidates: {candidates_summary}."
                        items.append(
                            RetrievalResultItem(
                                source_type=SourceType.RCA,
                                source_id=key,
                                title=f"RCA: {root_cause}",
                                content=content,
                                timestamp=ts,
                                similarity_score=0.90,
                                citation=f"[RCA:{key}]",
                                metadata={
                                    "group_key": report.get("group_key"),
                                    "primary_confidence": report.get("primary_confidence"),
                                    "status": report.get("status"),
                                },
                            )
                        )
                    return items, None
        except Exception:
            pass

        # 2. Try in-process DB search fallback
        try:
            db = SessionLocal()
            try:
                query = select(RCAAnalysis).options(
                    selectinload(RCAAnalysis.candidates),
                    selectinload(RCAAnalysis.edges),
                )
                filters = []
                if group_key:
                    filters.append(RCAAnalysis.group_key == group_key)
                if min_confidence is not None:
                    filters.append(RCAAnalysis.primary_confidence >= min_confidence)

                if filters:
                    query = query.where(*filters)

                reports = list(
                    db.execute(
                        query.order_by(RCAAnalysis.created_at.desc()).limit(top_k)
                    ).scalars().all()
                )

                if reports:
                    items: List[RetrievalResultItem] = []
                    for report in reports:
                        key = report.analysis_key
                        root_cause = report.primary_root_cause or ""
                        candidates_summary = ", ".join(
                            [f"{c.candidate_name} ({c.score:.2f})" for c in report.candidates[:3]]
                        )
                        content = f"Primary Root Cause: {root_cause}. Top Candidates: {candidates_summary}."
                        items.append(
                            RetrievalResultItem(
                                source_type=SourceType.RCA,
                                source_id=key,
                                title=f"RCA: {root_cause}",
                                content=content,
                                timestamp=report.started_at,
                                similarity_score=0.90,
                                citation=f"[RCA:{key}]",
                                metadata={
                                    "group_key": report.group_key,
                                    "primary_confidence": report.primary_confidence,
                                    "status": report.status,
                                },
                            )
                        )
                    return items, None
            finally:
                db.close()
        except Exception:
            pass

        return [], "RCA Service unavailable"
