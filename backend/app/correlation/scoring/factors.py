from typing import Optional, Tuple
from backend.app.correlation.schemas.correlation import SignalInput


def evaluate_time_proximity(
    s1: SignalInput,
    s2: SignalInput,
    strong_window: int = 60,
    medium_window: int = 300,
    max_window: int = 900,
) -> Tuple[float, Optional[str]]:
    """Evaluate temporal distance between two signals."""
    delta_seconds = abs((s1.timestamp - s2.timestamp).total_seconds())

    if delta_seconds > max_window:
        return 0.0, f"signals separated by {int(delta_seconds / 60)} minutes (exceeds {int(max_window / 60)}m window)"
    elif delta_seconds <= strong_window:
        return 1.0, f"signals occurred within {int(delta_seconds)} seconds"
    elif delta_seconds <= medium_window:
        ratio = 0.60 + 0.40 * ((medium_window - delta_seconds) / (medium_window - strong_window))
        return round(ratio, 4), f"signals occurred within {int(delta_seconds / 60)} minutes"
    else:
        ratio = 0.20 * ((max_window - delta_seconds) / (max_window - medium_window))
        return round(max(0.05, ratio), 4), f"signals occurred within {int(delta_seconds / 60)} minutes"


def evaluate_service_match(s1: SignalInput, s2: SignalInput) -> Tuple[float, Optional[str]]:
    """Evaluate if both signals originate from or target the same service."""
    if s1.service.lower() == s2.service.lower():
        return 1.0, f"same service: {s1.service}"
    return 0.0, None


def evaluate_environment_match(s1: SignalInput, s2: SignalInput) -> Tuple[float, Optional[str]]:
    """Evaluate if both signals share the same deployment environment."""
    if s1.environment.lower() == s2.environment.lower():
        return 1.0, f"same environment: {s1.environment}"
    return 0.0, f"different environments ({s1.environment} vs {s2.environment})"


def evaluate_trace_match(s1: SignalInput, s2: SignalInput) -> Tuple[float, Optional[str]]:
    """Evaluate if both signals share a distributed trace_id."""
    trace1 = s1.metadata.get("trace_id") if s1.metadata else None
    trace2 = s2.metadata.get("trace_id") if s2.metadata else None

    if trace1 and trace2 and str(trace1).strip() == str(trace2).strip():
        return 1.0, f"shared trace_id: {trace1}"
    return 0.0, None


def evaluate_severity_concordance(s1: SignalInput, s2: SignalInput) -> Tuple[float, Optional[str]]:
    """Evaluate if both signals have concurrent elevated severities."""
    elevated = {"CRITICAL", "HIGH", "ERROR", "SEV1", "SEV2"}
    s1_sev = s1.severity.upper()
    s2_sev = s2.severity.upper()

    if s1_sev in elevated and s2_sev in elevated:
        return 1.0, f"concurrent elevated severities ({s1.severity}, {s2.severity})"
    return 0.0, None


def evaluate_metric_anomaly_relationship(s1: SignalInput, s2: SignalInput) -> Tuple[float, Optional[str]]:
    """Evaluate temporal relationship between a metric anomaly and service event or alert."""
    types = {s1.signal_type.value, s2.signal_type.value}
    if "ANOMALY" in types and ("EVENT" in types or "ALERT" in types):
        if s1.service.lower() == s2.service.lower():
            return 1.0, "metric anomaly temporally correlated with service error/alert"
    return 0.0, None


def evaluate_deployment_proximity(s1: SignalInput, s2: SignalInput) -> Tuple[float, Optional[str]]:
    """
    Evaluate if a deployment event occurred shortly before an anomaly or error signal.
    Explicitly non-causal evidence statement.
    """
    if s1.signal_type.value == "DEPLOYMENT" and s2.signal_type.value in ["ANOMALY", "EVENT", "ALERT"]:
        delta = (s2.timestamp - s1.timestamp).total_seconds()
        if 0 <= delta <= 600:
            mins = int(delta / 60)
            return 1.0, f"deployment occurred {mins} minutes before anomaly/error signal"

    if s2.signal_type.value == "DEPLOYMENT" and s1.signal_type.value in ["ANOMALY", "EVENT", "ALERT"]:
        delta = (s1.timestamp - s2.timestamp).total_seconds()
        if 0 <= delta <= 600:
            mins = int(delta / 60)
            return 1.0, f"deployment occurred {mins} minutes before anomaly/error signal"

    return 0.0, None


def evaluate_log_cluster_relationship(s1: SignalInput, s2: SignalInput) -> Tuple[float, Optional[str]]:
    """
    Evaluate correlation between a log cluster signal and another operational signal (metric anomaly, alert, event).
    """
    s1_meta = s1.metadata or {}
    s2_meta = s2.metadata or {}
    s1_is_cluster = "cluster_id" in s1_meta or "cluster_label" in s1_meta
    s2_is_cluster = "cluster_id" in s2_meta or "cluster_label" in s2_meta

    if not s1_is_cluster and not s2_is_cluster:
        return 0.0, None

    cluster_sig = s1 if s1_is_cluster else s2
    other_sig = s2 if s1_is_cluster else s1
    meta = cluster_sig.metadata or {}

    cluster_label = meta.get("cluster_label") or meta.get("cluster_id") or "cluster"
    cluster_services = [s.lower() for s in meta.get("affected_services", [cluster_sig.service])]

    if other_sig.service.lower() in cluster_services or cluster_sig.service.lower() == other_sig.service.lower():
        return 1.0, f"log cluster '{cluster_label}' active on service '{other_sig.service}'"

    category = str(meta.get("cluster_category", "")).lower()
    if any(k in category for k in ["database", "cache", "resource", "network"]):
        return 0.7, f"log cluster '{cluster_label}' concurrent with {other_sig.service} signal"

    return 0.0, None
