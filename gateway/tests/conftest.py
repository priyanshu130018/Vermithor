import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional, Tuple
import pytest

DEV_SECRET = "vermithor-dev-secret-key-32-chars-min"
CLOCK_SKEW_TOLERANCE_SECONDS = 30


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def base64url_decode(data: str) -> bytes:
    remainder = len(data) % 4
    if remainder > 0:
        data += "=" * (4 - remainder)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def generate_test_jwt(
    secret: str = DEV_SECRET,
    issuer: str = "vermithor",
    audience: str = "vermithor-api",
    subject: str = "sre-user-001",
    expires_in: int = 3600,
    tamper_signature: bool = False,
    alg: str = "HS256",
    nbf_offset: int = 0,
    iat_offset: int = 0,
) -> str:
    header = {"alg": alg, "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now + iat_offset,
        "exp": now + expires_in,
    }
    if nbf_offset != 0:
        payload["nbf"] = now + nbf_offset

    header_b64 = base64url_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = base64url_encode(json.dumps(payload).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    if alg == "HS256":
        sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        sig_b64 = base64url_encode(sig)
    else:
        sig_b64 = "simulated_unsupported_signature"

    if tamper_signature:
        sig_b64 = "invalid_signature_bits"

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def simulate_gateway_auth(path: str, auth_header: Optional[str]) -> Tuple[int, Dict[str, Any]]:
    """Simulates OpenResty Lua JWT validation logic from gateway/jwt_auth.lua."""
    if path == "/health":
        return 200, {"service": "vermithor-gateway", "status": "healthy"}

    if not auth_header or not auth_header.startswith("Bearer "):
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    token = auth_header.split(" ", 1)[1].strip()
    parts = token.split(".")
    if len(parts) != 3:
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    header_b64, payload_b64, signature_b64 = parts[0], parts[1], parts[2]

    try:
        header = json.loads(base64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(base64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    # Verify Algorithm
    if header.get("alg") != "HS256":
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    # Verify Signature
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = base64url_encode(hmac.new(DEV_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest())
    if signature_b64 != expected_sig:
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    # Verify Claims
    if payload.get("iss") != "vermithor" or payload.get("aud") != "vermithor-api":
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    now = int(time.time())
    if "exp" in payload and (payload["exp"] + CLOCK_SKEW_TOLERANCE_SECONDS) < now:
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    if "nbf" in payload and (payload["nbf"] - CLOCK_SKEW_TOLERANCE_SECONDS) > now:
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    if "iat" in payload and (payload["iat"] - CLOCK_SKEW_TOLERANCE_SECONDS) > now:
        return 401, {
            "error": "unauthorized",
            "message": "Invalid authentication token",
            "request_id": "test-req-id",
        }

    return 200, {
        "authenticated": True,
        "user_id": payload.get("sub"),
        "request_id": "test-req-id",
    }


@pytest.fixture
def valid_token() -> str:
    return generate_test_jwt()


@pytest.fixture
def expired_token() -> str:
    return generate_test_jwt(expires_in=-3600)


@pytest.fixture
def invalid_sig_token() -> str:
    return generate_test_jwt(tamper_signature=True)


@pytest.fixture
def wrong_issuer_token() -> str:
    return generate_test_jwt(issuer="unauthorized-issuer")


@pytest.fixture
def wrong_audience_token() -> str:
    return generate_test_jwt(audience="wrong-api")
