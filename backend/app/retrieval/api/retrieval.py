import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.retrieval.retrieval.engine import RetrievalEngine
from backend.app.retrieval.schemas.retrieval import (
    RAGContextRequest,
    RAGContextResponse,
    RetrievalQuery,
    RetrievalResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["retrieval"])
engine = RetrievalEngine()


@router.post(
    "/retrieval/search",
    response_model=RetrievalResponse,
    summary="Multi-source hybrid retrieval search",
    description="Searches logs, incidents, RCA reports, and runbooks with hybrid ranking, deduplication, and source attribution.",
)
def search_retrieval(
    req: RetrievalQuery,
    db: Session = Depends(get_db),
) -> RetrievalResponse:
    """Execute hybrid retrieval across heterogeneous observability and knowledge sources."""
    if not req.query and not req.incident_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either 'query' or 'incident_key' must be provided",
        )
    return engine.execute_query(db=db, req=req)


@router.post(
    "/retrieval/incident/{incident_key}",
    response_model=RetrievalResponse,
    summary="Incident context retrieval",
    description="Loads incident details, extracts query context, and collects evidence across all relevant sources.",
)
def retrieve_incident_context(
    incident_key: str,
    top_k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> RetrievalResponse:
    """Collect and rank evidence relevant to an incident."""
    return engine.execute_incident_retrieval(db=db, incident_key=incident_key, top_k=top_k)


@router.post(
    "/rag/context",
    response_model=RAGContextResponse,
    summary="Assemble grounded RAG context for LLM",
    description="Retrieves evidence, ranks, enforces context limits, and formats prompt-ready context text for LLM incident summary generation.",
)
def get_rag_context(
    req: RAGContextRequest,
    db: Session = Depends(get_db),
) -> RAGContextResponse:
    """Generate structured and text-formatted RAG context with budget enforcement."""
    if not req.query and not req.incident_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either 'query' or 'incident_key' must be provided",
        )
    return engine.assemble_rag_context(db=db, req=req)
