import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Generator, Optional
import pytest
from fastapi.testclient import TestClient

from backend.app.common.config import get_settings
from backend.app.common.security import create_access_token, verify_access_token
from backend.app.main import app

DEV_SECRET = "vermithor-dev-secret-key-32-chars-min"
CLOCK_SKEW_TOLERANCE_SECONDS = 30


def base64url_encode(data: bytes) -> str:
    """Encode bytes using URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def base64url_decode(data: str) -> bytes:
    """Decode URL-safe base64 with missing padding restoration."""
    remainder = len(data) % 4
    if remainder > 0:
        data += "=" * (4 - remainder)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def generate_test_jwt(
    secret: Optional[str] = None,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
    subject: str = "sre-user-001",
    expires_in: int = 3600,
    tamper_signature: bool = False,
    alg: str = "HS256",
    nbf_offset: int = 0,
    iat_offset: int = 0,
    omit_sub: bool = False,
    omit_exp: bool = False,
    omit_iss: bool = False,
    omit_aud: bool = False,
) -> str:
    """Generate customizable JWT tokens for auth boundary and security edge-case testing."""
    settings = get_settings()
    signing_secret = secret if secret is not None else settings.JWT_SECRET
    token_issuer = issuer if issuer is not None else settings.JWT_ISSUER
    token_audience = audience if audience is not None else settings.JWT_AUDIENCE

    header = {"alg": alg, "typ": "JWT"}
    now = int(time.time())
    payload: Dict[str, Any] = {
        "iat": now + iat_offset,
    }
    if not omit_iss:
        payload["iss"] = token_issuer
    if not omit_aud:
        payload["aud"] = token_audience
    if not omit_sub:
        payload["sub"] = subject
    if not omit_exp:
        payload["exp"] = now + expires_in
    if nbf_offset != 0:
        payload["nbf"] = now + nbf_offset

    header_b64 = base64url_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = base64url_encode(json.dumps(payload).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    if alg == "HS256":
        sig = hmac.new(signing_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        sig_b64 = base64url_encode(sig)
    else:
        sig_b64 = "simulated_unsupported_signature"

    if tamper_signature:
        sig_b64 = "tampered_signature_bits"

    return f"{header_b64}.{payload_b64}.{sig_b64}"


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """TestClient fixture targeting Vermithor backend application."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def valid_token() -> str:
    """Valid standard HS256 JWT token."""
    return generate_test_jwt()


@pytest.fixture
def expired_token() -> str:
    """Expired HS256 JWT token."""
    return generate_test_jwt(expires_in=-3600)


@pytest.fixture
def invalid_sig_token() -> str:
    """Token with corrupted cryptographic signature."""
    return generate_test_jwt(tamper_signature=True)


@pytest.fixture
def wrong_issuer_token() -> str:
    """Token with unauthorized issuer."""
    return generate_test_jwt(issuer="unauthorized-issuer")


@pytest.fixture
def wrong_audience_token() -> str:
    """Token with mismatched audience."""
    return generate_test_jwt(audience="wrong-audience")
