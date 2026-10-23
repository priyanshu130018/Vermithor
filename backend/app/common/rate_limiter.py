import collections
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
from fastapi import HTTPException, Request, Response, status

from backend.app.common.config import get_settings

logger = logging.getLogger(__name__)


class InMemorySlidingWindowLimiter:
    """Thread-safe in-memory sliding window rate limiter used as primary or fallback."""

    def __init__(self, capacity: int = 1000):
        self._lock = threading.Lock()
        self._windows: Dict[str, collections.deque] = {}
        self._capacity = capacity

    def check_and_record(
        self, key: str, max_calls: int, window_seconds: int
    ) -> Tuple[bool, int, int]:
        """
        Record a hit and return (allowed, remaining, retry_after_seconds).
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Simple LRU-style cleanup if capacity exceeded
            if len(self._windows) > self._capacity:
                oldest_keys = [k for k, q in self._windows.items() if not q or q[-1] < cutoff]
                for k in oldest_keys[:100]:
                    self._windows.pop(k, None)

            if key not in self._windows:
                self._windows[key] = collections.deque()

            q = self._windows[key]

            # Evict timestamps outside the window
            while q and q[0] <= cutoff:
                q.popleft()

            current_count = len(q)
            if current_count >= max_calls:
                oldest = q[0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, 0, retry_after

            # Allow and record current timestamp
            q.append(now)
            remaining = max(0, max_calls - (current_count + 1))
            return True, remaining, 0

    def reset(self) -> None:
        """Reset internal memory windows (useful for testing)."""
        with self._lock:
            self._windows.clear()


_in_memory_limiter = InMemorySlidingWindowLimiter()


class RateLimiter:
    """
    FastAPI dependency enforcing sliding-window rate limiting.
    Supports Redis with automatic in-memory fallback if Redis is unavailable.
    """

    def __init__(
        self,
        scope: str,
        calls_per_minute: int,
        window_seconds: int = 60,
        fail_closed_on_redis_outage: bool = False,
        degraded_ratio: Optional[float] = None,
    ):
        self.scope = scope
        self.calls_per_minute = calls_per_minute
        self.window_seconds = window_seconds
        self.fail_closed_on_redis_outage = fail_closed_on_redis_outage
        self.degraded_ratio = degraded_ratio

    def _get_redis_client(self):
        try:
            import redis
            settings = get_settings()
            return redis.Redis.from_url(
                settings.REDIS_URL,
                socket_timeout=1.0,
                socket_connect_timeout=1.0,
                decode_responses=True,
            )
        except Exception as exc:
            logger.debug("Redis client init failed for rate limiting: %s", exc)
            return None

    def _resolve_key(self, request: Request) -> str:
        """
        Determine rate limit bucket key from verified server-side request state.
        Uses organization and user ID if authenticated, or client IP if unauthenticated.
        """
        # Verified JWT payload attached by require_jwt_auth
        jwt_payload = getattr(request.state, "jwt_payload", None)
        if not jwt_payload:
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
                try:
                    from backend.app.common.security import verify_access_token
                    jwt_payload = verify_access_token(token)
                except Exception:
                    jwt_payload = None
        jwt_payload = jwt_payload or {}

        user_id = getattr(request.state, "user_id", None) or jwt_payload.get("sub")
        org_id = (
            jwt_payload.get("org_id")
            or jwt_payload.get("organization")
            or jwt_payload.get("org")
        )

        if org_id:
            org_clean = str(org_id).strip().lower()
            user_clean = str(user_id or "anon").strip()
            return f"rl:{self.scope}:org:{org_clean}:{user_clean}"
        elif user_id:
            return f"rl:{self.scope}:user:{str(user_id).strip()}"

        # Unauthenticated: use direct socket client IP; only trust X-Forwarded-For if configured
        client_host = "127.0.0.1"
        if request.client and request.client.host:
            client_host = request.client.host
        settings = get_settings()
        if getattr(settings, "TRUST_FORWARDED_HEADERS", False):
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                client_host = forwarded_for.split(",")[0].strip()

        return f"rl:{self.scope}:ip:{client_host}"

    def check_rate_limit(
        self,
        request: Request,
        response: Optional[Response] = None,
    ) -> None:
        """
        Check rate limit and record request. Raises HTTP 429 if limit exceeded.
        """
        settings = get_settings()
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return

        key = self._resolve_key(request)
        max_calls = self.calls_per_minute
        window = self.window_seconds

        allowed = True
        remaining = max_calls
        retry_after = 0

        # 1. Attempt Redis sliding window with sorted set
        redis_client = self._get_redis_client()
        redis_succeeded = False

        if redis_client:
            try:
                now = time.time()
                cutoff = now - window
                pipe = redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, cutoff)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, window + 5)
                res = pipe.execute()

                current_count = res[1]
                if current_count >= max_calls:
                    # Remove the just-added timestamp since request is rejected
                    redis_client.zrem(key, str(now))
                    allowed = False
                    remaining = 0
                    retry_after = int(window)
                else:
                    allowed = True
                    remaining = max(0, max_calls - (current_count + 1))
                    retry_after = 0
                redis_succeeded = True
            except Exception as exc:
                logger.warning(
                    "Redis rate limit check failed (%s); engaging in-memory fallback for key '%s'",
                    exc,
                    key,
                )
                redis_succeeded = False

        # 2. In-memory fallback if Redis was unavailable or failed
        if not redis_succeeded:
            if self.fail_closed_on_redis_outage:
                logger.error(
                    "Rate limit fail-closed policy enforced for scope '%s' on key '%s' due to Redis outage",
                    self.scope,
                    key,
                )
                headers = {
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(max_calls),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + window)),
                }
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Rate limiting service temporarily unavailable for {self.scope}. Request blocked under fail-closed safety policy.",
                    headers=headers,
                )

            effective_calls = max_calls
            if self.degraded_ratio is not None:
                effective_calls = max(1, int(max_calls * self.degraded_ratio))
            elif getattr(settings, "RATE_LIMIT_DEGRADED_QUOTA_BOUNDED", True):
                worker_count = max(1, getattr(settings, "RATE_LIMIT_WORKER_PROCESS_COUNT", 4))
                effective_calls = max(1, max_calls // worker_count)

            allowed, remaining, retry_after = _in_memory_limiter.check_and_record(
                key=key,
                max_calls=effective_calls,
                window_seconds=window,
            )

        # Set rate limit headers if response object is available
        reset_time = int(time.time() + (retry_after if not allowed else window))
        if response:
            response.headers["X-RateLimit-Limit"] = str(max_calls)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_time)

        if not allowed:
            logger.warning(
                "Rate limit exceeded for scope '%s' on key '%s'. Limit: %d/%ds. Retry-After: %ds",
                self.scope,
                key,
                max_calls,
                window,
                retry_after,
            )
            headers = {
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(max_calls),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
            }
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {self.scope}. Limit: {max_calls} requests per {window}s. Retry after {retry_after}s.",
                headers=headers,
            )

    def __call__(self, request: Request, response: Response) -> None:
        """FastAPI dependency entrypoint."""
        self.check_rate_limit(request, response)
