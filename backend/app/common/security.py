import logging
import time
from typing import Any, Dict, Optional
import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.common.config import get_settings

logger = logging.getLogger(__name__)

http_bearer = HTTPBearer(auto_error=False)


def create_access_token(
    data: Dict[str, Any],
    expires_delta_seconds: int = 3600,
    secret_key: Optional[str] = None,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
) -> str:
    """Create a signed HS256 JWT access token for client testing and internal authorization."""
    settings = get_settings()
    secret = secret_key or settings.JWT_SECRET
    token_issuer = issuer or data.get("iss") or settings.JWT_ISSUER
    token_audience = audience or data.get("aud") or settings.JWT_AUDIENCE
    now = int(time.time())
    payload = data.copy()
    payload.update({
        "iss": token_issuer,
        "aud": token_audience,
        "iat": now,
        "nbf": now,
        "exp": now + expires_delta_seconds,
    })
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_access_token(token: str, secret_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Verify an HS256 JWT token against signature, required claims (sub, exp, iss, aud), and clock skew bounds."""
    settings = get_settings()
    secret = secret_key or settings.JWT_SECRET
    if not secret:
        logger.warning("Auth failure category: missing_signing_secret (JWT_SECRET not configured)")
        return None

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={
                "require": ["sub", "exp", "iss", "aud"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
            leeway=30,
        )
        sub = payload.get("sub")
        if sub is None or str(sub).strip() == "":
            logger.warning("Auth failure category: missing_or_empty_sub_claim")
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Auth failure category: expired_signature")
        return None
    except jwt.InvalidSignatureError:
        logger.warning("Auth failure category: invalid_signature (mismatched signing secret)")
        return None
    except jwt.InvalidIssuerError:
        logger.warning("Auth failure category: invalid_issuer")
        return None
    except jwt.InvalidAudienceError:
        logger.warning("Auth failure category: invalid_audience")
        return None
    except jwt.MissingRequiredClaimError as exc:
        logger.warning("Auth failure category: missing_required_claim (%s)", type(exc).__name__)
        return None
    except jwt.InvalidAlgorithmError:
        logger.warning("Auth failure category: invalid_algorithm")
        return None
    except jwt.DecodeError:
        logger.warning("Auth failure category: malformed_token_decode_error")
        return None
    except Exception as exc:
        logger.warning("Auth failure category: unexpected_error (%s)", type(exc).__name__)
        return None


def require_jwt_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(http_bearer),
) -> Dict[str, Any]:
    """FastAPI dependency enforcing valid HS256 JWT authentication for protected routes."""
    if not credentials or not credentials.credentials:
        logger.warning("Auth failure category: missing_credentials_header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_access_token(credentials.credentials)
    if not payload:
        logger.warning("Auth failure category: token_verification_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attach authenticated user identity to request state
    request.state.user_id = str(payload["sub"])
    request.state.jwt_payload = payload
    return payload


def get_current_user(
    token_payload: Dict[str, Any] = Depends(require_jwt_auth),
) -> str:
    """Return subject identifier (user ID) from validated JWT payload."""
    return str(token_payload["sub"])
