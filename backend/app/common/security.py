import time
from typing import Any, Dict, Optional
import jwt

from backend.app.common.config import get_settings


def create_access_token(
    data: Dict[str, Any],
    expires_delta_seconds: int = 3600,
    secret_key: Optional[str] = None,
) -> str:
    """Create a signed HS256 JWT access token for client testing and internal authorization."""
    settings = get_settings()
    secret = secret_key or settings.JWT_SECRET
    now = int(time.time())
    payload = data.copy()
    payload.update({
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + expires_delta_seconds,
    })
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_access_token(token: str, secret_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Verify an HS256 JWT token against standard issuer/audience bounds."""
    settings = get_settings()
    secret = secret_key or settings.JWT_SECRET
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
        return payload
    except Exception:
        return None
