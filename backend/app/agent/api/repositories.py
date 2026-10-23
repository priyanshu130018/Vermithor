from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent.db.models import RepositoryConnection
from backend.app.agent.git.factory import GitProviderFactory
from backend.app.agent.schemas.repository import (
    RepoConnectRequest,
    RepoConnectResponse,
    RepoDisconnectResponse,
    RepoVerifyResponse,
    RepositorySummaryResponse,
    validate_repo_identifier,
)
from backend.app.common.config import get_settings
from backend.app.common.database import get_db
from backend.app.common.rate_limiter import RateLimiter
from backend.app.common.security import require_jwt_auth, verify_org_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent/repositories", tags=["agent-repositories"])
settings = get_settings()
repo_rate_limiter = RateLimiter(
    scope="repositories",
    calls_per_minute=settings.RATE_LIMIT_REPOSITORIES_PER_MIN,
)


def _get_tenant_org(auth: Dict[str, Any]) -> str:
    """Extract and normalize organization identifier from JWT auth context."""
    return str(auth.get("org_id") or auth.get("organization") or auth.get("org") or "default").lower()


@router.post(
    "/connect",
    response_model=RepoConnectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect Git repository in read-only pilot mode",
    description=(
        "Connects a dedicated test repository under least-privilege read-only permissions "
        "('contents: read', 'metadata: read'). Validates the repository identifier against "
        "path traversal, command injection, and SSRF loopback/private hosts. Probes read-only "
        "reachability and records connection metadata without storing plaintext secrets."
    ),
)
def connect_repository(
    payload: RepoConnectRequest,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
    _rate_limit: None = Depends(repo_rate_limiter),
) -> RepoConnectResponse:
    """Register and verify a repository connection in strict read-only pilot mode."""
    verify_org_access(auth)
    tenant_org = _get_tenant_org(auth)
    repo_ident = payload.repo_identifier

    logger.info("Connecting repository '%s' for tenant '%s' in read-only pilot mode", repo_ident, tenant_org)

    # 1. Probe repository reachability and commit SHA via read-only provider
    provider = GitProviderFactory.get_provider(repo_ident, read_only=True)
    is_accessible = provider.authorize_access(repo_ident, "main", auth)
    if not is_accessible:
        logger.warning("Repository '%s' authorization check failed for org '%s'", repo_ident, tenant_org)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: unable to authorize read-only access to repository '{repo_ident}'",
        )

    latest_sha: Optional[str] = None
    try:
        latest_sha = provider.get_latest_commit_sha(repo_ident, "main")
    except Exception as exc:
        logger.warning("Could not resolve latest commit SHA for '%s': %s", repo_ident, exc)

    # 2. Check existing connection for this tenant
    stmt = select(RepositoryConnection).where(
        RepositoryConnection.org_id == tenant_org,
        RepositoryConnection.repo_identifier == repo_ident,
    )
    existing = db.execute(stmt).scalars().first()

    now = datetime.now(timezone.utc)
    user_sub = str(auth.get("sub") or "user")

    if existing:
        existing.status = "CONNECTED"
        existing.read_only = True
        existing.installation_id = payload.installation_id or existing.installation_id
        existing.connected_by = user_sub
        existing.connected_at = now
        existing.revoked_at = None
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        target_record = existing
    else:
        new_conn = RepositoryConnection(
            org_id=tenant_org,
            repo_identifier=repo_ident,
            installation_id=payload.installation_id,
            read_only=True,
            status="CONNECTED",
            connected_by=user_sub,
            connected_at=now,
        )
        db.add(new_conn)
        db.commit()
        db.refresh(new_conn)
        target_record = new_conn

    logger.info("AUDIT LOG: Repository '%s' connected for org '%s' in read-only mode by '%s'", repo_ident, tenant_org, user_sub)

    return RepoConnectResponse(
        id=target_record.id,
        org_id=target_record.org_id,
        repo_identifier=target_record.repo_identifier,
        installation_id=target_record.installation_id,
        read_only=True,
        status="CONNECTED",
        connected_by=target_record.connected_by,
        connected_at=target_record.connected_at,
        revoked_at=None,
        latest_commit_sha=latest_sha,
        permissions={"contents": "read", "metadata": "read"},
        audit_notice="Connected in Read-Only Pilot Mode: write operations (branch creation, PR creation, push) are strictly prohibited.",
    )


