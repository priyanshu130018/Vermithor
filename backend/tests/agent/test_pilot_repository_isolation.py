import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation, Repair, RepositoryConnection
from backend.app.agent.git.github_provider import GitHubProvider
from backend.app.agent.git.local_provider import LocalGitProvider
from backend.app.agent.schemas.repository import validate_repo_identifier
from backend.app.agent.services.repair_service import RepairService
from backend.app.main import app
from backend.app.common.database import get_db


@pytest.fixture
def auth_headers_org_a():
    """Valid JWT token fixture for Org A."""
    from backend.app.common.security import create_access_token
    token = create_access_token({"sub": "eng_lead_a", "org_id": "vermithor", "role": "engineer"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_org_b():
    """Valid JWT token fixture for Org B."""
    from backend.app.common.security import create_access_token
    token = create_access_token({"sub": "eng_lead_b", "org_id": "internal", "role": "engineer"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_client(db_session: Session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ============================================================================
# 1. Repository Identifier Validation & SSRF / Traversal Protection
# ============================================================================

def test_validate_repo_identifier_accepts_clean_owner_repo():
    assert validate_repo_identifier("vermithor-org/payment-service") == "vermithor-org/payment-service"
    assert validate_repo_identifier("my-team/core.api_v2") == "my-team/core.api_v2"
    assert validate_repo_identifier("https://github.com/vermithor-org/payment-service.git") == "vermithor-org/payment-service"


def test_validate_repo_identifier_blocks_path_traversal():
    with pytest.raises(ValueError, match="Directory traversal attempt detected"):
        validate_repo_identifier("../../etc/passwd")

    with pytest.raises(ValueError, match="Directory traversal attempt detected"):
        validate_repo_identifier("vermithor/../secrets")


def test_validate_repo_identifier_blocks_null_bytes_and_control_chars():
    with pytest.raises(ValueError, match="illegal control characters"):
        validate_repo_identifier("vermithor/repo\x00extra")


def test_validate_repo_identifier_blocks_ssrf_and_private_hosts():
    with pytest.raises(ValueError, match="Prohibited host / SSRF attempt"):
        validate_repo_identifier("http://127.0.0.1/admin/repo")

    with pytest.raises(ValueError, match="Prohibited host / SSRF attempt"):
        validate_repo_identifier("http://localhost:8080/myrepo")

    with pytest.raises(ValueError, match="Prohibited host / SSRF attempt"):
        validate_repo_identifier("http://169.254.169.254/latest/meta-data")


# ============================================================================
# 2. Safe Repository Connection & Enforced Read-Only Mode
# ============================================================================

def test_connect_repository_success_read_only(test_client, auth_headers_org_a):
    payload = {
        "repo_identifier": "vermithor/payment-service",
        "installation_id": "inst_12345",
        "read_only": True,
    }
    resp = test_client.post("/api/v1/agent/repositories/connect", json=payload, headers=auth_headers_org_a)
    assert resp.status_code == 201
    data = resp.json()
    assert data["repo_identifier"] == "vermithor/payment-service"
    assert data["org_id"] == "vermithor"
    assert data["read_only"] is True
    assert data["status"] == "CONNECTED"
    assert data["permissions"] == {"contents": "read", "metadata": "read"}
    assert "Read-Only Pilot Mode" in data["audit_notice"]
    assert data["latest_commit_sha"] is not None


def test_connect_repository_rejects_write_mode(test_client, auth_headers_org_a):
    payload = {
        "repo_identifier": "vermithor/payment-service",
        "read_only": False,
    }
    resp = test_client.post("/api/v1/agent/repositories/connect", json=payload, headers=auth_headers_org_a)
    assert resp.status_code == 422
    assert "read_only" in resp.text


# ============================================================================
# 3. Multi-Tenant Isolation
# ============================================================================

def test_tenant_isolation_org_b_cannot_see_org_a_repositories(test_client, auth_headers_org_a, auth_headers_org_b):
    # Org A connects a repo
    test_client.post(
        "/api/v1/agent/repositories/connect",
        json={"repo_identifier": "vermithor/org-a-private", "read_only": True},
        headers=auth_headers_org_a,
    )

    # Org B lists repositories
    resp_b = test_client.get("/api/v1/agent/repositories", headers=auth_headers_org_b)
    assert resp_b.status_code == 200
    repos_b = resp_b.json()
    assert not any(r["repo_identifier"] == "vermithor/org-a-private" for r in repos_b)


def test_tenant_isolation_org_b_cannot_disconnect_org_a_repository(test_client, auth_headers_org_a, auth_headers_org_b):
    conn_resp = test_client.post(
        "/api/v1/agent/repositories/connect",
        json={"repo_identifier": "vermithor/shared-candidate", "read_only": True},
        headers=auth_headers_org_a,
    )
    conn_id = conn_resp.json()["id"]

    # Org B tries to disconnect Org A's repository connection
    resp_b = test_client.post(f"/api/v1/agent/repositories/{conn_id}/disconnect", headers=auth_headers_org_b)
    assert resp_b.status_code == 404


def test_repair_service_blocks_unauthorized_org_repository(db_session, auth_headers_org_b):
    # Connect repo exclusively for vermithor
    conn = RepositoryConnection(
        org_id="vermithor",
        repo_identifier="vermithor/exclusive-repo",
        read_only=True,
        status="CONNECTED",
    )
    db_session.add(conn)
    db_session.commit()

    service = RepairService()
    from backend.app.agent.schemas.repair import RepairRequest
    req = RepairRequest(
        investigation_key="INV-000001",
        repository_url="vermithor/exclusive-repo",
    )

    # Attempt repair as internal (Org B)
    with pytest.raises(PermissionError, match="Multi-tenant isolation violation"):
        service.run_repair(
            db=db_session,
            req=req,
            user_identity={"sub": "user_b", "org_id": "internal"},
        )


# ============================================================================
# 4. Disconnect / Revocation Flow
# ============================================================================

def test_disconnect_repository_revokes_access(test_client, auth_headers_org_a):
    conn_resp = test_client.post(
        "/api/v1/agent/repositories/connect",
        json={"repo_identifier": "vermithor/disconnect-test", "read_only": True},
        headers=auth_headers_org_a,
    )
    conn_id = conn_resp.json()["id"]

    disc_resp = test_client.post(f"/api/v1/agent/repositories/{conn_id}/disconnect", headers=auth_headers_org_a)
    assert disc_resp.status_code == 200
    assert disc_resp.json()["status"] == "REVOKED"
    assert disc_resp.json()["revoked_at"] is not None

    # Verify endpoint reflects REVOKED status
    ver_resp = test_client.get(f"/api/v1/agent/repositories/{conn_id}/verify", headers=auth_headers_org_a)
    assert ver_resp.status_code == 200
    assert ver_resp.json()["status"] == "REVOKED"
    assert ver_resp.json()["reachable"] is False


def test_repair_service_blocks_revoked_repository(db_session):
    conn = RepositoryConnection(
        org_id="vermithor",
        repo_identifier="vermithor/revoked-test",
        read_only=True,
        status="REVOKED",
    )
    db_session.add(conn)
    db_session.commit()

    service = RepairService()
    from backend.app.agent.schemas.repair import RepairRequest
    req = RepairRequest(
        investigation_key="INV-000001",
        repository_url="vermithor/revoked-test",
    )

    with pytest.raises(PermissionError, match="has been revoked"):
        service.run_repair(
            db=db_session,
            req=req,
            user_identity={"sub": "user_a", "org_id": "vermithor"},
        )


# ============================================================================
# 5. Read-Only Git Provider Safeguards
# ============================================================================

def test_github_provider_read_only_blocks_branch_and_pr_creation():
    provider = GitHubProvider(token="mock_token", read_only=True)

    with pytest.raises(PermissionError, match="read-only pilot mode.*create_branch"):
        provider.create_branch("vermithor/payment-service", "repair/my-branch")

    with pytest.raises(PermissionError, match="read-only pilot mode.*create_pull_request"):
        provider.create_pull_request("vermithor/payment-service", "title", "body", "repair/my-branch")


def test_local_git_provider_read_only_blocks_branch_and_pr_creation():
    provider = LocalGitProvider(read_only=True)

    with pytest.raises(PermissionError, match="read-only pilot mode.*create_branch"):
        provider.create_branch("local", "repair/my-branch")

    with pytest.raises(PermissionError, match="read-only pilot mode.*create_pull_request"):
        provider.create_pull_request("local", "title", "body", "repair/my-branch")


# ============================================================================
# 6. Rate Limit Handling
# ============================================================================

def test_github_provider_rate_limit_handling():
    provider = GitHubProvider(token="mock_token", read_only=True)

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"X-RateLimit-Remaining": "0"}

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(PermissionError, match="rate limit exceeded"):
            provider.get_latest_commit_sha("vermithor/payment-service", "main")


# ============================================================================
# 7. Traceability and Pilot Artifact Guarantees in Repair Workflow
# ============================================================================

def test_repair_workflow_produces_read_only_pilot_report(db_session):
    inv = Investigation(
        investigation_key="INV-000042",
        incident_key="INC-2026-1042",
        target_service="payment-service",
        confidence=0.92,
        leading_hypothesis="HikariCP connection pool exhausted",
        model_provider="anthropic",
        status="COMPLETED",
        evidence_json=[{"id": "EV-01", "description": "HikariCP pool size 10 is exhausted"}],
    )
    db_session.add(inv)
    db_session.commit()

    fixture_dir = Path(__file__).parent.parent / "fixtures" / "payment_service"
    git_prov = LocalGitProvider(root_dir=fixture_dir, read_only=True)

    service = RepairService()
    from backend.app.agent.schemas.repair import RepairRequest
    req = RepairRequest(
        investigation_key="INV-000042",
        repository_url="local",
        auto_create_pr=True,  # Even if requested, pilot mode must strictly suppress PR
    )

    resp = service.run_repair(
        db=db_session,
        req=req,
        git_provider=git_prov,
        repo_root=fixture_dir,
        user_identity={"sub": "eng_lead", "org_id": "vermithor"},
    )

    # Verify Pilot Safeguards
    assert resp.is_read_only_pilot is True
    assert "Read-Only Pilot Mode" in resp.pilot_audit_notice
    assert resp.pull_request_url is None
    assert resp.repair_branch is None

    # Verify Traceability
    assert resp.base_commit is not None
    assert resp.evidence_citations is not None
    assert resp.patch_hash is not None
    assert resp.validation_status.value == "VALIDATED"
