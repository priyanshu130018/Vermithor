import json
import time
import pytest
from fastapi.testclient import TestClient

from backend.app.common.security import create_access_token, verify_access_token
from gateway.tests.conftest import (
    DEV_SECRET,
    base64url_encode,
    generate_test_jwt,
)


def test_public_health_endpoint(test_client: TestClient):
    """Liveness probe /health is public and does not require authentication."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "healthy"
    assert "service" in data


def test_public_readiness_endpoint(test_client: TestClient):
    """Readiness probe /ready is public and accessible without authentication."""
    response = test_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data


def test_public_root_endpoint(test_client: TestClient):
    """Root metadata endpoint / is public and accessible without authentication."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data.get("name") == "Vermithor Modular Monolith API"
    assert data.get("docs") == "/docs"


def test_missing_jwt_rejected(test_client: TestClient):
    """Protected endpoints reject requests missing an Authorization header."""
    for path in ["/api/v1/incidents", "/api/v1/events", "/api/v1/observations", "/api/v1/correlations/groups"]:
        response = test_client.get(path)
        assert response.status_code == 401, f"Expected 401 on {path}"
        data = response.json()
        assert data.get("error") == "unauthorized"
        assert data.get("message") == "Invalid authentication token"
        assert "request_id" in data


def test_malformed_auth_headers_rejected(test_client: TestClient):
    """Malformed or non-Bearer authorization headers are rejected with 401."""
    malformed_headers = [
        "Basic dXNlcjpwYXNz",
        "Token some-random-opaque-token",
        "Bearer",
        "Bearer ",
        "Bearer not-a-jwt",
        "Bearer part1.part2",
        "Bearer p1.p2.p3.p4",
    ]
    for auth in malformed_headers:
        response = test_client.get("/api/v1/incidents", headers={"Authorization": auth})
        assert response.status_code == 401
        data = response.json()
        assert data.get("error") == "unauthorized"


def test_invalid_signature_rejected(test_client: TestClient):
    """Tokens signed with wrong secret key or tampered signature bits are rejected."""
    wrong_secret_token = generate_test_jwt(secret="wrong-secret-key-at-least-32-chars-length")
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {wrong_secret_token}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"

    tampered_token = generate_test_jwt(tamper_signature=True)
    response2 = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {tampered_token}"})
    assert response2.status_code == 401
    assert response2.json().get("error") == "unauthorized"


def test_expired_jwt_rejected(test_client: TestClient, expired_token: str):
    """Tokens past expiration (including clock skew leeway) are rejected."""
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_wrong_issuer_rejected(test_client: TestClient, wrong_issuer_token: str):
    """Tokens with unauthorized issuer claim are rejected."""
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {wrong_issuer_token}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_wrong_audience_rejected(test_client: TestClient, wrong_audience_token: str):
    """Tokens with mismatched audience claim are rejected."""
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {wrong_audience_token}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_missing_sub_claim_rejected(test_client: TestClient):
    """Tokens missing subject claim or containing empty subject are rejected."""
    token_no_sub = generate_test_jwt(omit_sub=True)
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_no_sub}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"

    token_empty_sub = generate_test_jwt(subject="   ")
    response2 = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_empty_sub}"})
    assert response2.status_code == 401
    assert response2.json().get("error") == "unauthorized"


