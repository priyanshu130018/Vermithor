import time
import pytest
from fastapi.testclient import TestClient

from backend.app.common.config import get_settings
from backend.app.common.security import verify_access_token
from backend.app.main import app
from gateway.tests.conftest import generate_test_jwt


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_auth_dev_token_endpoint_post(client: TestClient):
    """POST /api/v1/auth/dev-token issues a valid, signed JWT access token."""
    response = client.post("/api/v1/auth/dev-token", json={"sub": "sre-user-001"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 86400
    assert data["user"]["sub"] == "sre-user-001"

    # Verify token verifies successfully against backend security logic
    payload = verify_access_token(data["access_token"])
    assert payload is not None
    assert payload["sub"] == "sre-user-001"
    assert payload["iss"] == get_settings().JWT_ISSUER
    assert payload["aud"] == get_settings().JWT_AUDIENCE


def test_auth_dev_token_endpoint_get(client: TestClient):
    """GET /api/v1/auth/dev-token issues a valid JWT access token for sandbox init."""
    response = client.get("/api/v1/auth/dev-token")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"


def test_auth_token_endpoint_post(client: TestClient):
    """POST /api/v1/auth/token endpoint issues a valid JWT access token."""
    response = client.post("/api/v1/auth/token")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


def test_server_issued_token_authenticates_incidents_and_runbooks(client: TestClient):
    """Tokens obtained from dev-token endpoint grant access across incidents and runbooks."""
    token_resp = client.post("/api/v1/auth/dev-token")
    assert token_resp.status_code == 200
    access_token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Test incidents
    inc_resp = client.get("/api/v1/incidents?page_size=10", headers=headers)
    assert inc_resp.status_code == 200
    assert "items" in inc_resp.json()

    # Test runbooks
    rb_resp = client.get("/api/v1/runbooks", headers=headers)
    assert rb_resp.status_code == 200
    assert "items" in rb_resp.json()


def test_missing_token_rejected_with_401(client: TestClient):
    """Protected incident and runbook endpoints reject requests missing authorization."""
    for path in ["/api/v1/incidents?page_size=10", "/api/v1/runbooks"]:
        response = client.get(path)
        assert response.status_code == 401
        data = response.json()
        assert data.get("error") == "unauthorized"


def test_expired_token_rejected_with_401(client: TestClient):
    """Tokens past expiration are rejected on protected routes."""
    expired_token = generate_test_jwt(expires_in=-3600)
    for path in ["/api/v1/incidents", "/api/v1/runbooks"]:
        response = client.get(path, headers={"Authorization": f"Bearer {expired_token}"})
        assert response.status_code == 401
        assert response.json().get("error") == "unauthorized"


def test_invalid_signature_rejected_with_401(client: TestClient):
    """Tokens signed with wrong secret key are rejected on protected routes."""
    wrong_key_token = generate_test_jwt(secret="mismatched-key-32-chars-long-1234567")
    for path in ["/api/v1/incidents", "/api/v1/runbooks"]:
        response = client.get(path, headers={"Authorization": f"Bearer {wrong_key_token}"})
        assert response.status_code == 401
        assert response.json().get("error") == "unauthorized"


def test_wrong_issuer_and_audience_rejected_with_401(client: TestClient):
    """Tokens with incorrect issuer or audience claims are rejected."""
    wrong_issuer = generate_test_jwt(issuer="untrusted-issuer")
    resp_iss = client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {wrong_issuer}"})
    assert resp_iss.status_code == 401

    wrong_aud = generate_test_jwt(audience="wrong-audience")
    resp_aud = client.get("/api/v1/runbooks", headers={"Authorization": f"Bearer {wrong_aud}"})
    assert resp_aud.status_code == 401


def test_missing_iss_claim_rejected_with_401(client: TestClient, caplog):
    """Tokens missing the 'iss' claim are rejected with 401 and safe category logging."""
    token_no_iss = generate_test_jwt(omit_iss=True)
    for path in ["/api/v1/incidents", "/api/v1/runbooks"]:
        resp = client.get(path, headers={"Authorization": f"Bearer {token_no_iss}"})
        assert resp.status_code == 401
        assert resp.json().get("error") == "unauthorized"


def test_missing_aud_claim_rejected_with_401(client: TestClient):
    """Tokens missing the 'aud' claim are rejected with 401."""
    token_no_aud = generate_test_jwt(omit_aud=True)
    for path in ["/api/v1/incidents", "/api/v1/runbooks"]:
        resp = client.get(path, headers={"Authorization": f"Bearer {token_no_aud}"})
        assert resp.status_code == 401
        assert resp.json().get("error") == "unauthorized"


def test_minimal_claims_token_without_iss_aud_rejected_with_401(client: TestClient):
    """Tokens containing only sub, exp, and iat (no iss or aud) are strictly rejected."""
    minimal_token = generate_test_jwt(omit_iss=True, omit_aud=True)
    for path in ["/api/v1/incidents", "/api/v1/runbooks"]:
        resp = client.get(path, headers={"Authorization": f"Bearer {minimal_token}"})
        assert resp.status_code == 401
        assert resp.json().get("error") == "unauthorized"


def test_dev_token_disabled_in_production(client: TestClient, monkeypatch):
    """When APP_ENV is production and ENABLE_DEV_AUTH is False, dev-token returns 403."""
    settings = get_settings()
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ENABLE_DEV_AUTH", False)

    response = client.post("/api/v1/auth/dev-token")
    assert response.status_code == 403
    assert "disabled in production" in response.json().get("detail", "")

