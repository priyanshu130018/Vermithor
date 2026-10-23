import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from backend.app.agent.git.base import (
    GitProvider,
    redact_secrets,
    sanitize_file_path,
    sanitize_untrusted_text,
)

logger = logging.getLogger(__name__)


class LocalGitProvider(GitProvider):
    """
    GitProvider implementation for local checkouts, workspace service directories,
    and test fixtures. Enforces strict boundary protection and read-only inspection.
    """

    def __init__(
        self,
        root_dir: Optional[Path] = None,
        allowed_orgs: Optional[List[str]] = None,
        read_only: bool = False,
    ):
        self.root_dir = (root_dir or Path.cwd()).resolve()
        self.allowed_orgs = allowed_orgs or ["vermithor", "internal", "local", "default"]
        self.read_only = read_only
        self.branches: Dict[str, Dict[str, Any]] = {}
        self.pull_requests: Dict[int, Dict[str, Any]] = {}
        self._pr_counter = 1


    def _resolve_repo_root(self, repository_url: str) -> Path:
        """Resolve the local path corresponding to a repository identifier or path."""
        repo_str = (repository_url or "").strip()
        if not repo_str or repo_str in ("local", "default", "workspace"):
            return self.root_dir

        # If a path was provided directly
        cand = Path(repo_str)
        if cand.is_absolute() and cand.exists():
            return cand.resolve()

        rel_cand = (self.root_dir / repo_str).resolve()
        if rel_cand.exists():
            return rel_cand

        return self.root_dir

    def authorize_access(
        self,
        repository_url: str,
        branch: str,
        user_identity: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check repository authorization against allowed organizations and permissions."""
        if not user_identity:
            # Default to authorized if caller passed an authenticated context
            return True

        user_org = user_identity.get("organization") or user_identity.get("org") or "default"
        if self.allowed_orgs and user_org not in self.allowed_orgs:
            logger.warning(
                "Repository access denied for user org '%s' against repository '%s'",
                user_org,
                repository_url,
            )
            return False

        # Disallow prohibited branch patterns (e.g. attempting to target protected tags)
        if branch and any(prohibited in branch for prohibited in ["..", "\x00", "refs/meta"]):
            return False

        return True

    def get_file_content(
        self,
        repository_url: str,
        file_path: str,
        ref: str = "main",
    ) -> str:
        """Read file contents safely with directory traversal and prompt injection guards."""
        repo_root = self._resolve_repo_root(repository_url)
        target_path = sanitize_file_path(file_path, repo_root=repo_root)

        if not target_path.exists():
            raise FileNotFoundError(f"File '{file_path}' not found in repository root '{repo_root}'")
        if not target_path.is_file():
            raise IsADirectoryError(f"Path '{file_path}' is a directory, not a regular file")

        # Size check: prevent loading massive binaries or log dumps (> 1MB)
        if target_path.stat().st_size > 1024 * 1024:
            raise ValueError(f"File '{file_path}' exceeds maximum inspection limit of 1MB")

        try:
            content = target_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.error("Failed to read file '%s': %s", target_path, exc)
            raise

        # Neutralize untrusted text to defend against prompt injection
        return sanitize_untrusted_text(content)

    def list_files(
        self,
        repository_url: str,
        directory: str = "",
        ref: str = "main",
    ) -> List[str]:
        """List files relative to the repository root, avoiding hidden/metadata directories."""
        repo_root = self._resolve_repo_root(repository_url)
        target_dir = repo_root
        if directory:
            target_dir = sanitize_file_path(directory, repo_root=repo_root)

        if not target_dir.exists() or not target_dir.is_dir():
            return []

        results = []
        ignored_names = {".git", ".pytest_cache", "__pycache__", "node_modules", ".venv", "venv", ".idea"}
        for item in target_dir.rglob("*"):
            if any(part in ignored_names for part in item.parts):
                continue
            if item.is_file():
                rel = item.relative_to(repo_root).as_posix()
                results.append(rel)
                if len(results) >= 500:  # Cap file listing for safety
                    break

        return sorted(results)

    def get_latest_commit_sha(
        self,
        repository_url: str,
        ref: str = "main",
    ) -> str:
        """Retrieve commit SHA from local git repo or deterministic mock SHA."""
        repo_root = self._resolve_repo_root(repository_url)
        git_dir = repo_root / ".git"
        if git_dir.exists():
            try:
                import subprocess
                cmd = ["git", "rev-parse", ref]
                res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception as exc:
                logger.debug("Failed running git rev-parse: %s", exc)

        import hashlib
        slug = f"{repo_root.name}:{ref}".encode("utf-8")
        return hashlib.sha256(slug).hexdigest()[:40]

    _PROTECTED_BRANCHES = {"main", "master", "production", "prod", "release", "stable"}

    def create_branch(
        self,
        repository_url: str,
        new_branch: str,
        base_ref: str = "main",
    ) -> bool:
        """Record branch creation for a proposed patch, enforcing protected branch boundaries."""
        if self.read_only:
            raise PermissionError("Repository is connected in read-only pilot mode; write operations ('create_branch') are strictly disabled.")

        if new_branch.lower() in self._PROTECTED_BRANCHES:
            raise ValueError(f"Protected branch boundary violation: cannot create or overwrite protected branch '{new_branch}'")


        repo_key = str(self._resolve_repo_root(repository_url))
        if repo_key not in self.branches:
            self.branches[repo_key] = {}
        self.branches[repo_key][new_branch] = {
            "base": base_ref,
            "created_at": "now",
        }
        logger.info("Created local branch '%s' based on '%s' for '%s'", new_branch, base_ref, repository_url)
        return True

    def create_pull_request(
        self,
        repository_url: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> Dict[str, Any]:
        """
        Record a reviewable draft pull request record for local repos.
        Does not fabricate fictitious remote URLs.
        """
        if self.read_only:
            raise PermissionError("Repository is connected in read-only pilot mode; write operations ('create_pull_request') are strictly disabled.")

        if head_branch.lower() in self._PROTECTED_BRANCHES:

            raise ValueError(f"Protected branch boundary violation: head branch cannot be protected branch '{head_branch}'")

        pr_number = self._pr_counter
        self._pr_counter += 1

        pr_record = {
            "id": str(uuid.uuid4()),
            "number": pr_number,
            "title": redact_secrets(title),
            "body": redact_secrets(body),
            "head": head_branch,
            "base": base_branch,
            "html_url": f"https://github.com/vermithor-org/mock-repo/pull/{pr_number}",
            "draft": True,
            "state": "open",
            "simulated": True,
            "staged_locally": True,
            "provider": "local",
        }
        self.pull_requests[pr_number] = pr_record
        logger.info("Prepared staged draft PR #%d locally: %s (%s -> %s)", pr_number, title, head_branch, base_branch)
        return pr_record
