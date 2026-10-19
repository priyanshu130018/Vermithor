import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import httpx

from backend.app.common.config import get_settings

logger = logging.getLogger(__name__)


class JaegerClient:
    """Client for querying Jaeger Query API with timeout resilience and trace summarization."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        settings = get_settings()
        self.base_url = (base_url or settings.JAEGER_QUERY_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.OBSERVABILITY_REQUEST_TIMEOUT

    def check_health(self) -> Dict[str, Any]:
        """Check Jaeger query service connectivity and report registered services."""
        url = f"{self.base_url}/api/services"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return {
                        "status": "healthy",
                        "base_url": self.base_url,
                        "services_count": len(data),
                        "services": data,
                    }
                return {
                    "status": "degraded",
                    "base_url": self.base_url,
                    "http_status": resp.status_code,
                    "error": resp.text[:200],
                }
        except httpx.ConnectError:
            logger.warning("Jaeger query unreachable at %s (Connection Refused)", self.base_url)
            return {"status": "unavailable", "base_url": self.base_url, "error": "Connection refused"}
        except httpx.TimeoutException:
            logger.warning("Jaeger query timed out at %s after %.1fs", self.base_url, self.timeout)
            return {"status": "timeout", "base_url": self.base_url, "error": "Request timed out"}
        except Exception as exc:
            logger.error("Jaeger health check error: %s", exc)
            return {"status": "error", "base_url": self.base_url, "error": str(exc)}

    def get_services(self) -> List[str]:
        """Retrieve list of all services that have submitted traces to Jaeger."""
        url = f"{self.base_url}/api/services"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    return resp.json().get("data") or []
        except Exception as exc:
            logger.debug("Failed to retrieve Jaeger services: %s", exc)
        return []

    def get_operations(self, service: str) -> List[str]:
        """Retrieve operations registered for a given service."""
        url = f"{self.base_url}/api/operations"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params={"service": service})
                if resp.status_code == 200:
                    return resp.json().get("data") or []
        except Exception as exc:
            logger.debug("Failed to retrieve operations for %s: %s", service, exc)
        return []

    def get_traces(
        self,
        service: str,
        operation: Optional[str] = None,
        lookback_seconds: int = 900,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent traces for a given service."""
        url = f"{self.base_url}/api/traces"
        params: Dict[str, Any] = {
            "service": service,
            "limit": limit,
            "lookback": f"{lookback_seconds}s",
        }
        if operation:
            params["operation"] = operation

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json().get("data") or []
        except Exception as exc:
            logger.warning("Failed to query Jaeger traces for service '%s': %s", service, exc)
        return []

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full trace details by 32-character hexadecimal trace ID."""
        url = f"{self.base_url}/api/traces/{trace_id}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        return data[0]
        except Exception as exc:
            logger.warning("Failed to query Jaeger trace '%s': %s", trace_id, exc)
        return None

    def summarize_traces(
        self,
        traces: List[Dict[str, Any]],
        bottleneck_threshold_ms: float = 500.0,
    ) -> List[Dict[str, Any]]:
        """Extract structured summaries from raw Jaeger trace responses."""
        summaries: List[Dict[str, Any]] = []

        for trace_obj in traces:
            trace_id = trace_obj.get("traceID", "unknown")
            spans = trace_obj.get("spans", [])
            processes = trace_obj.get("processes", {})

            if not spans:
                continue

            # Identify services involved
            services_involved: Set[str] = set()
            for proc in processes.values():
                s_name = proc.get("serviceName")
                if s_name:
                    services_involved.add(s_name)

            # Find root span (span with no parent references)
            root_span = None
            for span in spans:
                if not span.get("references"):
                    root_span = span
                    break
            if not root_span and spans:
                root_span = spans[0]

            root_process_id = root_span.get("processID")
            root_service = processes.get(root_process_id, {}).get("serviceName", "unknown") if root_process_id else "unknown"
            root_operation = root_span.get("operationName", "unknown")

            # Duration in ms (Jaeger duration is in microseconds)
            duration_ms = round(float(root_span.get("duration", 0)) / 1000.0, 2)
            start_time_us = root_span.get("startTime", 0)
            start_dt = datetime.fromtimestamp(start_time_us / 1000000.0, tz=timezone.utc).isoformat() if start_time_us else None

            # Detect errors and latency bottlenecks across all spans in the trace
            has_error = False
            error_spans: List[Dict[str, Any]] = []
            bottleneck_spans: List[Dict[str, Any]] = []

            for span in spans:
                span_duration_ms = round(float(span.get("duration", 0)) / 1000.0, 2)
                span_proc = processes.get(span.get("processID", ""), {})
                span_service = span_proc.get("serviceName", root_service)
                span_op = span.get("operationName", "unknown")

                # Parse tags
                tags_dict: Dict[str, Any] = {}
                for tag in span.get("tags", []):
                    tags_dict[tag.get("key")] = tag.get("value")

                is_span_error = bool(
                    tags_dict.get("error") is True
                    or str(tags_dict.get("error")).lower() == "true"
                    or int(tags_dict.get("http.status_code", 0) or 0) >= 500
                    or int(tags_dict.get("http.response.status_code", 0) or 0) >= 500
                )

                if is_span_error:
                    has_error = True
                    error_spans.append({
                        "span_id": span.get("spanID"),
                        "service": span_service,
                        "operation": span_op,
                        "status_code": tags_dict.get("http.status_code") or tags_dict.get("http.response.status_code"),
                        "error_message": tags_dict.get("error.message") or tags_dict.get("message"),
                    })

                if span_duration_ms >= bottleneck_threshold_ms:
                    bottleneck_spans.append({
                        "span_id": span.get("spanID"),
                        "service": span_service,
                        "operation": span_op,
                        "duration_ms": span_duration_ms,
                    })

            summaries.append({
                "trace_id": trace_id,
                "root_service": root_service,
                "root_operation": root_operation,
                "start_time": start_dt,
                "duration_ms": duration_ms,
                "span_count": len(spans),
                "services_involved": sorted(list(services_involved)),
                "has_error": has_error,
                "error_spans": error_spans,
                "bottleneck_spans": bottleneck_spans,
            })

        return summaries