@router.get(
    "",
    response_model=List[RepositorySummaryResponse],
    summary="List connected repositories for authenticated tenant",
    description="Returns all active read-only repository connections for the authenticated organization.",
)
def list_repositories(
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> List[RepositorySummaryResponse]:
    """Retrieve tenant's connected repositories enforcing organization boundary isolation."""
    verify_org_access(auth)
    tenant_org = _get_tenant_org(auth)

    stmt = (
        select(RepositoryConnection)
        .where(
            RepositoryConnection.org_id == tenant_org,
            RepositoryConnection.status == "CONNECTED",
        )
        .order_by(RepositoryConnection.connected_at.desc())
    )
    results = db.execute(stmt).scalars().all()
    return [RepositorySummaryResponse.model_validate(r) for r in results]


@router.post(
    "/{repo_id}/disconnect",
    response_model=RepoDisconnectResponse,
    summary="Disconnect and revoke repository connection",
    description="Revokes access to a connected repository, marking status as REVOKED and preventing further inspection.",
)
def disconnect_repository(
    repo_id: str,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> RepoDisconnectResponse:
    """Disconnect repository connection and enforce tenant ownership."""
    verify_org_access(auth)
    tenant_org = _get_tenant_org(auth)

    # Resolve by UUID or repo_identifier
    filter_clause = (RepositoryConnection.org_id == tenant_org) & (
        (RepositoryConnection.repo_identifier == repo_id)
    )
    try:
        val_uuid = uuid.UUID(repo_id)
        filter_clause = (RepositoryConnection.org_id == tenant_org) & (
            (RepositoryConnection.id == val_uuid) | (RepositoryConnection.repo_identifier == repo_id)
        )
    except (ValueError, AttributeError):
        pass

    record = db.execute(select(RepositoryConnection).where(filter_clause)).scalars().first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository connection '{repo_id}' not found for organization '{tenant_org}'",
        )

    now = datetime.now(timezone.utc)
    record.status = "REVOKED"
    record.revoked_at = now
    record.updated_at = now
    db.commit()
    db.refresh(record)

    logger.info(
        "AUDIT LOG: Repository connection %s (%s) revoked for org '%s' by '%s'",
        record.id,
        record.repo_identifier,
        tenant_org,
        auth.get("sub"),
    )

    return RepoDisconnectResponse(
        id=record.id,
        repo_identifier=record.repo_identifier,
        status="REVOKED",
        revoked_at=now,
        message=f"Repository '{record.repo_identifier}' successfully disconnected. Further inspection requests are blocked.",
    )


@router.get(
    "/{repo_id}/verify",
    response_model=RepoVerifyResponse,
    summary="Verify repository connection, rate limits, and permissions",
    description="Probes the connected repository to confirm read-only connectivity, current commit SHA, and API rate limits.",
)
def verify_repository(
    repo_id: str,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
    _rate_limit: None = Depends(repo_rate_limiter),
) -> RepoVerifyResponse:
    """Verify health and permissions of a connected repository."""
    verify_org_access(auth)
    tenant_org = _get_tenant_org(auth)

    filter_clause = (RepositoryConnection.org_id == tenant_org) & (
        (RepositoryConnection.repo_identifier == repo_id)
    )
    try:
        val_uuid = uuid.UUID(repo_id)
        filter_clause = (RepositoryConnection.org_id == tenant_org) & (
            (RepositoryConnection.id == val_uuid) | (RepositoryConnection.repo_identifier == repo_id)
        )
    except (ValueError, AttributeError):
        pass

    record = db.execute(select(RepositoryConnection).where(filter_clause)).scalars().first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository connection '{repo_id}' not found for organization '{tenant_org}'",
        )

    if record.status == "REVOKED":
        return RepoVerifyResponse(
            repo_identifier=record.repo_identifier,
            status="REVOKED",
            reachable=False,
            read_only=True,
            message="Repository connection has been revoked. Reconnection required before inspection.",
        )

    provider = GitProviderFactory.get_provider(record.repo_identifier, read_only=True)
    rate_remaining: Optional[int] = None
    if hasattr(provider, "check_rate_limit"):
        rate_info = provider.check_rate_limit()
        rate_remaining = rate_info.get("remaining")

    latest_sha: Optional[str] = None
    try:
        latest_sha = provider.get_latest_commit_sha(record.repo_identifier, "main")
    except Exception as exc:
        logger.warning("Error fetching commit SHA during verify: %s", exc)

    return RepoVerifyResponse(
        repo_identifier=record.repo_identifier,
        status="CONNECTED",
        reachable=True,
        read_only=True,
        rate_limit_remaining=rate_remaining,
        latest_commit_sha=latest_sha,
        message="Repository verified and healthy in strict read-only pilot mode.",
    )
