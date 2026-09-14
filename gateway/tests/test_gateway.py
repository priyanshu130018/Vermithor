import time
import base64
import json
import hmac
import hashlib
import pytest
from gateway.tests.conftest import simulate_gateway_auth

DEV_SECRET = "vermithor-dev-secret-key-32-chars-min"
ISSUER = "vermithor"
AUDIENCE = "vermithor-api"


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def generate_test_token(
    payload_override=None,
    header_override=None,
    secret=DEV_SECRET,
    sign=True,
):
    header = {"alg": "HS256", "typ": "JWT"}
    if header_override:
        header.update(header_override)

    now = int(time.time())
    payload = {
        "sub": "sre-user-test",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 3600,
    }
    if payload_override:
        payload.update(payload_override)

    header_b64 = base64url_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = base64url_encode(json.dumps(payload).encode("utf-8"))

    if not sign:
        return f"{header_b64}.{payload_b64}.invalidsignature"

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = base64url_encode(sig)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def test_gateway_health():
    status, body = simulate_gateway_auth("/health", None)
    assert status == 200
    assert body.get("status") == "healthy"


def test_missing_jwt_rejected():
    status, body = simulate_gateway_auth("/api/v1/incidents", None)
    assert status == 401
    assert body.get("error") == "unauthorized"
    assert body.get("message") == "Invalid authentication token"
    assert "request_id" in body


def test_invalid_signature_rejected():
    token = generate_test_token(secret="wrong-secret-key-that-does-not-match")
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_expired_jwt_rejected():
    token = generate_test_token(payload_override={"exp": int(time.time()) - 100})
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_wrong_issuer_rejected():
    token = generate_test_token(payload_override={"iss": "untrusted-issuer"})
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_wrong_audience_rejected():
    token = generate_test_token(payload_override={"aud": "wrong-audience"})
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_valid_jwt_accepted():
    token = generate_test_token()
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 200
    assert body.get("authenticated") is True
    assert body.get("user_id") == "sre-user-test"


def test_disallowed_algorithm_none_rejected():
    header_b64 = base64url_encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload_b64 = base64url_encode(json.dumps({"sub": "admin", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 3600}).encode("utf-8"))
    token = f"{header_b64}.{payload_b64}."
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_disallowed_algorithm_rs256_rejected():
    token = generate_test_token(header_override={"alg": "RS256"})
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_token_not_valid_yet_nbf():
    token = generate_test_token(payload_override={"nbf": int(time.time()) + 300})
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_token_issued_in_future_iat():
    token = generate_test_token(payload_override={"iat": int(time.time()) + 300})
    status, body = simulate_gateway_auth("/api/v1/incidents", f"Bearer {token}")
    assert status == 401
    assert body.get("error") == "unauthorized"


def test_security_headers_defined():
    with open("gateway/nginx.conf", "r", encoding="utf-8") as f:
        conf = f.read()

    assert 'add_header X-Content-Type-Options "nosniff"' in conf
    assert 'add_header X-Frame-Options "DENY"' in conf
    assert "Referrer-Policy" in conf
    assert "Content-Security-Policy" in conf
    assert "Permissions-Policy" in conf
    assert "client_max_body_size 10m;" in conf
