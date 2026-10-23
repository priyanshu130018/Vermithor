import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException, Request, Response

from backend.app.common.config import Settings, get_settings
from backend.app.common.database import get_pool_status
from backend.app.common.rate_limiter import (
    InMemorySlidingWindowLimiter,
    RateLimiter,
    _in_memory_limiter,
)
from backend.app.common.security import create_access_token


def test_in_memory_sliding_window_basic():
    """Verify in-memory sliding window allows up to max_calls and rejects the next."""
    limiter = InMemorySlidingWindowLimiter(capacity=100)
    key = "test:user:1"
    max_calls = 3
    window = 10

    # 1st call
    allowed, remaining, retry_after = limiter.check_and_record(key, max_calls, window)
    assert allowed is True
    assert remaining == 2
    assert retry_after == 0

    # 2nd call
    allowed, remaining, retry_after = limiter.check_and_record(key, max_calls, window)
    assert allowed is True
    assert remaining == 1

    # 3rd call
    allowed, remaining, retry_after = limiter.check_and_record(key, max_calls, window)
    assert allowed is True
    assert remaining == 0

    # 4th call (exceeded)
    allowed, remaining, retry_after = limiter.check_and_record(key, max_calls, window)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_in_memory_sliding_window_expiry():
    """Verify sliding window clears older hits as time advances."""
    limiter = InMemorySlidingWindowLimiter(capacity=100)
    key = "test:user:2"
    max_calls = 2
    window = 2

    # Add 2 calls at time T=100
    with patch("time.time", return_value=100.0):
        allowed1, _, _ = limiter.check_and_record(key, max_calls, window)
        allowed2, _, _ = limiter.check_and_record(key, max_calls, window)
        assert allowed1 and allowed2

        # 3rd call at T=100 rejected
        allowed3, _, retry_after = limiter.check_and_record(key, max_calls, window)
        assert not allowed3
        assert retry_after == 2

    # Advance time to T=103 (past window)
    with patch("time.time", return_value=103.0):
        allowed4, remaining, _ = limiter.check_and_record(key, max_calls, window)
        assert allowed4 is True
        assert remaining == 1


def test_rate_limiter_key_resolution():
    """Verify server-side rate limit key resolution across tenant org, user, and unauthenticated IP."""
    limiter = RateLimiter(scope="repairs", calls_per_minute=10)

    # 1. Authenticated with org_id and sub
    req_auth = MagicMock(spec=Request)
    req_auth.state = MagicMock()
    req_auth.state.jwt_payload = {"org_id": "Acme-Corp", "sub": "usr_123"}
    req_auth.state.user_id = "usr_123"
    req_auth.headers = {}
    key1 = limiter._resolve_key(req_auth)
    assert key1 == "rl:repairs:org:acme-corp:usr_123"

    # 2. Authenticated with sub only
    req_user = MagicMock(spec=Request)
    req_user.state = MagicMock()
    req_user.state.jwt_payload = {"sub": "usr_456"}
    req_user.state.user_id = "usr_456"
    req_user.headers = {}
    key2 = limiter._resolve_key(req_user)
    assert key2 == "rl:repairs:user:usr_456"

    # 3. Unauthenticated with client IP
    req_unauth = MagicMock(spec=Request)
    req_unauth.state = MagicMock()
    req_unauth.state.jwt_payload = None
    req_unauth.state.user_id = None
    req_unauth.client.host = "192.168.1.50"
    req_unauth.headers = {}
    key3 = limiter._resolve_key(req_unauth)
    assert key3 == "rl:repairs:ip:192.168.1.50"

    # 4. Bearer token in headers parsed when request.state is empty
    token = create_access_token({"sub": "jwt_user", "org_id": "cyberdyne"})
    req_token = MagicMock(spec=Request)
    req_token.state = MagicMock()
    req_token.state.jwt_payload = None
    req_token.state.user_id = None
    req_token.headers = {"authorization": f"Bearer {token}"}
    key4 = limiter._resolve_key(req_token)
    assert key4 == "rl:repairs:org:cyberdyne:jwt_user"


