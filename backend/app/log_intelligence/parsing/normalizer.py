import re

# Regex patterns for secret redaction
PASSWORD_PATTERN = re.compile(r"(?i)\b(password|passwd|pwd|secret|api_key|apikey|token|access_token|auth_token)\s*([:=])\s*([^\s,;]+)")
BEARER_PATTERN = re.compile(r"(?i)\b(bearer)\s+([a-zA-Z0-9_\-\.\~]+)")
JWT_PATTERN = re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b")

# Regex patterns for normalization of volatile values
TIMESTAMP_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
IP_PORT_PATTERN = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})\b")
IP_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HEX_ID_PATTERN = re.compile(r"\b[0-9a-fA-F]{16,64}\b")
FLOAT_PATTERN = re.compile(r"\b\d+\.\d+(?:ms|s|MB|GB|KB|%)?\b|\b\d+\.\d+")
DURATION_PATTERN = re.compile(r"\b\d+(?:\.\d+)?(?:ms|µs|us|ns|s|min)\b")

# HTTP status codes to preserve (don't replace with <NUM>)
PRESERVED_STATUS_CODES = {"200", "201", "204", "400", "401", "403", "404", "409", "422", "429", "500", "501", "502", "503", "504"}


class LogNormalizer:
    """Handles sensitive data redaction and volatile token normalization."""

    @classmethod
    def redact_secrets(cls, text: str) -> str:
        """
        Redact sensitive passwords, tokens, API keys, and JWTs from log text.

        Returns:
            str: Redacted text with <REDACTED> placeholders.
        """
        if not text:
            return ""

        redacted = PASSWORD_PATTERN.sub(r"\1\2<REDACTED>", text)
        redacted = BEARER_PATTERN.sub(r"\1 <REDACTED>", redacted)
        redacted = JWT_PATTERN.sub(r"<REDACTED>", redacted)
        return redacted

    @classmethod
    def normalize_log(cls, raw_message: str) -> str:
        """
        Normalize volatile runtime parameters (IPs, timestamps, UUIDs, hex IDs, numbers)
        while preserving semantic indicators (HTTP status codes, errors).

        Returns:
            str: Normalized log string.
        """
        if not raw_message:
            return ""

        # 1. Redact secrets first
        text = cls.redact_secrets(raw_message)

        # 2. Replace timestamps
        text = TIMESTAMP_PATTERN.sub("<TIMESTAMP>", text)

        # 3. Replace IP + Port combinations, then standalone IPs
        text = IP_PORT_PATTERN.sub("<IP>:<PORT>", text)
        text = IP_PATTERN.sub("<IP>", text)

        # 4. Replace UUIDs
        text = UUID_PATTERN.sub("<UUID>", text)

        # 5. Replace long Hex hashes / trace IDs
        text = HEX_ID_PATTERN.sub("<HEX>", text)

        # 6. Replace duration and float quantities
        text = DURATION_PATTERN.sub("<NUM>", text)
        text = FLOAT_PATTERN.sub("<NUM>", text)

        # 7. Normalize general integers while preserving HTTP status codes
        def replace_num(match):
            val = match.group(0)
            if val in PRESERVED_STATUS_CODES:
                return val
            return "<NUM>"

        text = re.sub(r"\b\d{4,}\b", replace_num, text)

        # 8. Consolidate whitespaces
        text = re.sub(r"\s+", " ", text).strip()
        return text
