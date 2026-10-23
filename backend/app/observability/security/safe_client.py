import ipaddress
import logging
import re
import socket
import typing
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
import httpcore
import httpx

logger = logging.getLogger(__name__)

# Cloud metadata endpoints and hostnames to block strictly
PROHIBITED_METADATA_HOSTS = {
    "169.254.169.254",
    "169.254.170.2",
    "metadata.google.internal",
    "instance-data",
    "100.100.100.200",  # Alibaba cloud metadata
}

# Maximum allowable response size for telemetry queries (2 MB)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

# Default timeouts for external telemetry endpoints (seconds)
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 5.0

# Regex patterns for credential masking
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9-_.]+)|(password|secret|api_key|token|auth_token|client_secret|private_key)\s*[:=]\s*['\"]?([^'\"\s,;]+)"
)


def mask_secret(secret_str: Optional[str]) -> str:
    """Mask a secret value displaying only the first and last 2 characters."""
    if not secret_str:
        return ""
    s = secret_str.strip()
    if len(s) <= 6:
        return "******"
    if s.lower().startswith("bearer "):
        token = s[7:]
        if len(token) <= 6:
            return "Bearer ******"
        return f"Bearer ***{token[-4:]}"
    return f"***{s[-4:]}"


def redact_sensitive_text(text: str) -> str:
    """
    Redact sensitive keys, passwords, bearer tokens, JWTs, URI credentials,
    and plausible email addresses/PII from error messages, prompts, or logs.
    """
    if not text:
        return text
    # 1. Redact Authorization / Bearer headers first
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9-_\.]+", "Bearer [REDACTED_TOKEN]", text)
    # 2. Redact standalone JWTs (header.payload.signature)
    text = re.sub(r"\bey[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_=]{10,}\.?[A-Za-z0-9-_.+/=]*\b", "[REDACTED_JWT]", text)
    # 3. Redact Database / service connection URI credentials (e.g. postgresql://user:pass@host)
    text = re.sub(r"(://[^:/@\s]+):[^/@\s]+@", r"\1:[REDACTED_CREDS]@", text)
    # 4. Redact common credential patterns (api_key=..., secret="...", password: ...)
    text = re.sub(
        r"(?i)(password|secret|api_key|token|auth_token|client_secret|private_key)\s*[:=]\s*['\"]?([^'\"\s,;]+)",
        r"\1=[REDACTED]",
        text,
    )
    # 5. Redact plausible email addresses / PII
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", text)
    return text


def redact_sensitive_data(val: Any) -> Any:
    """Recursively redact sensitive text across nested dictionaries, lists, and strings."""
    if isinstance(val, dict):
        return {
            (redact_sensitive_text(str(k)) if isinstance(k, str) else k): redact_sensitive_data(v)
            for k, v in val.items()
        }
    elif isinstance(val, list):
        return [redact_sensitive_data(item) for item in val]
    elif isinstance(val, str):
        return redact_sensitive_text(val)
    return val


