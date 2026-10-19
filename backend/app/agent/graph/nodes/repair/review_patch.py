import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from backend.app.agent.git.base import _PROMPT_INJECTION_PATTERNS, _SECRET_PATTERNS
from backend.app.agent.graph.repair_state import RepairState

logger = logging.getLogger(__name__)

# Files that patches are strictly forbidden from modifying
_FORBIDDEN_FILES = {
    ".env",
    "docker-compose.yml",
    "dockerfile",
    "alembic.ini",
    "id_rsa",
    "authorized_keys",
    ".aws/credentials",
    ".github/workflows",
    "security.md",
}

# Dependency definition files that AI patches cannot modify without explicit human authorization
_DEPENDENCY_FILES = {
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pom.xml",
    "build.gradle",
    "go.mod",
    "go.sum",
    "gemfile",
    "gemfile.lock",
    "setup.py",
    "pipfile",
}

# Whitelist of permissible file extensions for code repairs
_ALLOWED_FILE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".java",
    ".rs",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".sql",
    ".ini",
    ".cfg",
    ".conf",
}

# Suspicious code patterns (arbitrary shell execution, network calls to raw IPs)
_SUSPICIOUS_CODE_PATTERNS = [
    re.compile(r"os\.system\("),
    re.compile(r"subprocess\.call\(.*shell\s*=\s*True"),
    re.compile(r"eval\("),
    re.compile(r"exec\("),
    re.compile(r"curl\s+http"),
    re.compile(r"wget\s+http"),
    re.compile(r"__import__\("),
    re.compile(r"open\(.*['\"][wa\+]['\"].*\/etc\/"),
]


def review_patch_node(state: RepairState, settings: Optional[Any] = None) -> Dict[str, Any]:
    """
    Review proposed patch for syntax validity, scope bounding, secret exposure,
    prompt injection, dependency changes, and suspicious system-level calls.
    """
    patch = state.get("proposed_patch") or ""
    files_changed = state.get("files_changed") or []
    target_service = (state.get("target_service") or "").lower().replace("-", "").replace("_", "")
    inspected_files = state.get("inspected_files") or []
    review_notes: List[str] = []
    is_clean = True

    max_files = getattr(settings, "AGENT_REPAIR_MAX_CHANGED_FILES", 3) if settings else 3
    max_lines = getattr(settings, "AGENT_REPAIR_MAX_PATCH_LINES", 150) if settings else 150

    if not patch.strip():
        return {
            "patch_review_passed": False,
            "review_notes": ["Patch proposal is empty"],
            "status": "VALIDATION_FAILED",
        }

    # 1. Syntax check
    if not (patch.startswith("--- ") or "\n--- " in patch) or "+++ " not in patch:
        review_notes.append("Malformed patch: missing unified diff headers (--- / +++)")
        is_clean = False

    # Check for binary diff indicators
    if "GIT binary patch" in patch or "Binary files differ" in patch:
        review_notes.append("Security violation: patch contains unexpected binary diff data")
        is_clean = False

    # 2. Patch line size check
    patch_lines = patch.splitlines()
    if len(patch_lines) > max_lines:
        review_notes.append(f"Scope violation: patch size ({len(patch_lines)} lines) exceeds maximum limit of {max_lines} lines")
        is_clean = False

    # 3. Scope check: Limit number of modified files
    if len(files_changed) > max_files:
        review_notes.append(f"Scope violation: proposed patch touches {len(files_changed)} files (max allowed: {max_files})")
        is_clean = False

    # 4. Target Service Boundary Check
    if target_service and target_service != "unknown":
        for f in files_changed:
            f_norm = f.lower().replace("-", "").replace("_", "")
            # If path indicates a multi-service repo structure (e.g., services/order-service or apps/payment)
            for part in f.lower().replace("\\", "/").split("/"):
                part_norm = part.replace("-", "").replace("_", "")
                if part_norm.endswith("service") or part_norm.endswith("api") or part_norm.endswith("app"):
                    if target_service not in part_norm and part_norm not in target_service:
                        review_notes.append(
                            f"Scope violation: patch modifies file '{f}' belonging to unrelated service '{part}' "
                            f"(authorized target: '{state.get('target_service')}')"
                        )
                        is_clean = False
                        break

    # 5. File Extension Whitelist & Forbidden Files Check
    for f in files_changed:
        f_lower = f.lower().replace("\\", "/")
        file_name = Path(f_lower).name
        file_ext = Path(f_lower).suffix

        # Whitelist extension
        if file_ext and file_ext not in _ALLOWED_FILE_EXTENSIONS:
            review_notes.append(f"Security violation: proposed patch modifies disallowed file type '{file_ext}' on '{f}'")
            is_clean = False

        # Dependency modification guard
        if file_name in _DEPENDENCY_FILES or any(dep in f_lower for dep in _DEPENDENCY_FILES):
            review_notes.append(f"Security violation: patch modifies dependency definition or lockfile '{f}' without authorization")
            is_clean = False

        # Forbidden sensitive / infrastructure files
        if any(forbid in f_lower for forbid in _FORBIDDEN_FILES):
            review_notes.append(f"Security violation: proposed patch attempts to modify sensitive file '{f}'")
            is_clean = False

    # 6. Secret exposure check
    for pat in _SECRET_PATTERNS:
        if pat.search(patch):
            review_notes.append("Security violation: patch introduces suspected hardcoded secret or token")
            is_clean = False
            break

    # 7. Prompt injection / adversarial instruction check
    for pat in _PROMPT_INJECTION_PATTERNS:
        if pat.search(patch):
            review_notes.append("Security violation: patch contains suspected adversarial prompt injection text")
            is_clean = False
            break

    # 8. Suspicious dangerous function check in added lines
    for pat in _SUSPICIOUS_CODE_PATTERNS:
        added_lines = [l for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
        for al in added_lines:
            if pat.search(al):
                review_notes.append(f"Security violation: patch introduces suspicious operation: {al.strip()[:60]}")
                is_clean = False
                break

    # 9. Evidence & Inspected files correlation check
    if inspected_files and files_changed:
        inspected_normalized = {Path(p.replace("\\", "/")).name for p in inspected_files}
        changed_normalized = {Path(p.replace("\\", "/")).name for p in files_changed}
        if not changed_normalized.intersection(inspected_normalized):
            review_notes.append(
                f"Grounding violation: patch modifies files {list(changed_normalized)} that were not in inspected files "
                f"{list(inspected_normalized)}"
            )
            is_clean = False

    if is_clean:
        logger.info("Patch review passed: %d file(s) changed, no security anomalies detected", len(files_changed))
        review_notes.append("Patch syntax valid, scope bounded, and verified free of hardcoded secrets and dependency tampering.")
    else:
        logger.warning("Patch review rejected: %s", review_notes)

    return {
        "patch_review_passed": is_clean,
        "review_notes": review_notes,
    }
