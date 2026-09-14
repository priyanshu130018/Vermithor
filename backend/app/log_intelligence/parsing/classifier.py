import re
from typing import Optional
from backend.app.log_intelligence.schemas.logs import LogCategory


class LogClassifier:
    """Classifies log messages into operational domain categories."""

    CATEGORY_PATTERNS = [
        (
            LogCategory.DEPLOYMENT,
            re.compile(r"(?i)\b(deployment|deploy|rollout|rolled out|rollback|release|build #|starting container|version update)\b"),
        ),
        (
            LogCategory.DATABASE,
            re.compile(r"(?i)\b(postgres|postgresql|mysql|database|db|sql|connection pool|deadlock|query timeout|pq:|pg_stat|relation \"|table \")\b"),
        ),
        (
            LogCategory.AUTHENTICATION,
            re.compile(r"(?i)\b(unauthorized|forbidden|401|403|jwt|auth|authentication|token expired|invalid token|permission denied|bad credentials|login failed)\b"),
        ),
        (
            LogCategory.CACHE,
            re.compile(r"(?i)\b(redis|memcached|cache miss|cache hit|cache eviction|cluster down|redis connection)\b"),
        ),
        (
            LogCategory.RESOURCE,
            re.compile(r"(?i)\b(oom|out of memory|cpu saturation|memory limit|heap space|garbage collection|thread pool full|disk full|no space left)\b"),
        ),
        (
            LogCategory.HTTP,
            re.compile(r"(?i)\b(http 5\d{2}|500 internal|502 bad gateway|503 service unavailable|504 gateway timeout|http 4\d{2}|404 not found|bad request)\b"),
        ),
        (
            LogCategory.NETWORK,
            re.compile(r"(?i)\b(connection refused|econnrefused|econnreset|dns lookup|network unreachable|broken pipe|socket timeout|no route to host)\b"),
        ),
    ]

    @classmethod
    def classify(cls, message: str, service: Optional[str] = None) -> LogCategory:
        """
        Infer domain category for an operational log message.

        Returns:
            LogCategory: Categorized classification.
        """
        combined = f"{service or ''} {message}".lower()

        for category, pattern in cls.CATEGORY_PATTERNS:
            if pattern.search(combined):
                return category

        return LogCategory.UNKNOWN
