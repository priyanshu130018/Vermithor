from abc import ABC, abstractmethod
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Patterns for detecting potential prompt injections inside untrusted code / repository text
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"override\s+system\s+(prompt|instructions)", re.IGNORECASE),
    re.compile(r"<system>.*?</system>", re.IGNORECASE | re.DOTALL),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now", re.IGNORECASE),
    re.compile(r"new\s+system\s+directive:", re.IGNORECASE),
]

# Patterns for identifying and redacting credentials / secrets
_SECRET_PATTERNS = [
    re.compile(r"(ghp_[a-zA-Z0-9]{36,})"),
    re.compile(r"(github_pat_[a-zA-Z0-9_]{50,})"),
    re.compile(r"(bearer\s+ey[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,})", re.IGNORECASE),
    re.compile(r"(password\s*[:=]\s*['\"][^'\"]+['\"])", re.IGNORECASE),
    re.compile(r"(postgres(?:ql)?:\/\/[^:]+:[^@]+@[^\s/]+(?:\/[^\s?]*)?)", re.IGNORECASE),
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    re.compile(r"(hf_[a-zA-Z0-9]{34,})"),
]


def sanitize_file_path(file_path: str, repo_root: Optional[Path] = None) -> Path:
    """
    Sanitize and validate a file path to prevent directory traversal and unauthorized filesystem access.
    
    Raises:
        ValueError: If path attempts to escape the root or contains invalid control sequences.
    """
    if not file_path or not file_path.strip():
        raise ValueError("File path cannot be empty")

    cleaned = file_path.strip().replace("\\", "/")

    # Check for null bytes or control characters
    if "\x00" in cleaned or any(ord(c) < 32 for c in cleaned if c not in ("\t", "\n")):
        raise ValueError(f"Path contains illegal control characters: {file_path}")

    # Check for obvious traversal sequences
    parts = cleaned.split("/")
    if ".." in parts:
        raise ValueError(f"Directory traversal detected in path: {file_path}")

    # Prevent absolute paths escaping boundaries
    if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
        if repo_root:
            try:
                resolved = Path(cleaned).resolve()
                repo_root_resolved = repo_root.resolve()
                if not str(resolved).startswith(str(repo_root_resolved)):
                    raise ValueError(f"Path escapes repository root: {file_path}")
                return resolved
            except Exception as exc:
                raise ValueError(f"Invalid repository path: {file_path}") from exc
        else:
            raise ValueError(f"Absolute paths not permitted without explicit repo root: {file_path}")

    if repo_root:
        full_path = (repo_root / cleaned).resolve()
        repo_root_resolved = repo_root.resolve()
        if not str(full_path).startswith(str(repo_root_resolved)):
            raise ValueError(f"Path escapes repository root: {file_path}")
        return full_path

    return Path(cleaned)


def sanitize_untrusted_text(content: str) -> str:
    """
    Sanitize source code, comments, or commit messages to neutralize embedded prompt injection attempts.
    Preserves code structure while escaping adversarial instructions.
    """
    if not content:
        return ""

    sanitized = content
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(sanitized):
            logger.warning("Potential prompt injection pattern detected in untrusted repository content")
            sanitized = pattern.sub("[REDACTED_ADVERSARIAL_INSTRUCTION]", sanitized)

    return sanitized


def redact_secrets(text: str) -> str:
    """
    Redact access tokens, private keys, passwords, and sensitive credentials from logs or artifacts.
    """
    if not text:
        return ""

    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)

    return redacted


class GitProvider(ABC):
    """Abstract interface for authorized, least-privilege repository inspection and branch management."""

    @abstractmethod
    def authorize_access(
        self,
        repository_url: str,
        branch: str,
        user_identity: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Verify whether the authenticated user has permission to access the repository and branch."""
        pass

    @abstractmethod
    def get_file_content(
        self,
        repository_url: str,
        file_path: str,
        ref: str = "main",
    ) -> str:
        """Retrieve the text content of a file in read-only mode."""
        pass

    @abstractmethod
    def list_files(
        self,
        repository_url: str,
        directory: str = "",
        ref: str = "main",
    ) -> List[str]:
        """List files in the specified directory."""
        pass

    @abstractmethod
    def create_branch(
        self,
        repository_url: str,
        new_branch: str,
        base_ref: str = "main",
    ) -> bool:
        """Create a new branch for the proposed repair."""
        pass

    @abstractmethod
    def create_pull_request(
        self,
        repository_url: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> Dict[str, Any]:
        """Create a reviewable draft pull request for human evaluation."""
        pass