def parse_ip_representation(hostname: str) -> Optional[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Parse direct IP, integer, hex, octal, or IPv4-mapped IPv6 representations."""
    clean_host = hostname.strip("[]")

    # 1. Direct standard IP
    try:
        ip = ipaddress.ip_address(clean_host)
        if getattr(ip, "ipv4_mapped", None):
            return ip.ipv4_mapped
        return ip
    except ValueError:
        pass

    # 2. Integer format (e.g. 2852039166 -> 169.254.169.254)
    if clean_host.isdigit():
        try:
            val = int(clean_host)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except Exception:
            pass

    # 3. Hexadecimal format (e.g. 0xa9fea9fe -> 169.254.169.254)
    if clean_host.lower().startswith("0x"):
        try:
            val = int(clean_host, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except Exception:
            pass

    # 4. Octal or mixed decimal dots (e.g. 0177.0.0.1 or 0251.0376.0251.0376)
    parts = clean_host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        try:
            octets = []
            for p in parts:
                if p.startswith("0") and len(p) > 1:
                    octets.append(int(p, 8))
                else:
                    octets.append(int(p, 10))
            if all(0 <= o <= 255 for o in octets):
                val = (octets[0] << 24) + (octets[1] << 16) + (octets[2] << 8) + octets[3]
                return ipaddress.IPv4Address(val)
        except Exception:
            pass

    return None


def _verify_ip_safety(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    allow_localhost: bool,
    allow_private: bool,
):
    """Verify that an IP address is not cloud metadata, loopback, link-local, or prohibited."""
    # Unwrap IPv4-mapped IPv6 address (e.g. ::ffff:169.254.169.254)
    if getattr(ip_obj, "ipv4_mapped", None):
        ip_obj = ip_obj.ipv4_mapped

    ip_str = str(ip_obj)

    # Cloud metadata check
    if ip_str in PROHIBITED_METADATA_HOSTS or ip_str.startswith("169.254."):
        raise ValueError(f"SSRF violation: Cloud metadata IP '{ip_str}' is strictly prohibited.")

    # Loopback check
    if ip_obj.is_loopback and not allow_localhost:
        raise ValueError(f"SSRF violation: Loopback address '{ip_str}' is prohibited.")

    # Multicast or unspecified
    if ip_obj.is_multicast or ip_obj.is_unspecified:
        raise ValueError(f"SSRF violation: Multicast/unspecified address '{ip_str}' is prohibited.")

    # Link local
    if ip_obj.is_link_local:
        raise ValueError(f"SSRF violation: Link-local address '{ip_str}' is prohibited.")

    # Private network check (RFC 1918)
    if ip_obj.is_private and not allow_private and not allow_localhost:
        raise ValueError(f"SSRF violation: Private network address '{ip_str}' is prohibited without explicit authorization.")


def validate_telemetry_endpoint(
    url: str,
    allow_localhost: bool = False,
    allow_internal_docker_hosts: bool = True,
) -> str:
    """
    Validates a telemetry endpoint URL against SSRF, DNS rebinding, private networks,
    cloud metadata instances, and invalid protocols.

    Returns normalized URL if safe, or raises ValueError with descriptive reason.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Telemetry endpoint URL must be a non-empty string")

    cleaned = url.strip()
    if any(char in cleaned for char in ["\x00", "\r", "\n", " ", "'", '"']):
        raise ValueError("Telemetry endpoint URL contains illegal whitespace or control characters")

    parsed = urlparse(cleaned)

    # 1. Scheme check: only http or https
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Prohibited protocol scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    # 2. Userinfo check: credentials in URL are strictly prohibited
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URL authority (user:pass@host) are strictly prohibited for security.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Telemetry endpoint URL has no valid hostname")

    hostname_lower = hostname.lower()

    # 3. Cloud metadata check
    if hostname_lower in PROHIBITED_METADATA_HOSTS:
        raise ValueError(f"SSRF violation: Access to cloud metadata service '{hostname}' is strictly prohibited.")

    # 4. Check for loopback and localhost
    is_localhost = hostname_lower in ("localhost", "127.0.0.1", "::1")
    if is_localhost and not allow_localhost:
        raise ValueError(f"SSRF violation: Loopback host '{hostname}' is not permitted in production pilot mode.")

    # 5. Check numeric, octal, hex, or mapped representations
    parsed_ip = parse_ip_representation(hostname)
    if parsed_ip is not None:
        _verify_ip_safety(parsed_ip, allow_localhost=allow_localhost, allow_private=allow_internal_docker_hosts)
        return cleaned.rstrip("/")

    # 6. Internal domain fast-path when explicitly authorized
    if allow_internal_docker_hosts and (
        hostname_lower.endswith((".internal", ".local", ".test", ".docker"))
        or hostname_lower in ("prometheus", "jaeger", "vermithor-backend", "vermithor-gateway")
    ):
        return cleaned.rstrip("/")

    # 7. DNS resolution probe for domains
    if not is_localhost:
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
            for entry in addr_info:
                resolved_ip_str = entry[4][0]
                resolved_ip = ipaddress.ip_address(resolved_ip_str)
                _verify_ip_safety(resolved_ip, allow_localhost=allow_localhost, allow_private=allow_internal_docker_hosts)
        except socket.gaierror as exc:
            logger.debug("DNS resolution probe for '%s' returned: %s", hostname, exc)

    return cleaned.rstrip("/")


class SSRFProtectedSyncBackend(httpcore.SyncBackend):
    """
    Hardened network backend that enforces socket-level peer address verification
    upon TCP connection establishment to defeat Time-of-Check to Time-of-Use (TOCTOU)
    DNS rebinding attacks.
    """

    def __init__(self, allow_localhost: bool = False, allow_private: bool = True):
        super().__init__()
        self.allow_localhost = allow_localhost
        self.allow_private = allow_private

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[typing.Any]] = None,
    ) -> httpcore.NetworkStream:
        stream = super().connect_tcp(host, port, timeout, local_address, socket_options)
        sock = getattr(stream, "_sock", None)
        if sock:
            peer_ip_str = sock.getpeername()[0]
            try:
                ip_obj = ipaddress.ip_address(peer_ip_str)
                _verify_ip_safety(
                    ip_obj,
                    allow_localhost=self.allow_localhost,
                    allow_private=self.allow_private,
                )
            except Exception as exc:
                sock.close()
                logger.warning("SSRF / DNS rebinding connection aborted: peer '%s' failed validation: %s", peer_ip_str, exc)
                raise ValueError(f"SSRF / DNS rebinding violation: connected peer '{peer_ip_str}' is prohibited") from exc
        return stream


