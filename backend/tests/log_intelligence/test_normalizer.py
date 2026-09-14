from backend.app.log_intelligence.parsing.normalizer import LogNormalizer


def test_secret_redaction():
    """Verify passwords, bearer tokens, API keys, and JWTs are redacted."""
    raw = (
        "User login failed with password=super-secret-123 and "
        "Authorization: Bearer my-jwt-token-xyz. api_key: key-999-secret"
    )
    redacted = LogNormalizer.redact_secrets(raw)

    assert "super-secret-123" not in redacted
    assert "my-jwt-token-xyz" not in redacted
    assert "key-999-secret" not in redacted
    assert "password=<REDACTED>" in redacted
    assert "Bearer <REDACTED>" in redacted
    assert "api_key:<REDACTED>" in redacted


def test_normalization_volatile_tokens():
    """Verify IPs, ports, timestamps, UUIDs, and hex hashes are normalized."""
    raw = (
        "2026-08-29 12:02:31 ERROR booking-api: "
        "Connection refused to postgres at 10.20.30.41:5432. "
        "Session 123e4567-e89b-12d3-a456-426614174000 trace 4bf92f3577b34da6a3ce929d0e0e4736."
    )
    normalized = LogNormalizer.normalize_log(raw)

    assert "<TIMESTAMP>" in normalized
    assert "<IP>:<PORT>" in normalized
    assert "<UUID>" in normalized
    assert "<HEX>" in normalized
    assert "10.20.30.41" not in normalized
    assert "123e4567-e89b-12d3-a456-426614174000" not in normalized


def test_http_status_code_preservation():
    """Verify HTTP status codes (500, 404, 502, 503) are preserved for semantic search."""
    raw = "Request GET /api/v1/orders returned HTTP 500 with duration 123.45ms"
    normalized = LogNormalizer.normalize_log(raw)

    assert "500" in normalized
    assert "<NUM>" in normalized  # 123.45 is replaced
    assert "HTTP 500" in normalized
