import os
import time
import json
import base64
import hmac
import hashlib
from typing import Any, Dict, Optional
import httpx

DEV_SECRET = os.getenv("JWT_SECRET", "vermithor-dev-secret-key-32-chars-min")
DEFAULT_GATEWAY_URL = os.getenv("VERMITHOR_API_URL", "http://localhost:8080")


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def generate_dev_jwt(
    secret: str = DEV_SECRET,
    issuer: str = "vermithor",
    audience: str = "vermithor-api",
    subject: str = "synthetic-generator-bot",
    expires_in: int = 3600,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "name": "Synthetic Incident Engine",
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
    }
    header_b64 = base64url_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = base64url_encode(json.dumps(payload).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = base64url_encode(sig)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


class VermithorClient:
    def __init__(self, base_url: str = DEFAULT_GATEWAY_URL, secret: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.secret = secret or os.getenv("JWT_SECRET", DEV_SECRET)
        # Attempt to acquire from auth endpoint if available, otherwise sign with secret
        try:
            with httpx.Client(base_url=self.base_url, timeout=3.0) as client:
                res = client.post("/api/v1/auth/dev-token", json={"sub": "synthetic-generator-bot"})
                if res.status_code == 200:
                    self.token = res.json()["access_token"]
                else:
                    self.token = generate_dev_jwt(secret=self.secret)
        except Exception:
            self.token = generate_dev_jwt(secret=self.secret)

    def _headers(self, trace_id: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if trace_id:
            # W3C traceparent format: version-trace_id-parent_id-flags
            headers["traceparent"] = f"00-{trace_id.ljust(32, '0')[:32]}-00f067aa0ba902b7-01"
        return headers

    def check_health(self) -> Dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=5.0) as client:
            resp = client.get("/health")
            resp.raise_for_status()
            return resp.json()

    def post_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = event_data.get("trace_id")
        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            resp = client.post("/api/v1/events", json=event_data, headers=self._headers(trace_id))
            resp.raise_for_status()
            return resp.json()

    def post_metric(self, observation_data: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            resp = client.post("/api/v1/observations", json=observation_data, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def run_correlation(self, correlation_payload: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            resp = client.post("/api/v1/correlations/evaluate", json=correlation_payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def post_group(self, group_payload: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            resp = client.post("/api/v1/correlations/groups", json=group_payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def trigger_rca(self, group_key: str) -> Dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            resp = client.post(f"/api/v1/rca/analyze/{group_key}", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_rag_context(self, incident_key: str, top_k: int = 10) -> Dict[str, Any]:
        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            resp = client.post("/api/v1/rag/context", json={"incident_key": incident_key, "top_k": top_k}, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def generate_summary(self, incident_key: str, regenerate: bool = True) -> Dict[str, Any]:
        param = "?regenerate=true" if regenerate else ""
        with httpx.Client(base_url=self.base_url, timeout=30.0) as client:
            resp = client.post(f"/api/v1/summaries/incident/{incident_key}{param}", headers=self._headers())
            resp.raise_for_status()
            return resp.json()


VermithorClient = VermithorClient
