import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.agent.schemas.shadow import ShadowModeRequest, ShadowModeResponse
from backend.app.agent.services.shadow_service import ShadowEvaluationService
from backend.app.common.database import get_db
from backend.app.common.rate_limiter import RateLimiter
from backend.app.common.security import require_jwt_auth, verify_org_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent/shadow", tags=["shadow-mode"])
shadow_service = ShadowEvaluationService()
shadow_rate_limiter = RateLimiter(scope="shadow_evaluation", calls_per_minute=20, window_seconds=60)


@router.post(
    "/evaluate",
    response_model=ShadowModeResponse,
    summary="Trigger passive shadow-mode incident evaluation",
    description="Analyzes incident telemetry in strictly read-only shadow mode without triggering repair workflows or external writes.",
    dependencies=[Depends(shadow_rate_limiter)],
)
def evaluate_incident_shadow_mode(
    req: ShadowModeRequest,
    db: Session = Depends(get_db),
    user_identity: Dict[str, Any] = Depends(require_jwt_auth),
) -> ShadowModeResponse:
    """Execute passive shadow-mode investigation with zero repair triggers."""
    verify_org_access(user_identity)
    org_id = user_identity.get("org_id") or user_identity.get("organization") or "vermithor"

    try:
        return shadow_service.run_shadow_evaluation(
            db=db,
            req=req,
            org_id=str(org_id),
        )
    except Exception as exc:
        logger.error("Shadow-mode evaluation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Shadow-mode evaluation failed: {exc}",
        )
