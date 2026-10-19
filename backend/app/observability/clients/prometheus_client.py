import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from backend.app.common.config import get_settings

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Client for querying Prometheus metrics server with bounded timeouts and error resilience."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        settings = get_settings()
        self.base_url = (base_url or settings.PROMETHEUS_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.OBSERVABILITY_REQUEST_TIMEOUT

    def check_health(self) -> Dict[str, Any]:
        """Check Prometheus server connectivity and active scrape targets status."""
        url = f"{self.base_url}/api/v1/targets"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    active_targets = data.get("activeTargets", [])
                    healthy_count = sum(1 for t in active_targets if t.get("health") == "up")
                    return {
                        "status": "healthy",
                        "base_url": self.base_url,
                        "total_targets": len(active_targets),
                        "healthy_targets": healthy_count,
                        "targets": [
                            {
                                "job": t.get("labels", {}).get("job"),
                                "instance": t.get("labels", {}).get("instance"),
                                "health": t.get("health"),
                                "last_scrape": t.get("lastScrape"),
                                "last_error": t.get("lastError", ""),
                            }
                            for t in active_targets
                        ],
                    }
                return {
                    "status": "degraded",
                    "base_url": self.base_url,
                    "http_status": resp.status_code,
                    "error": resp.text[:200],
                }
        except httpx.ConnectError:
            logger.warning("Prometheus unreachable at %s (Connection Refused)", self.base_url)
            return {"status": "unavailable", "base_url": self.base_url, "error": "Connection refused"}
        except httpx.TimeoutException:
            logger.warning("Prometheus request timed out at %s after %.1fs", self.base_url, self.timeout)
            return {"status": "timeout", "base_url": self.base_url, "error": "Request timed out"}
        except Exception as exc:
            logger.error("Prometheus health check error: %s", exc)
            return {"status": "error", "base_url": self.base_url, "error": str(exc)}

    def query_instant(self, query: str, time_val: Optional[datetime] = None) -> Dict[str, Any]:
        """Execute an instant PromQL query returning vector or scalar data."""
        url = f"{self.base_url}/api/v1/query"
        params: Dict[str, Any] = {"query": query}
        if time_val is not None:
            params["time"] = time_val.timestamp()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    payload = resp.json()
                    if payload.get("status") == "success":
                        result_data = payload.get("data", {}).get("result", [])
                        return {
                            "status": "success",
                            "query": query,
                            "result_type": payload.get("data", {}).get("resultType"),
                            "result": result_data,
                        }
                return {
                    "status": "error",
                    "query": query,
                    "http_status": resp.status_code,
                    "error": resp.text[:200],
                    "result": [],
                }
        except httpx.ConnectError:
            logger.debug("Prometheus connection refused for query: %s", query)
            return {"status": "unavailable", "query": query, "error": "Connection refused", "result": []}
        except httpx.TimeoutException:
            logger.warning("Prometheus query timed out: %s", query)
            return {"status": "timeout", "query": query, "error": "Query timed out", "result": []}
        except Exception as exc:
            logger.error("Prometheus instant query failed: %s", exc)
            return {"status": "error", "query": query, "error": str(exc), "result": []}

    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> Dict[str, Any]:
        """Execute a range PromQL query returning matrix timeseries data."""
        url = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    payload = resp.json()
                    if payload.get("status") == "success":
                        return {
                            "status": "success",
                            "query": query,
                            "result_type": payload.get("data", {}).get("resultType"),
                            "result": payload.get("data", {}).get("result", []),
                        }
                return {
                    "status": "error",
                    "query": query,
                    "http_status": resp.status_code,
                    "error": resp.text[:200],
                    "result": [],
                }
        except httpx.ConnectError:
            return {"status": "unavailable", "query": query, "error": "Connection refused", "result": []}
        except httpx.TimeoutException:
            return {"status": "timeout", "query": query, "error": "Query timed out", "result": []}
        except Exception as exc:
            return {"status": "error", "query": query, "error": str(exc), "result": []}

    def get_service_metrics(self, service: str, window_minutes: int = 15) -> Dict[str, Any]:
        """Retrieve key service performance metrics (requests, errors, latency, active)."""
        metrics_summary: Dict[str, Any] = {
            "service": service,
            "window_minutes": window_minutes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {},
        }

        queries = {
            "request_rate_per_sec": f'sum(rate(http_requests_total{{service="{service}"}}[5m])) or sum(http_requests_total{{service="{service}"}})',
            "error_rate_5xx": f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m])) or sum(http_requests_total{{service="{service}",status=~"5.."}})',
            "latency_p95_seconds": f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m])) by (le))',
            "active_requests": f'active_requests{{service="{service}"}}',
        }

        for metric_name, q in queries.items():
            res = self.query_instant(q)
            val = None
            if res.get("status") == "success" and res.get("result"):
                raw_val = res["result"][0].get("value")
                if raw_val and len(raw_val) > 1:
                    try:
                        parsed = float(raw_val[1])
                        # Filter out NaN or Inf
                        if parsed == parsed and abs(parsed) != float("inf"):
                            val = round(parsed, 4)
                    except (ValueError, TypeError):
                        pass
            metrics_summary["metrics"][metric_name] = {
                "value": val,
                "query": q,
                "status": res.get("status"),
            }

        return metrics_summary
