from datetime import datetime
import re
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_repo_identifier(repo_str: str) -> str:
    """
    Validate repository identifier format:
    Requires standard format 'owner/repo' or clean HTTPS URL pointing to github.com.
    Strictly rejects directory traversal, null bytes, control characters, and SSRF loopback/private IPs.
    """
    if not repo_str or not repo_str.strip():
        raise ValueError("Repository identifier cannot be empty")

    cleaned = repo_str.strip()

    # Block null bytes and illegal control characters
    if "\x00" in cleaned or any(ord(c) < 32 for c in cleaned):
        raise ValueError("Repository identifier contains illegal control characters")

    # Block directory traversal sequences
    if ".." in cleaned or "\\." in cleaned:
        raise ValueError("Directory traversal attempt detected in repository identifier")

    # Block localhost / private IP SSRF patterns
    ssrf_blocklist = [
        "localhost",
        "127.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "[::1]",
        "10.",
        "192.168.",
        "172.16.",
    ]
    cleaned_lower = cleaned.lower()
    for blocked in ssrf_blocklist:
        if blocked in cleaned_lower:
            raise ValueError(f"Prohibited host / SSRF attempt detected in repository identifier: '{blocked}'")

    # Handle full HTTPS URLs
    if cleaned_lower.startswith("http://") or cleaned_lower.startswith("https://"):
        if not cleaned_lower.startswith("https://github.com/"):
            raise ValueError("Only secure 'https://github.com/owner/repo' URLs are supported for remote repositories")
        path_part = cleaned[len("https://github.com/"):].rstrip("/")
        if path_part.endswith(".git"):
            path_part = path_part[:-4]
        cleaned = path_part

    # Validate standard owner/repo format
    parts = cleaned.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Repository identifier must be in 'owner/repo' format (e.g. 'vermithor-org/payment-service')")

    owner, repo = parts[0], parts[1].replace(".git", "")
    ident_pattern = re.compile(r"^[a-zA-Z0-9_.-]+$")
    if not ident_pattern.match(owner) or not ident_pattern.match(repo):
        raise ValueError(f"Repository identifier '{cleaned}' contains invalid characters (allowed: alphanumeric, _, ., -)")

    return f"{owner}/{repo}"


class RepoConnectRequest(BaseModel):
    """Payload to safely connect a repository in read-only pilot mode."""
    repo_identifier: str = Field(..., description="Repository in 'owner/repo' format or GitHub URL")
    installation_id: Optional[str] = Field(None, description="GitHub App installation ID if connecting via GitHub App")
    read_only: bool = Field(True, description="Strictly enforced read-only mode for pilot")

    @field_validator("repo_identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        return validate_repo_identifier(v)

    @field_validator("read_only")
    @classmethod
    def enforce_read_only(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Write mode is strictly disabled during the controlled pilot. 'read_only' must be true.")
        return True


class RepoConnectResponse(BaseModel):
    """Metadata response confirming repository connection."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    org_id: str
    repo_identifier: str
    installation_id: Optional[str] = None
    read_only: bool = True
    status: str
    connected_by: Optional[str] = None
    connected_at: datetime
    revoked_at: Optional[datetime] = None
    latest_commit_sha: Optional[str] = None
    permissions: Dict[str, str] = Field(default_factory=lambda: {"contents": "read", "metadata": "read"})
    audit_notice: str = "Connected in Read-Only Pilot Mode: write operations (branch creation, PR creation, push) are strictly prohibited."


class RepoVerifyResponse(BaseModel):
    """Health and permissions probe response for connected repository."""
    repo_identifier: str
    status: str
    reachable: bool
    read_only: bool = True
    rate_limit_remaining: Optional[int] = None
    latest_commit_sha: Optional[str] = None
    message: str


class RepoDisconnectResponse(BaseModel):
    """Response returned upon revoking a repository connection."""
    id: uuid.UUID
    repo_identifier: str
    status: str = "REVOKED"
    revoked_at: datetime
    message: str


class RepositorySummaryResponse(BaseModel):
    """Summary item for tenant's connected repositories list."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: uuid.UUID
    org_id: str
    repo_identifier: str
    installation_id: Optional[str] = None
    read_only: bool = True
    status: str
    connected_by: Optional[str] = None
    connected_at: datetime
    revoked_at: Optional[datetime] = None
