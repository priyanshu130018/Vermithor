from datetime import datetime, timezone
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.rca.analysis.analyzer import RCAAnalyzer
from backend.app.rca.clients.correlation_client import CorrelationServiceClient
from backend.app.common.config import get_settings
from backend.app.common.database import get_db
from backend.app.rca.db.models import CausalEdge, RCAAnalysis, RootCauseCandidate
from backend.app.rca.schemas.rca import (
    AnalysisStatus,
    RCAAnalysisListResponse,
    RCAAnalysisResponse,
)

router = APIRouter(prefix="/rca", tags=["rca"])
settings = get_settings()
correlation_client = CorrelationServiceClient(settings.CORRELATION_SERVICE_URL)
analyzer = RCAAnalyzer(settings)


def generate_analysis_key(db: Session) -> str:
    """Generate a database-backed human-readable analysis key (e.g. RCA-000001)."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        try:
            seq_val = db.execute(text("SELECT nextval('rca_analysis_key_seq')")).scalar()
            return f"RCA-{int(seq_val):06d}"
        except Exception:
            db.rollback()
            count = db.execute(select(func.count(RCAAnalysis.id))).scalar() or 0
            return f"RCA-{count + 1:06d}"
    else:
        count = db.execute(select(func.count(RCAAnalysis.id))).scalar() or 0
        return f"RCA-{count + 1:06d}"


@router.post(
    "/analyze/{group_key}",
    response_model=RCAAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute Root Cause Analysis on a correlation group",
    description="Fetches correlation signals from Correlation Service, evaluates causal graphs and candidates, and persists an explainable RCA analysis.",
)
def analyze_correlation_group(
    group_key: str,
    db: Session = Depends(get_db),
) -> RCAAnalysisResponse:
    """Run RCA analysis on a specific correlation group."""
    # 1. Idempotency check
    existing = db.execute(
        select(RCAAnalysis)
        .options(
            selectinload(RCAAnalysis.candidates),
            selectinload(RCAAnalysis.edges),
        )
        .where(
            RCAAnalysis.group_key == group_key,
            RCAAnalysis.analysis_version == settings.RCA_ANALYSIS_VERSION,
        )
    ).scalar_one_or_none()

    if existing and existing.status == "COMPLETED":
        return RCAAnalysisResponse.from_orm_model(existing)

    # 2. Fetch group from Correlation Service
    started_at = datetime.now(timezone.utc)
    group_data = correlation_client.get_correlation_group(group_key)

    if group_data is None:
        # Check if Correlation Service is completely unreachable or group was simply not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Correlation group '{group_key}' not found or unreachable from Correlation Service",
        )

    # 3. Execute RCA Analyzer
    analysis_result = analyzer.analyze(group_data)

    # 4. Persist analysis
    analysis_key = generate_analysis_key(db)
    completed_at = datetime.now(timezone.utc)

    db_analysis = RCAAnalysis(
        analysis_key=analysis_key,
        group_key=group_key,
        analysis_version=settings.RCA_ANALYSIS_VERSION,
        status="COMPLETED",
        primary_root_cause=analysis_result["primary_root_cause"],
        primary_confidence=analysis_result["primary_confidence"],
        causal_chain=analysis_result["causal_chain"],
        started_at=started_at,
        completed_at=completed_at,
    )
    db.add(db_analysis)
    db.flush()

    # 5. Persist candidates
    for cand in analysis_result["candidates"]:
        db_cand = RootCauseCandidate(
            analysis_id=db_analysis.id,
            candidate_type=cand["candidate_type"],
            candidate_name=cand["candidate_name"],
            score=cand["score"],
            rank=cand["rank"],
            is_primary=cand["is_primary"],
            evidence=cand.get("evidence", []),
        )
        db.add(db_cand)

    # 6. Persist causal edges
    for edge in analysis_result["edges"]:
        db_edge = CausalEdge(
            analysis_id=db_analysis.id,
            source_signal_id=edge["source_signal_id"],
            target_signal_id=edge["target_signal_id"],
            relationship=edge["relationship"],
            score=edge["score"],
            evidence=edge.get("evidence", {}),
        )
        db.add(db_edge)

    db.commit()
    db.refresh(db_analysis)

    # Reload with relationships
    loaded = db.execute(
        select(RCAAnalysis)
        .options(
            selectinload(RCAAnalysis.candidates),
            selectinload(RCAAnalysis.edges),
        )
        .where(RCAAnalysis.id == db_analysis.id)
    ).scalar_one()

    return RCAAnalysisResponse.from_orm_model(loaded)


@router.get(
    "/{analysis_key}",
    response_model=RCAAnalysisResponse,
    summary="Get RCA analysis by analysis_key",
    description="Retrieve full details of an existing RCA analysis report.",
)
def get_rca_analysis(
    analysis_key: str,
    db: Session = Depends(get_db),
) -> RCAAnalysisResponse:
    """Retrieve an RCA analysis report by analysis_key."""
    analysis = db.execute(
        select(RCAAnalysis)
        .options(
            selectinload(RCAAnalysis.candidates),
            selectinload(RCAAnalysis.edges),
        )
        .where(RCAAnalysis.analysis_key == analysis_key)
    ).scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RCA analysis with key '{analysis_key}' not found",
        )
    return RCAAnalysisResponse.from_orm_model(analysis)


@router.get(
    "",
    response_model=RCAAnalysisListResponse,
    summary="List RCA analyses with filtering and pagination",
    description="Retrieve a paginated list of RCA analysis reports.",
)
def list_rca_analyses(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    group_key: Optional[str] = Query(None, description="Filter by correlation group key"),
    status: Optional[AnalysisStatus] = Query(None, description="Filter by analysis status"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Filter by minimum primary confidence"),
    start_time: Optional[datetime] = Query(None, description="Filter analyses started >= start timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter analyses completed <= end timestamp"),
    db: Session = Depends(get_db),
) -> RCAAnalysisListResponse:
    """List RCA analyses with multi-attribute filtering and pagination."""
    query: Select = select(RCAAnalysis).options(
        selectinload(RCAAnalysis.candidates),
        selectinload(RCAAnalysis.edges),
    )
    count_query: Select = select(func.count(RCAAnalysis.id))

    filters = []
    if group_key:
        filters.append(RCAAnalysis.group_key == group_key)
    if status:
        filters.append(RCAAnalysis.status == status.value)
    if min_confidence is not None:
        filters.append(RCAAnalysis.primary_confidence >= min_confidence)
    if start_time:
        filters.append(RCAAnalysis.started_at >= start_time)
    if end_time:
        filters.append(RCAAnalysis.completed_at <= end_time)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.execute(count_query).scalar() or 0
    offset = (page - 1) * page_size

    items = list(
        db.execute(
            query.order_by(RCAAnalysis.created_at.desc())
            .offset(offset)
            .limit(page_size)
        ).scalars().all()
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return RCAAnalysisListResponse(
        items=[RCAAnalysisResponse.from_orm_model(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
