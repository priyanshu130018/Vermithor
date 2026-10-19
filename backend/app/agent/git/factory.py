import os
from typing import Optional

from backend.app.agent.git.base import GitProvider
from backend.app.agent.git.github_provider import GitHubProvider
from backend.app.agent.git.local_provider import LocalGitProvider


class GitProviderFactory:
    """Factory for instantiating the appropriate GitProvider based on repository identifier."""

    @staticmethod
    def get_provider(
        repository_url: Optional[str] = None,
        token: Optional[str] = None,
    ) -> GitProvider:
        repo_str = (repository_url or "").strip()
        github_token = token or os.getenv("GITHUB_TOKEN")

        # Remote GitHub URLs or owner/repo format when token is explicitly set
        if ("github.com" in repo_str or "/" in repo_str) and not os.path.exists(repo_str) and github_token:
            return GitHubProvider(token=github_token)

        # Default to safe LocalGitProvider, respecting local path if provided
        if repo_str:
            from pathlib import Path
            cand_p = Path(repo_str)
            if cand_p.is_absolute() and cand_p.exists() and cand_p.is_dir():
                return LocalGitProvider(root_dir=cand_p.resolve())
            rel_p = (Path.cwd() / repo_str).resolve()
            if rel_p.exists() and rel_p.is_dir():
                return LocalGitProvider(root_dir=rel_p)

        return LocalGitProvider()