class SSRFSafeTransport(httpx.HTTPTransport):
    """Custom HTTP transport backed by SSRFProtectedSyncBackend."""

    def __init__(self, allow_localhost: bool = False, allow_private: bool = True, **kwargs):
        super().__init__(**kwargs)
        self._pool = httpcore.ConnectionPool(
            ssl_context=getattr(self._pool, "_ssl_context", None),
            network_backend=SSRFProtectedSyncBackend(
                allow_localhost=allow_localhost,
                allow_private=allow_private,
            ),
            http1=True,
            http2=False,
            retries=0,
        )


class SafeTelemetryHttpClient:
    """
    Hardened HTTP client for querying external telemetry providers (Prometheus, Jaeger, OTel).
    Guarantees:
      - Enforced connection and read timeouts.
      - Streamed response body bounding (max 2 MB) to prevent denial of service and memory expansion.
      - Disables automated redirect following (prevents redirect SSRF).
      - Socket-level peer address pinning to defeat TOCTOU DNS rebinding.
      - Redacts all sensitive authorization headers, JWTs, and secrets from logging and errors.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_READ_TIMEOUT,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ):
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    def execute_query(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_header: Optional[str] = None,
        allow_localhost: bool = False,
        allow_private: bool = False,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Execute an SSRF-validated, timeout-bounded, size-limited HTTP request to a telemetry endpoint.
        Returns (status_code, json_or_error_dict).
        """
        # Validate endpoint before dispatch
        validated_url = validate_telemetry_endpoint(
            url,
            allow_localhost=allow_localhost,
            allow_internal_docker_hosts=allow_private or allow_localhost,
        )

        req_headers = dict(headers or {})
        if auth_header:
            req_headers["Authorization"] = auth_header

        transport = SSRFSafeTransport(
            allow_localhost=allow_localhost,
            allow_private=allow_private,
        )

        try:
            with httpx.Client(
                transport=transport,
                timeout=httpx.Timeout(self.timeout, connect=DEFAULT_CONNECT_TIMEOUT),
                follow_redirects=False,
            ) as client:
                resp = client.request(
                    method=method.upper(),
                    url=validated_url,
                    params=params,
                    headers=req_headers,
                )

                # Check for redirects
                if resp.is_redirect:
                    redirect_target = resp.headers.get("location", "")
                    logger.warning("Telemetry endpoint attempt redirected to '%s' - rejecting unsafe redirect", redirect_target)
                    return resp.status_code, {
                        "status": "error",
                        "error": "Redirects from telemetry endpoints are strictly rejected for security",
                        "redirect_location": redact_sensitive_text(redirect_target),
                    }

                # Check Content-Length if present
                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > self.max_response_bytes:
                    return 413, {
                        "status": "error",
                        "error": f"Response size ({content_length} bytes) exceeds limit ({self.max_response_bytes} bytes)",
                    }

                # Read body and enforce size bounding
                content_bytes = resp.content
                if len(content_bytes) > self.max_response_bytes:
                    return 413, {
                        "status": "error",
                        "error": f"Response body exceeds {self.max_response_bytes} bytes limit",
                    }

                # Parse JSON
                try:
                    payload = resp.json()
                    return resp.status_code, payload
                except Exception:
                    text_preview = resp.text[:300]
                    return resp.status_code, {
                        "status": "non_json",
                        "text": redact_sensitive_text(text_preview),
                    }

        except httpx.ConnectTimeout:
            logger.warning("Safe telemetry client connect timeout for '%s'", validated_url)
            return 504, {"status": "timeout", "error": "Connection timed out"}
        except httpx.ReadTimeout:
            logger.warning("Safe telemetry client read timeout for '%s'", validated_url)
            return 504, {"status": "timeout", "error": "Query read timed out"}
        except httpx.ConnectError as exc:
            logger.warning("Safe telemetry client connection refused for '%s'", validated_url)
            return 503, {"status": "unavailable", "error": f"Connection refused: {redact_sensitive_text(str(exc))}"}
        except ValueError as val_exc:
            logger.warning("Safe telemetry security rejection for '%s': %s", validated_url, val_exc)
            return 400, {"status": "rejected", "error": redact_sensitive_text(str(val_exc))}
        except Exception as exc:
            logger.error("Safe telemetry query unexpected failure: %s", exc)
            return 500, {"status": "error", "error": redact_sensitive_text(str(exc))}
