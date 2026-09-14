import logging
from typing import Any, Dict, Optional
import httpx

from backend.app.common.config import get_settings
from backend.app.common.database import SessionLocal
from backend.app.retrieval.retrieval.engine import RetrievalEngine
from backend.app.retrieval.schemas.retrieval import RAGContextRequest

logger = logging.getLogger(__name__)


class RetrievalClient:
    """Decoupled client supporting both direct in-process service calls and mocked HTTP testing."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 6.0):
        settings = get_settings()
        self.base_url = (base_url or settings.RETRIEVAL_SERVICE_URL).rstrip("/")
        self.timeout = timeout
        self.engine = RetrievalEngine()

    def get_rag_context(
        self,
        incident_key: str,
        query: Optional[str] = None,
        top_k: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve grounded RAG context for an incident."""
        # 1. Try HTTP first if monkeypatched or needed
        url = f"{self.base_url}/api/v1/rag/context"
        payload = {
            "incident_key": incident_key,
            "query": query,
            "top_k": top_k,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()
        except Exception:
            pass

        # 2. In-process direct assembly fallback
        try:
            db = SessionLocal()
            try:
                req = RAGContextRequest(
                    incident_key=incident_key,
                    query=query,
                    top_k=top_k,
                )
                response = self.engine.assemble_rag_context(db=db, req=req)
                return response.model_dump()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Error fetching RAG context in-process: %s", exc)
        return None