def test_missing_exp_claim_rejected(test_client: TestClient):
    """Tokens missing expiration claim are rejected."""
    token_no_exp = generate_test_jwt(omit_exp=True)
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_no_exp}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_missing_iss_claim_rejected(test_client: TestClient):
    """Tokens missing issuer claim are rejected."""
    token_no_iss = generate_test_jwt(omit_iss=True)
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_no_iss}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_missing_aud_claim_rejected(test_client: TestClient):
    """Tokens missing audience claim are rejected."""
    token_no_aud = generate_test_jwt(omit_aud=True)
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_no_aud}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_minimal_claims_token_rejected(test_client: TestClient):
    """Tokens containing only sub, exp, and iat (no iss or aud) are rejected."""
    token_minimal = generate_test_jwt(omit_iss=True, omit_aud=True)
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token_minimal}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_disallowed_algorithm_none_rejected(test_client: TestClient):
    """Tokens signed with insecure 'none' algorithm are strictly rejected."""
    header_b64 = base64url_encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload_b64 = base64url_encode(
        json.dumps({
            "sub": "admin",
            "iss": "vermithor",
            "aud": "vermithor-api",
            "exp": int(time.time()) + 3600,
        }).encode("utf-8")
    )
    token = f"{header_b64}.{payload_b64}."
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_disallowed_algorithm_rs256_rejected(test_client: TestClient):
    """Tokens configured with RS256 algorithm are rejected when HS256 is expected."""
    token = generate_test_jwt(alg="RS256")
    response = test_client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json().get("error") == "unauthorized"


def test_valid_jwt_accepted_on_protected_endpoints(test_client: TestClient, valid_token: str):
    """Valid JWT tokens authenticate successfully across protected API endpoints."""
    headers = {"Authorization": f"Bearer {valid_token}"}
    for path in ["/api/v1/incidents", "/api/v1/events", "/api/v1/observations", "/api/v1/correlations/groups"]:
        response = test_client.get(path, headers=headers)
        assert response.status_code != 401, f"Expected authenticated response on {path}, got 401"
        assert response.status_code in [200, 404]


def test_security_headers_defined_in_nginx():
    """Verify standard Nginx configuration maintains all required security headers."""
    with open("gateway/nginx.conf", "r", encoding="utf-8") as f:
        conf = f.read()

    assert 'add_header X-Content-Type-Options "nosniff"' in conf
    assert 'add_header X-Frame-Options "DENY"' in conf
    assert "Referrer-Policy" in conf
    assert "Content-Security-Policy" in conf
    assert "Permissions-Policy" in conf
    assert "client_max_body_size 10m;" in conf


def test_rate_limiting_zones_defined_in_nginx():
    """Verify standard Nginx configuration retains all tiered rate limiting zones."""
    with open("gateway/nginx.conf", "r", encoding="utf-8") as f:
        conf = f.read()

    assert "limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;" in conf
    assert "limit_req_zone $binary_remote_addr zone=api_summary:10m rate=2r/s;" in conf
    assert "limit_req_zone $binary_remote_addr zone=api_logs:10m rate=10r/s;" in conf
    assert "limit_req_status 429;" in conf


def test_nginx_proxy_forwards_authorization_and_headers():
    """Verify Nginx reverse proxy forwards Authorization and tracing headers to backend."""
    with open("gateway/nginx.conf", "r", encoding="utf-8") as f:
        conf = f.read()

    assert "proxy_pass http://backend_service;" in conf
    assert "proxy_set_header Authorization $http_authorization;" in conf
    assert "proxy_set_header X-Request-ID $req_id;" in conf
    assert "upstream backend_service" in conf


def test_no_lua_or_openresty_in_gateway_config():
    """Verify all Lua and OpenResty directives are completely eliminated from gateway."""
    with open("gateway/nginx.conf", "r", encoding="utf-8") as f:
        conf = f.read()

    assert "access_by_lua_file" not in conf
    assert "openresty" not in conf.lower()
    assert "env JWT_" not in conf


def test_dockerfile_uses_standard_nginx():
    """Verify gateway Dockerfile uses standard nginx:alpine without Lua dependencies."""
    with open("gateway/Dockerfile", "r", encoding="utf-8") as f:
        dockerfile = f.read()

    assert "FROM nginx:alpine" in dockerfile
    assert "openresty" not in dockerfile.lower()
    assert "luarocks" not in dockerfile.lower()
    assert "jwt_auth.lua" not in dockerfile
