import logging
from typing import Any, Dict, List

from backend.app.agent.git.base import GitProvider
from backend.app.agent.graph.repair_state import RepairState

logger = logging.getLogger(__name__)


def locate_relevant_code_node(state: RepairState, git_provider: GitProvider) -> Dict[str, Any]:
    """
    Locate and inspect relevant repository files using read-only operations.
    Prioritizes configuration, service routes, pool definitions, and corresponding tests
    derived from incident evidence and service names.
    """
    repo_url = state.get("repository_url") or "workspace"
    target_service = (state.get("target_service") or "").lower()
    target_branch = state.get("target_branch") or "main"
    evidence_citations = state.get("evidence_citations") or []

    logger.info("Locating relevant files for service '%s' in '%s'", target_service, repo_url)

    all_files = git_provider.list_files(repo_url, directory="", ref=target_branch)

    # Keywords to search for in filenames
    keywords = [target_service]
    # Check citations for endpoints or file names
    for cite in evidence_citations:
        if "/api/v1/payments" in cite or "payment" in cite.lower():
            keywords.extend(["payment", "charge", "pool", "database", "config"])
        if "hikari" in cite.lower() or "pool" in cite.lower():
            keywords.extend(["pool", "config", "datasource", "db"])

    # Score and filter matching files
    candidates: List[str] = []
    test_candidates: List[str] = []

    for f in all_files:
        f_lower = f.lower()
        if any(kw in f_lower for kw in ["test_", "_test", "tests/"]):
            if any(kw in f_lower for kw in keywords):
                test_candidates.append(f)
        elif any(kw in f_lower for kw in keywords):
            candidates.append(f)
        elif any(cfg in f_lower for cfg in ["config.py", "settings.py", "application.yaml", "database.py", "datasource"]):
            candidates.append(f)

    # Pick up to 4 source candidates and up to 2 test candidates
    selected_files = candidates[:4] + test_candidates[:2]
    if not selected_files and all_files:
        selected_files = all_files[:3]

    inspected_files: Dict[str, str] = {}
    for file_path in selected_files:
        try:
            content = git_provider.get_file_content(repo_url, file_path, ref=target_branch)
            inspected_files[file_path] = content
            logger.info("Successfully inspected '%s' (%d bytes)", file_path, len(content))
        except Exception as exc:
            logger.warning("Could not inspect file '%s': %s", file_path, exc)

    return {
        "inspected_files": inspected_files,
        "inspected_file_paths": list(inspected_files.keys()),
        "status": "GENERATING_PATCH",
    }
