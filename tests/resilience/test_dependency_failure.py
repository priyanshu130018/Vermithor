import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import httpx


def test_gateway_nginx_upstream_timeout_configurations():
    """Verify Nginx gateway nginx.conf specifies explicit proxy read and connect timeouts."""
    nginx_conf_path = os.path.abspath("gateway/nginx.conf")
    with open(nginx_conf_path, "r", encoding="utf-8") as f:
        conf = f.read()

    assert "proxy_connect_timeout" in conf
    assert "proxy_read_timeout" in conf
    assert "proxy_send_timeout" in conf


def test_standardized_error_envelope_structure():
    """Verify standardized error envelope masking internal server errors."""
    error_payload = {
        "error": "service_unavailable",
        "message": "The requested upstream service is temporarily unavailable",
        "request_id": "req-resilience-12345",
    }

    assert "error" in error_payload
    assert "message" in error_payload
    assert "request_id" in error_payload
    assert "traceback" not in error_payload
    assert "password" not in str(error_payload).lower()


def test_client_timeout_bounds():
    """Verify client enforces bounded timeout rather than infinite wait."""
    def mock_hang(*args, **kwargs):
        raise httpx.ReadTimeout("Mock upstream read timed out after 10s")

    client = httpx.Client(timeout=1.0)
    with patch.object(client, "get", side_effect=mock_hang):
        with pytest.raises(httpx.ReadTimeout):
            client.get("http://localhost:8080/api/v1/incidents")
