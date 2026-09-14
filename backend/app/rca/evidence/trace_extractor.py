import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class TraceEvidenceItem:
    """Structured evidence item derived from distributed trace inspection."""

    def __init__(
        self,
        trace_id: str,
        service: str,
        span_name: str,
        duration_ms: float,
        status: str,
        is_error: bool,
        is_bottleneck: bool,
        description: str,
        strength: float,
        parent_service: Optional[str] = None,
        linked_log_ids: Optional[List[str]] = None,
    ):
        self.trace_id = trace_id
        self.service = service
        self.span_name = span_name
        self.duration_ms = duration_ms
        self.status = status
        self.is_error = is_error
        self.is_bottleneck = is_bottleneck
        self.description = description
        self.strength = strength
        self.parent_service = parent_service
        self.linked_log_ids = linked_log_ids or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "service": self.service,
            "span_name": self.span_name,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "is_error": self.is_error,
            "is_bottleneck": self.is_bottleneck,
            "description": self.description,
            "strength": round(self.strength, 3),
            "parent_service": self.parent_service,
            "linked_log_ids": self.linked_log_ids,
        }


class TraceEvidenceExtractor:
    """
    Extracts causal trace evidence:
    - Identifies failed spans and latency bottleneck spans.
    - Discovers responsible backend/database components across distributed execution paths.
    - Correlates error logs to matching spans via trace_id.
    """

    LATENCY_BOTTLENECK_MS = 500.0  # Spans > 500ms are considered significant bottlenecks

    @classmethod
    def extract_trace_evidence(
        cls,
        signals: List[Dict[str, Any]],
        traces: Optional[List[Dict[str, Any]]] = None,
    ) -> List[TraceEvidenceItem]:
        """
        Extract trace evidence items from available trace data and signal metadata.
        """
        evidence_items: List[TraceEvidenceItem] = []
        raw_traces = list(traces or [])

        # 1. Collect trace information embedded in signal metadata
        for sig in signals:
            meta = sig.get("metadata") or sig.get("metadata_json") or {}
            sig_trace_id = meta.get("trace_id") or sig.get("trace_id")
            if not sig_trace_id:
                continue

            # Check if signal has explicit span data
            spans = meta.get("spans") or meta.get("trace_spans") or []
            if isinstance(spans, list) and spans:
                for span in spans:
                    raw_traces.append({
                        "trace_id": sig_trace_id,
                        "service": span.get("service", sig.get("service", "unknown")),
                        "span_name": span.get("name") or span.get("span_name", "operation"),
                        "duration_ms": float(span.get("duration_ms") or span.get("duration", 0)),
                        "status": span.get("status", "OK"),
                        "error": span.get("error", False) or span.get("status") == "ERROR",
                        "parent_service": span.get("parent_service"),
                        "statement": span.get("statement") or span.get("db_statement"),
                    })
            elif "latency_ms" in meta or "duration_ms" in meta:
                raw_traces.append({
                    "trace_id": sig_trace_id,
                    "service": sig.get("service", "unknown"),
                    "span_name": meta.get("span_name") or meta.get("endpoint") or "request",
                    "duration_ms": float(meta.get("latency_ms") or meta.get("duration_ms", 0)),
                    "status": "ERROR" if sig.get("severity") in ["CRITICAL", "ERROR"] else "OK",
                    "error": sig.get("severity") in ["CRITICAL", "ERROR"],
                    "parent_service": meta.get("caller_service"),
                })

        # Group logs by trace_id for log <-> trace correlation
        logs_by_trace: Dict[str, List[str]] = {}
        for sig in signals:
            t_id = (sig.get("metadata") or {}).get("trace_id") or sig.get("trace_id")
            if t_id:
                logs_by_trace.setdefault(str(t_id), []).append(sig.get("signal_id", "unknown"))

        # Deduplicate and evaluate trace spans
        seen_spans: Set[str] = set()
        for t in raw_traces:
            trace_id = str(t.get("trace_id", "unknown"))
            service = str(t.get("service", "unknown"))
            span_name = str(t.get("span_name", "unknown"))
            duration_ms = float(t.get("duration_ms", 0))
            is_error = bool(t.get("error") or str(t.get("status", "")).upper() == "ERROR")
            parent_service = t.get("parent_service")
            statement = t.get("statement") or ""

            span_key = f"{trace_id}:{service}:{span_name}:{int(duration_ms)}"
            if span_key in seen_spans:
                continue
            seen_spans.add(span_key)

            is_bottleneck = duration_ms >= cls.LATENCY_BOTTLENECK_MS
            linked_logs = logs_by_trace.get(trace_id, [])

            # Compute evidence strength
            strength = 0.50
            desc_parts = []

            is_db_span = any(k in f"{span_name} {statement} {service}".lower() for k in ["postgres", "sql", "db", "query", "redis", "pool"])
            if is_db_span and duration_ms > 100:
                strength += 0.25
                desc_parts.append(f"database span latency: {duration_ms:.0f}ms")
            elif is_bottleneck:
                strength += 0.20
                desc_parts.append(f"latency bottleneck: {duration_ms:.0f}ms")

            if is_error:
                strength += 0.25
                desc_parts.append(f"span failed ({t.get('status', 'ERROR')})")

            if linked_logs:
                strength += 0.15
                desc_parts.append(f"correlated with {len(linked_logs)} error logs")

            strength = min(1.0, max(0.20, strength))
            desc = f"Trace {trace_id[:8]} on {service} ({span_name}): " + ", ".join(desc_parts or [f"{duration_ms:.0f}ms duration"])

            evidence_items.append(
                TraceEvidenceItem(
                    trace_id=trace_id,
                    service=service,
                    span_name=span_name,
                    duration_ms=duration_ms,
                    status="ERROR" if is_error else "OK",
                    is_error=is_error,
                    is_bottleneck=is_bottleneck,
                    description=desc,
                    strength=strength,
                    parent_service=parent_service,
                    linked_log_ids=linked_logs,
                )
            )

        # Sort by strength descending
        evidence_items.sort(key=lambda x: (x.strength, x.duration_ms), reverse=True)
        return evidence_items
