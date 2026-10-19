import logging
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.agent.graph.repair_state import RepairState
from backend.app.agent.runner.sandbox import IsolatedTestRunner
from backend.app.agent.schemas.repair import ValidationStatus

logger = logging.getLogger(__name__)


def run_isolated_validation_node(
    state: RepairState,
    test_runner: Optional[IsolatedTestRunner] = None,
    repo_root: Optional[Path] = None,
    git_provider: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Apply the proposed patch to a disposable sandbox copy of the repository and
    execute tests in an isolated subprocess with stripped environment variables.
    """
    patch = state.get("proposed_patch") or ""
    repo_url = state.get("repository_url") or "workspace"
    custom_cmd = state.get("custom_test_command")
    runner = test_runner or IsolatedTestRunner(timeout_seconds=30.0)

    # Determine source directory
    if repo_root and repo_root.exists():
        source_path = repo_root
    elif repo_url and Path(repo_url).is_absolute() and Path(repo_url).exists():
        source_path = Path(repo_url).resolve()
    elif repo_url and (Path.cwd() / repo_url).exists():
        source_path = (Path.cwd() / repo_url).resolve()
    elif hasattr(git_provider, "_resolve_repo_root") and repo_url:
        source_path = git_provider._resolve_repo_root(repo_url)
    elif hasattr(git_provider, "root_dir") and git_provider.root_dir and git_provider.root_dir.exists():
        source_path = git_provider.root_dir
    else:
        fixture_cand = (Path.cwd() / "backend" / "tests" / "fixtures" / "payment_service").resolve()
        if "payment" in (state.get("target_service") or "").lower() and fixture_cand.exists():
            source_path = fixture_cand
        else:
            source_path = Path.cwd().resolve()

    logger.info("Executing isolated test validation on '%s' with command '%s'", source_path, custom_cmd or "pytest")

    result = runner.run_validation(
        source_dir=source_path,
        patch_diff=patch,
        test_command=custom_cmd,
    )

    logger.info(
        "Isolated validation finished: status=%s, total=%d, passed=%d, failed=%d, duration=%.1fms",
        result.status.value,
        result.total_tests,
        result.passed,
        result.failed,
        result.duration_ms,
    )

    return {
        "validation_status": result.status.value,
        "validation_result": result.model_dump(),
        "test_commands": result.commands_run,
    }
