import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.anomaly.schemas.observation import MetricObservationCreate
from backend.app.anomaly.services.observation_service import ObservationService
from backend.app.correlation.schemas.correlation import SignalInput, SignalType
from backend.app.ingestion.schemas.event import EventCreate, EventType, Severity
from backend.app.ingestion.services.event_service import EventService
from backend.app.observability.clients.jaeger_client import JaegerClient
from backend.app.observability.clients.prometheus_client import PrometheusClient

logger = logging.getLogger(__name__)


class TelemetryEvidenceService:
    """Collects, aggregates, and normalizes live telemetry from Prometheus and Jaeger into Vermithor incident evidence."""

    def __init__(
        self,
        prometheus_client: Optional[PrometheusClient] = None,
        jaeger_client: Optional[JaegerClient] = None,
    ):
        self.prometheus = prometheus_client or PrometheusClient()
        self.jaeger = jaeger_client or JaegerClient()

    def get_telemetry_snapshot(
        self,
        service: str,
        lookback_minutes: int = 15,
    ) -> Dict[str, Any]:
        """Collect live metrics from Prometheus and traces from Jaeger for a given service."""
        now = datetime.now(timezone.utc)
        metrics = self.prometheus.get_service_metrics(service=service, window_minutes=lookback_minutes)
        raw_traces = self.jaeger.get_traces(
            service=service,
            lookback_seconds=lookback_minutes * 60,
            limit=25,
        )
        trace_summaries = self.jaeger.summarize_traces(raw_traces)

        return {
            "service": service,
            "lookback_minutes": lookback_minutes,
            "collected_at": now.isoformat(),
            "sources": {
                "prometheus": {
                    "base_url": self.prometheus.base_url,
                    "metrics": metrics.get("metrics", {}),
                },
                "jaeger": {
                    "base_url": self.jaeger.base_url,
                    "total_traces": len(raw_traces),
                    "summaries": trace_summaries,
                },
            },
        }

    def convert_telemetry_to_evidence(
        self,
        snapshot: Dict[str, Any],
        environment: str = "production",
    ) -> Dict[str, Any]:
        """Transforms a telemetry snapshot into normalized Vermithor observations, events, and correlation signals."""
        service = snapshot.get("service", "unknown")
        now = datetime.now(timezone.utc)

        observations: List[MetricObservationCreate] = []
        events: List[EventCreate] = []
        signals: List[SignalInput] = []

        # 1. Normalize Prometheus metrics into MetricObservations & CorrelationSignals
        metrics_dict = snapshot.get("sources", {}).get("prometheus", {}).get("metrics", {})
        for name, data in metrics_dict.items():
            val = data.get("value")
            if val is not None:
                obs_id = f"obs-{service}-{name}-{int(now.timestamp())}"
                obs = MetricObservationCreate(
                    observation_id=obs_id,
                    timestamp=now,
                    service=service,
                    environment=environment,
                    metric_name=name,
                    metric_value=float(val),
                    unit="sec" if "second" in name else "ratio" if "rate" in name else "count",
                    labels={"source": "prometheus", "query": data.get("query", "")},
                )
                observations.append(obs)

                # Map to correlation signal
                is_anomaly = (name == "error_rate_5xx" and float(val) > 0.05) or (
                    name == "latency_p95_seconds" and float(val) > 1.0
                )
                signals.append(
                    SignalInput(
                        signal_id=obs_id,
                        signal_type=SignalType.METRIC,
                        timestamp=now,
                        service=service,
                        environment=environment,
                        severity="ERROR" if is_anomaly else "INFO",
                        source_reference=obs_id,
                        metadata={
                            "metric_name": name,
                            "metric_value": float(val),
                            "source": "prometheus",
                            "is_anomaly": is_anomaly,
                        },
                    )
                )

        # 2. Normalize Jaeger trace summaries into Events & CorrelationSignals
        trace_summaries = snapshot.get("sources", {}).get("jaeger", {}).get("summaries", [])
        for trace in trace_summaries:
            t_id = trace.get("trace_id", str(uuid.uuid4()))
            has_error = trace.get("has_error", False)
            duration_ms = trace.get("duration_ms", 0.0)
            is_bottleneck = bool(trace.get("bottleneck_spans"))
            start_time_iso = trace.get("start_time")
            t_time = datetime.fromisoformat(str(start_time_iso).replace("Z", "+00:00")) if start_time_iso else now

            evt_severity = Severity.ERROR if has_error else Severity.WARNING if is_bottleneck else Severity.INFO
            msg = (
                f"Trace {t_id}: root={trace.get('root_operation')} duration={duration_ms}ms "
                f"spans={trace.get('span_count')} error={has_error}"
            )

            evt = EventCreate(
                event_id=f"trace-{t_id[:16]}",
                timestamp=t_time,
                service=service,
                environment=environment,
                event_type=EventType.TRACE,
                severity=evt_severity,
                message=msg,
                trace_id=t_id,
                metadata={
                    "source": "jaeger",
                    "duration_ms": duration_ms,
                    "has_error": has_error,
                    "services_involved": trace.get("services_involved", []),
                    "error_spans": trace.get("error_spans", []),
                    "bottleneck_spans": trace.get("bottleneck_spans", []),
                },
            )
            events.append(evt)

            signals.append(
                SignalInput(
                    signal_id=f"trace-{t_id[:16]}",
                    signal_type=SignalType.TRACE,
                    timestamp=t_time,
                    service=service,
                    environment=environment,
                    severity="ERROR" if has_error else "HIGH" if is_bottleneck else "INFO",
                    source_reference=t_id,
                    metadata={
                        "trace_id": t_id,
                        "duration_ms": duration_ms,
                        "has_error": has_error,
                        "source": "jaeger",
                    },
                )
            )

        return {
            "service": service,
            "environment": environment,
            "observations_count": len(observations),
            "events_count": len(events),
            "signals_count": len(signals),
            "observations": observations,
            "events": events,
            "signals": signals,
        }

    def ingest_telemetry_as_evidence(
        self,
        db: Session,
        service: str,
        lookback_minutes: int = 15,
        environment: str = "production",
    ) -> Dict[str, Any]:
        """Full pipeline: collect live telemetry and persist as evidence in database."""
        snapshot = self.get_telemetry_snapshot(service=service, lookback_minutes=lookback_minutes)
        evidence = self.convert_telemetry_to_evidence(snapshot=snapshot, environment=environment)

        persisted_observations = []
        for obs_in in evidence["observations"]:
            obs, _ = ObservationService.create_observation(db, obs_in)
            persisted_observations.append(obs.observation_id)

        persisted_events = []
        for evt_in in evidence["events"]:
            evt, _ = EventService.create_event(db, evt_in)
            persisted_events.append(evt.event_id)

        return {
            "status": "success",
            "service": service,
            "environment": environment,
            "observations_count": len(persisted_observations),
            "events_count": len(persisted_events),
            "signals_count": len(evidence["signals"]),
            "persisted_observations": persisted_observations,
            "persisted_events": persisted_events,
            "signals": [s.model_dump(mode="json") for s in evidence["signals"]],
        }
