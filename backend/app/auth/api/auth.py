import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.app.common.config import get_settings
from backend.app.common.security import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class DevTokenRequest(BaseModel):
    sub: Optional[str] = "sre-user-001"
    name: Optional[str] = "Incident Commander"
    role: Optional[str] = "admin"
    org_id: Optional[str] = "vermithor"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: Dict[str, Any]


def _issue_dev_token(req: Optional[DevTokenRequest] = None) -> TokenResponse:
    settings = get_settings()
    if settings.APP_ENV == "production" and not settings.ENABLE_DEV_AUTH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development token issuance is disabled in production environments.",
        )

    sub = (req.sub if req and req.sub else "sre-user-001").strip()
    name = (req.name if req and req.name else "Incident Commander").strip()
    role = (req.role if req and req.role else "admin").strip()

    expires_delta_seconds = 86400  # 24 hours
    org_id = (req.org_id if req and hasattr(req, "org_id") and req.org_id else "vermithor").strip().lower()
    payload = {
        "sub": sub,
        "name": name,
        "role": role,
        "org_id": org_id,
    }

    token = create_access_token(data=payload, expires_delta_seconds=expires_delta_seconds)
    logger.info("Issued development access token for sub=%s", sub)

    return TokenResponse(
        access_token=token,
        token_type="Bearer",
        expires_in=expires_delta_seconds,
        user=payload,
    )


@router.post("/dev-token", response_model=TokenResponse, summary="Issue a development access token")
def issue_dev_token_post(req: Optional[DevTokenRequest] = None) -> TokenResponse:
    """Issue a development JWT access token signed by the server's configured secret."""
    return _issue_dev_token(req)


@router.get("/dev-token", response_model=TokenResponse, summary="Issue a development access token (GET)")
def issue_dev_token_get() -> TokenResponse:
    """Issue a development JWT access token via GET for simplified development and sandbox initialization."""
    return _issue_dev_token(None)


@router.post("/token", response_model=TokenResponse, summary="Token endpoint for API clients")
def token_endpoint(req: Optional[DevTokenRequest] = None) -> TokenResponse:
    """Standard token issuance endpoint."""
    return _issue_dev_token(req)
