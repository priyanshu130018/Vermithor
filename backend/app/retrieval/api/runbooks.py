import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.retrieval.repositories.runbook_repository import RunbookRepository
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem
from backend.app.retrieval.schemas.runbooks import (
    RunbookCreateRequest,
    RunbookListResponse,
    RunbookResponse,
    RunbookSearchRequest,
    RunbookUpdateRequest,
)

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


@router.post(
    "",
    response_model=RunbookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new runbook",
)
def create_runbook(
    req: RunbookCreateRequest,
    db: Session = Depends(get_db),
) -> RunbookResponse:
    """Create and persist an operational runbook."""
    if req.runbook_key:
        existing = RunbookRepository.get_by_key(db, req.runbook_key)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Runbook with key '{req.runbook_key}' already exists",
            )
    rb = RunbookRepository.create(db, req)
    return RunbookResponse.model_validate(rb)


@router.get(
    "",
    response_model=RunbookListResponse,
    summary="List runbooks with pagination and filters",
)
def list_runbooks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> RunbookListResponse:
    """Retrieve paginated runbooks with optional service and category filters."""
    items, total = RunbookRepository.list_runbooks(
        db=db,
        page=page,
        page_size=page_size,
        service=service,
        category=category,
    )
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
    return RunbookListResponse(
        items=[RunbookResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{runbook_key}",
    response_model=RunbookResponse,
    summary="Get runbook by key",
)
def get_runbook(
    runbook_key: str,
    db: Session = Depends(get_db),
) -> RunbookResponse:
    """Retrieve single runbook details."""
    rb = RunbookRepository.get_by_key(db, runbook_key)
    if not rb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runbook with key '{runbook_key}' not found",
        )
    return RunbookResponse.model_validate(rb)


@router.delete(
    "/{runbook_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete runbook by key",
)
def delete_runbook(
    runbook_key: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a runbook by its unique key."""
    deleted = RunbookRepository.delete(db, runbook_key)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runbook with key '{runbook_key}' not found",
        )


@router.post(
    "/search",
    response_model=list[RetrievalResultItem],
    summary="Search runbooks by keywords and metadata",
)
def search_runbooks(
    req: RunbookSearchRequest,
    db: Session = Depends(get_db),
) -> list[RetrievalResultItem]:
    """Search runbooks matching query terms."""
    return RunbookRepository.search_runbooks(
        db=db,
        query=req.query,
        top_k=req.top_k,
        service=req.service,
        category=req.category,
    )
