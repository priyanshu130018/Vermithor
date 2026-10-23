import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx

from backend.app.agent.git.base import (
    GitProvider,
    redact_secrets,
    sanitize_file_path,
    sanitize_untrusted_text,
)

logger = logging.getLogger(__name__)


class GitHubProvider(GitProvider):
    """
    GitProvider implementation for GitHub remote repositories.
    Uses least-privilege token authentication, read-only inspection by default,
    and opens draft pull requests only when authorized.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = "https://api.github.com",
        allowed_orgs: Optional[List[str]] = None,
        read_only: bool = True,
    ):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.base_url = base_url.rstrip("/")
        self.allowed_orgs = allowed_orgs or ["vermithor", "internal", "default"]
        self.read_only = read_only
        self.timeout = 15.0


    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Vermithor-Code-Repair-Agent/1.0",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def _parse_repo(self, repository_url: str) -> tuple[str, str]:
        """Extract owner and repo from URL or string like 'owner/repo' or 'https://github.com/owner/repo'."""
        cleaned = repository_url.strip().rstrip("/")
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            match = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?$", cleaned)
            if match:
                return match.group(1), match.group(2)
        parts = cleaned.split("/")
        if len(parts) == 2:
            return parts[0], parts[1].replace(".git", "")
        return "vermithor", cleaned

    def authorize_access(
        self,
        repository_url: str,
        branch: str,
        user_identity: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Verify whether the user has access to the specified repository and organization."""
        owner, _ = self._parse_repo(repository_url)
        if self.allowed_orgs and owner not in self.allowed_orgs and "all" not in self.allowed_orgs:
            logger.warning("Repository owner '%s' is not in allowed organizations list", owner)
            return False

        if not self.token:
            # If no token configured, only public inspection or mocked access is allowed
            logger.info("No GITHUB_TOKEN configured; proceeding in read-only / mock mode")
            return True

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    f"{self.base_url}/repos/{owner}/{self._parse_repo(repository_url)[1]}",
                    headers=self._get_headers(),
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("GitHub authorization check error: %s", redact_secrets(str(exc)))
            return False

    def get_file_content(
        self,
        repository_url: str,
        file_path: str,
        ref: str = "main",
    ) -> str:
        """Retrieve file content from GitHub using the contents API."""
        owner, repo = self._parse_repo(repository_url)
        cleaned_path = str(sanitize_file_path(file_path)).replace("\\", "/")

        if not self.token:
            raise PermissionError("GITHUB_TOKEN not configured for remote repository inspection")

        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{cleaned_path}"
        params = {"ref": ref}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._get_headers(), params=params)
                if resp.status_code == 404:
                    raise FileNotFoundError(f"File '{cleaned_path}' not found in GitHub repository {owner}/{repo}@{ref}")
                if resp.status_code in (403, 429):
                    limit_rem = resp.headers.get("X-RateLimit-Remaining")
                    logger.warning("GitHub rate limit encountered while querying file content: remaining=%s", limit_rem)
                    raise PermissionError(f"GitHub API rate limit exceeded or access forbidden (remaining: {limit_rem})")
                resp.raise_for_status()

                data = resp.json()
                import base64
                encoded = data.get("content", "")
                decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
                return sanitize_untrusted_text(decoded)
        except Exception as exc:
            logger.error("GitHub get_file_content failed for %s: %s", cleaned_path, redact_secrets(str(exc)))
            raise

    def list_files(
        self,
        repository_url: str,
        directory: str = "",
        ref: str = "main",
    ) -> List[str]:
        """List repository files via GitHub tree API."""
        owner, repo = self._parse_repo(repository_url)
        if not self.token:
            return []

        url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._get_headers())
                if resp.status_code != 200:
                    return []
                tree = resp.json().get("tree", [])
                files = [item["path"] for item in tree if item.get("type") == "blob"]
                if directory:
                    prefix = directory.rstrip("/") + "/"
                    files = [f for f in files if f.startswith(prefix)]
                return sorted(files[:500])
        except Exception as exc:
            logger.warning("GitHub list_files failed: %s", redact_secrets(str(exc)))
            return []

    def get_latest_commit_sha(
        self,
        repository_url: str,
        ref: str = "main",
    ) -> str:
        """Retrieve commit SHA for the specified branch/ref on GitHub."""
        owner, repo = self._parse_repo(repository_url)
        if not self.token:
            # Deterministic pilot mock SHA when remote GitHub token is absent
            import hashlib
            slug = f"{owner}/{repo}:{ref}".encode("utf-8")
            return hashlib.sha256(slug).hexdigest()[:40]

        url = f"{self.base_url}/repos/{owner}/{repo}/commits/{ref}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._get_headers())
                if resp.status_code in (403, 429):
                    limit_rem = resp.headers.get("X-RateLimit-Remaining")
                    logger.warning("GitHub rate limit encountered while querying commit SHA: remaining=%s", limit_rem)
                    raise PermissionError(f"GitHub API rate limit exceeded or access forbidden (remaining: {limit_rem})")
                resp.raise_for_status()
                return resp.json()["sha"]
        except Exception as exc:
            logger.error("GitHub get_latest_commit_sha failed for %s/%s@%s: %s", owner, repo, ref, redact_secrets(str(exc)))
            raise

    def check_rate_limit(self) -> Dict[str, Any]:
        """Check GitHub API rate limit status without leaking credentials."""
        if not self.token:
            return {"limit": 60, "remaining": 60, "reset": 0, "mock": True}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/rate_limit", headers=self._get_headers())
                if resp.status_code == 200:
                    rate = resp.json().get("rate", {})
                    return {
                        "limit": rate.get("limit", 5000),
                        "remaining": rate.get("remaining", 5000),
                        "reset": rate.get("reset", 0),
                        "mock": False,
                    }
                return {"limit": 60, "remaining": 0, "reset": 0, "mock": False}
        except Exception as exc:
            logger.warning("Failed to check GitHub rate limit: %s", redact_secrets(str(exc)))
            return {"limit": 0, "remaining": 0, "reset": 0, "error": redact_secrets(str(exc))}

    _PROTECTED_BRANCHES = {"main", "master", "production", "prod", "release", "stable"}

    def create_branch(
        self,
        repository_url: str,
        new_branch: str,
        base_ref: str = "main",
    ) -> bool:
        """Create a new ref on GitHub, strictly preventing write in read-only pilot mode or to protected branches."""
        if self.read_only:
            raise PermissionError("Repository is connected in read-only pilot mode; write operations ('create_branch') are strictly disabled.")

        if new_branch.lower() in self._PROTECTED_BRANCHES:
            raise ValueError(f"Protected branch boundary violation: cannot create or overwrite protected branch '{new_branch}'")

        owner, repo = self._parse_repo(repository_url)
        if not self.token:
            logger.warning("Cannot create branch: GITHUB_TOKEN not configured")
            return False

        try:
            with httpx.Client(timeout=self.timeout) as client:
                # Get base SHA
                ref_resp = client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/git/ref/heads/{base_ref}",
                    headers=self._get_headers(),
                )
                ref_resp.raise_for_status()
                sha = ref_resp.json()["object"]["sha"]

                # Create ref
                create_resp = client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/git/refs",
                    headers=self._get_headers(),
                    json={"ref": f"refs/heads/{new_branch}", "sha": sha},
                )
                return create_resp.status_code == 201
        except Exception as exc:
            logger.error("Failed to create GitHub branch '%s': %s", new_branch, redact_secrets(str(exc)))
            return False

    def create_pull_request(
        self,
        repository_url: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> Dict[str, Any]:
        """Create a draft pull request on GitHub, strictly preventing write in read-only pilot mode."""
        if self.read_only:
            raise PermissionError("Repository is connected in read-only pilot mode; write operations ('create_pull_request') are strictly disabled.")

        if head_branch.lower() in self._PROTECTED_BRANCHES:
            raise ValueError(f"Protected branch boundary violation: head branch cannot be protected branch '{head_branch}'")

        owner, repo = self._parse_repo(repository_url)
        if not self.token:
            return {
                "number": 0,
                "html_url": f"https://github.com/{owner}/{repo}/compare/{base_branch}...{head_branch}",
                "draft": True,
                "simulated": True,
            }

        payload = {
            "title": redact_secrets(title),
            "body": redact_secrets(body),
            "head": head_branch,
            "base": base_branch,
            "draft": True,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls",
                    headers=self._get_headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "number": data.get("number"),
                    "html_url": data.get("html_url"),
                    "draft": data.get("draft", True),
                    "state": data.get("state"),
                }
        except Exception as exc:
            logger.error("Failed to create pull request on GitHub: %s", redact_secrets(str(exc)))
            return {
                "error": redact_secrets(str(exc)),
                "html_url": f"https://github.com/{owner}/{repo}/compare/{base_branch}...{head_branch}",
                "simulated": True,
            }

