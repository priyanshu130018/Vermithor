import logging
from typing import Any, Dict, Optional

from backend.app.agent.git.base import GitProvider
from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.schemas.repair import RepairStatus

logger = logging.getLogger(__name__)


def authorize_repository_node(
    state: RepairState,
    git_provider: GitProvider,
    user_identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Verify whether the caller and organization are authorized to access the specified
    repository and target branch. Enforces organization boundaries and least-privilege access.
    """
    repo_url = state.get("repository_url") or "workspace"
    target_branch = state.get("target_branch") or "main"

    logger.info("Authorizing repository access for '%s' on branch '%s'", repo_url, target_branch)
    is_authorized = git_provider.authorize_access(
        repository_url=repo_url,
        branch=target_branch,
        user_identity=user_identity,
    )

    if not is_authorized:
        logger.warning("Repository authorization failed for '%s' (branch: %s)", repo_url, target_branch)
        return {
            "is_authorized": False,
            "status": RepairStatus.UNAUTHORIZED.value,
            "authorization_error": f"Access denied to repository '{repo_url}' for the authenticated tenant/user",
            "error_message": f"Access denied: User is not authorized to inspect or modify repository '{repo_url}'",
        }

    base_commit = None
    try:
        base_commit = git_provider.get_latest_commit_sha(repo_url, ref=target_branch)
    except Exception as exc:
        logger.warning("Could not determine latest commit SHA for '%s': %s", repo_url, exc)

    is_read_only = getattr(git_provider, "read_only", True)
    return {
        "is_authorized": True,
        "authorization_error": None,
        "base_commit": base_commit,
        "is_read_only_pilot": is_read_only,
        "pilot_audit_notice": "No repository changes have been published (Read-Only Pilot Mode)" if is_read_only else None,
    }


