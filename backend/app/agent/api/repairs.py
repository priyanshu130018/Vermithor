import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.agent.schemas.repair import (
    ApprovalRequest,
    RepairRequest,
    RepairResponse,
    RepairStatus,
)
from backend.app.agent.services.repair_service import RepairService
from backend.app.common.config import get_settings
from backend.app.common.database import get_db
from backend.app.common.rate_limiter import RateLimiter
from backend.app.common.security import require_jwt_auth, verify_org_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-repairs"])
repair_service = RepairService()
settings = get_settings()
repair_rate_limiter = RateLimiter(
    scope="repairs",
    calls_per_minute=settings.RATE_LIMIT_REPAIRS_PER_MIN,
)


@router.post(
    "/repairs",
    response_model=RepairResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger LangGraph AI code repair agent",
    description=(
        "Initiates an evidence-backed code repair workflow for a completed incident investigation. "
        "Inspects authorized repository files, proposes a minimal patch, and runs tests in an isolated sandbox. "
        "Strictly requires explicit human review and approval; never autonomously merges or deploys code."
    ),
)
def create_or_run_repair(
    payload: RepairRequest,
    async_mode: bool = Query(False, description="Whether to dispatch repair task to background Celery queue"),
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
    _rate_limit: None = Depends(repair_rate_limiter),
) -> RepairResponse:
    """Initiate an AI-powered code repair workflow for an incident investigation."""
    user_org = verify_org_access(auth)
    if not payload.investigation_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field 'investigation_key' must not be empty",
        )
    if async_mode:
        from backend.workers.tasks import repair_code_task
        task_payload = payload.model_dump()
        task_payload["org_id"] = user_org
        task = repair_code_task.delay(task_payload)
        logger.info("Dispatched async Celery repair task: %s", task.id)
        # Return initial pending placeholder
        repair_key = repair_service.generate_repair_key(db)
        from backend.app.agent.db.models import Repair
        db_rep = Repair(
            repair_key=repair_key,
            org_id=user_org,
            investigation_key=payload.investigation_key,
            incident_key="PENDING",
            status=RepairStatus.PENDING.value,
            repository_url=payload.repository_url,
            target_branch=payload.target_branch,
            validation_status="PENDING",
            requires_human_approval=True,
            approval_status="PENDING",
        )
        db.add(db_rep)
        db.commit()
        db.refresh(db_rep)
        return repair_service._to_response(db_rep)

    try:
        result = repair_service.run_repair(
            db=db,
            req=payload,
            user_identity=auth,
        )
        return result
    except PermissionError as perm_exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(perm_exc),
        )
    except Exception as exc:
        logger.error("Repair workflow failed for investigation '%s': %s", payload.investigation_key, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Repair workflow encountered an unexpected error: {str(exc)[:300]}",
        )


@router.get(
    "/repairs/{repair_id}",
    response_model=RepairResponse,
    summary="Get repair report by ID or key",
    description="Retrieves a code repair artifact and validation report by its repair_key (REP-...) or UUID.",
)
def get_repair_by_id(
    repair_id: str,
    db: Session = Depends(get_db),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> RepairResponse:
    """Retrieve specific repair artifact and validation status."""
    user_org = verify_org_access(_auth)
    rep = repair_service.get_repair(db, repair_id, org_id=user_org)
    if not rep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repair '{repair_id}' not found",
        )
    return rep


@router.get(
    "/repairs",
    summary="List paginated code repair jobs",
    description="Lists past and current code repair proposals with filtering by investigation key, incident key, and status.",
)
def list_repairs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    investigation_key: Optional[str] = Query(None, description="Filter by investigation key"),
    incident_key: Optional[str] = Query(None, description="Filter by incident key"),
    status: Optional[str] = Query(None, description="Filter by repair status"),
    db: Session = Depends(get_db),
    _auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> Dict[str, Any]:
    """List paginated code repair jobs."""
    user_org = verify_org_access(_auth)
    items, total = repair_service.list_repairs(
        db,
        page=page,
        page_size=page_size,
        investigation_key=investigation_key,
        incident_key=incident_key,
        status=status,
        org_id=user_org,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "/repairs/{repair_id}/approve",
    response_model=RepairResponse,
    summary="Record human review decision for proposed repair",
    description=(
        "Records an explicit human review decision ('APPROVE' or 'REJECT') for a proposed code repair. "
        "Strict Safety Guardrail: This endpoint records human approval, but DOES NOT autonomously merge "
        "or deploy code into production."
    ),
)
def approve_or_reject_repair(
    repair_id: str,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> RepairResponse:
    verify_org_access(auth)
    try:
        user_id = auth.get("sub") or auth.get("username") or "human-engineer"
        return repair_service.approve_or_reject_repair(
            db=db,
            repair_id=repair_id,
            approval_req=payload,
            reviewer_id=user_id,
            user_identity=auth,
        )
    except PermissionError as perm_exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(perm_exc),
        )
    except ValueError as val_exc:
        val_str = str(val_exc).lower()
        if "stale" in val_str or "already finalized" in val_str:
            status_code = status.HTTP_409_CONFLICT
        elif "not found" in val_str:
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(
            status_code=status_code,
            detail=str(val_exc),
        )
    except Exception as exc:
        logger.error("Error approving repair '%s': %s", repair_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Approval recording encountered an error: {str(exc)[:300]}",
        )
