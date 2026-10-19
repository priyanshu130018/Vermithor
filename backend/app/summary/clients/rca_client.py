import logging
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.rca.db.models import RCAAnalysis

logger = logging.getLogger(__name__)


class RCAClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 4.0):
        settings = get_settings()
        self.base_url = (base_url or settings.RCA_SERVICE_URL).rstrip("/")
        self.timeout = timeout

    def get_rca_reports(self, group_key: Optional[str] = None, top_k: int = 1) -> List[Dict[str, Any]]:
        """Retrieve recent RCA reports."""
        # 1. HTTP call (supports test mocking and microservices)
        url = f"{self.base_url}/api/v1/rca"
        params = {"page": 1, "page_size": top_k}
        if group_key:
            params["group_key"] = group_key

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("items", [])
        except Exception as exc:
            logger.debug("HTTP call for RCA reports failed, falling back to direct DB: %s", exc)

        # 2. In-process direct lookup fallback
        try:
            db = SessionLocal()
            try:
                query = select(RCAAnalysis).options(
                    selectinload(RCAAnalysis.candidates),
                    selectinload(RCAAnalysis.edges),
                )
                if group_key:
                    query = query.where(RCAAnalysis.group_key == group_key)

                reports = list(
                    db.execute(
                        query.order_by(RCAAnalysis.created_at.desc()).limit(top_k)
                    ).scalars().all()
                )

                if reports:
                    result: List[Dict[str, Any]] = []
                    for r in reports:
                        candidates = [
                            {
                                "candidate_type": c.candidate_type,
                                "candidate_name": c.candidate_name,
                                "score": c.score,
                                "rank": c.rank,
                                "is_primary": c.is_primary,
                                "evidence": c.evidence,
                            }
                            for c in r.candidates
                        ]
                        edges = [
                            {
                                "source_signal_id": e.source_signal_id,
                                "target_signal_id": e.target_signal_id,
                                "relationship": e.relationship,
                                "score": e.score,
                                "evidence": e.evidence,
                            }
                            for e in r.edges
                        ]
                        result.append({
                            "id": str(r.id),
                            "analysis_key": r.analysis_key,
                            "group_key": r.group_key,
                            "analysis_version": r.analysis_version,
                            "status": r.status,
                            "primary_root_cause": r.primary_root_cause,
                            "primary_confidence": r.primary_confidence,
                            "causal_chain": r.causal_chain or [],
                            "candidates": candidates,
                            "edges": edges,
                            "started_at": r.started_at.isoformat() if r.started_at else None,
                            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                        })
                    return result
            finally:
                db.close()
        except Exception:
            pass
        return []

    def get_rca_by_key(self, analysis_key: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific RCA analysis by key."""
        try:
            db = SessionLocal()
            try:
                r = db.execute(
                    select(RCAAnalysis)
                    .options(
                        selectinload(RCAAnalysis.candidates),
                        selectinload(RCAAnalysis.edges),
                    )
                    .where(RCAAnalysis.analysis_key == analysis_key)
                ).scalar_one_or_none()

                if r:
                    candidates = [
                        {
                            "candidate_type": c.candidate_type,
                            "candidate_name": c.candidate_name,
                            "score": c.score,
                            "rank": c.rank,
                            "is_primary": c.is_primary,
                            "evidence": c.evidence,
                        }
                        for c in r.candidates
                    ]
                    edges = [
                        {
                            "source_signal_id": e.source_signal_id,
                            "target_signal_id": e.target_signal_id,
                            "relationship": e.relationship,
                            "score": e.score,
                            "evidence": e.evidence,
                        }
                        for e in r.edges
                    ]
                    return {
                        "id": str(r.id),
                        "analysis_key": r.analysis_key,
                        "group_key": r.group_key,
                        "analysis_version": r.analysis_version,
                        "status": r.status,
                        "primary_root_cause": r.primary_root_cause,
                        "primary_confidence": r.primary_confidence,
                        "causal_chain": r.causal_chain or [],
                        "candidates": candidates,
                        "edges": edges,
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    }
            finally:
                db.close()
        except Exception:
            pass

        url = f"{self.base_url}/api/v1/rca/{analysis_key}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return res.json()
        except Exception:
            pass
        return None