def test_rate_limiter_redis_sliding_window_execution():
    """Verify Redis pipeline sorted-set sliding window execution when Redis is available."""
    limiter = RateLimiter(scope="investigations", calls_per_minute=2, window_seconds=60)
    _in_memory_limiter.reset()

    mock_redis = MagicMock()
    mock_pipeline = MagicMock()
    # pipeline returns [remrange_res, count_before_add, add_res, expire_res]
    mock_pipeline.execute.return_value = [0, 1, 1, True]
    mock_redis.pipeline.return_value = mock_pipeline

    with patch.object(limiter, "_get_redis_client", return_value=mock_redis):
        req = MagicMock(spec=Request)
        req.state = MagicMock()
        req.state.jwt_payload = {"org_id": "testorg", "sub": "u1"}
        req.state.user_id = "u1"
        req.headers = {}
        res = Response()

        # Call within quota
        limiter.check_rate_limit(req, res)
        assert res.headers["X-RateLimit-Limit"] == "2"
        assert res.headers["X-RateLimit-Remaining"] == "0"
        assert "X-RateLimit-Reset" in res.headers

        # Second call exceeding quota (count >= max_calls)
        mock_pipeline.execute.return_value = [0, 2, 1, True]
        with pytest.raises(HTTPException) as exc_info:
            limiter.check_rate_limit(req, res)

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["X-RateLimit-Limit"] == "2"
        assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"


def test_rate_limiter_redis_fallback_to_memory():
    """Verify graceful fallback to in-memory limiter when Redis connection fails."""
    limiter = RateLimiter(scope="repositories", calls_per_minute=2, window_seconds=60)
    _in_memory_limiter.reset()

    # Redis client raises an exception during pipeline execution
    mock_redis = MagicMock()
    mock_redis.pipeline.side_effect = ConnectionError("Redis unreachable")

    with patch.object(limiter, "_get_redis_client", return_value=mock_redis):
        req = MagicMock(spec=Request)
        req.state = MagicMock()
        req.state.jwt_payload = {"org_id": "fallback_org", "sub": "u_fb"}
        req.state.user_id = "u_fb"
        req.headers = {}
        res = Response()

        # 1st call succeeds via in-memory fallback
        limiter.check_rate_limit(req, res)
        assert res.headers["X-RateLimit-Limit"] == "2"
        assert res.headers["X-RateLimit-Remaining"] == "1"

        # 2nd call succeeds via in-memory fallback
        limiter.check_rate_limit(req, res)
        assert res.headers["X-RateLimit-Remaining"] == "0"

        # 3rd call rejects with 429
        with pytest.raises(HTTPException) as exc_info:
            limiter.check_rate_limit(req, res)
        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"] is not None


def test_rate_limiter_disabled_setting():
    """Verify rate limiter allows calls unconditionally when RATE_LIMIT_ENABLED is False."""
    limiter = RateLimiter(scope="repairs", calls_per_minute=1)

    req = MagicMock(spec=Request)
    req.state = MagicMock()
    req.state.jwt_payload = {"org_id": "bypass_org", "sub": "admin"}
    req.state.user_id = "admin"
    req.headers = {}
    res = Response()

    with patch("backend.app.common.rate_limiter.get_settings") as mock_settings:
        mock_settings.return_value = Settings(RATE_LIMIT_ENABLED=False)
        # Should not raise even if called 10 times with limit 1
        for _ in range(10):
            limiter.check_rate_limit(req, res)


def test_get_pool_status_diagnostics():
    """Verify safe database connection pool diagnostics function."""
    status = get_pool_status()
    assert isinstance(status, dict)
    assert "pool_class" in status
    # Must not contain credentials or secret fields
    assert "password" not in status
    assert "secret" not in status
