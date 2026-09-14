import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.common.config import Settings, get_settings
from backend.app.common.telemetry import (
    LOG_CLUSTERS_CREATED_TOTAL,
    LOG_CLUSTER_NOISE_TOTAL,
    LOG_CLUSTERING_DURATION_SECONDS,
    LOGS_CLUSTERED_TOTAL,
)
from backend.app.correlation.schemas.correlation import SignalInput, SignalType
from backend.app.log_intelligence.clustering.hdbscan_clusterer import HDBSCANLogClusterer
from backend.app.log_intelligence.embedding.service import EmbeddingService, get_embedding_service
from backend.app.log_intelligence.repositories.log_repository import LogRepository
from backend.app.log_intelligence.schemas.logs import (
    LogCategory,
    LogClusterItem,
    LogClusteringRequest,
    LogClusteringResponse,
)

logger = logging.getLogger(__name__)


class LogClusteringService:
    """
    Orchestrates end-to-end log clustering:
    1. Fetches candidate logs and embeddings across a configured or requested time window.
    2. Executes HDBSCAN density clustering.
    3. Records telemetry metrics.
    4. Provides conversion to downstream correlation signals.
    """

    def __init__(
        self,
        clusterer: Optional[HDBSCANLogClusterer] = None,
        embedding_service: Optional[EmbeddingService] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.clusterer = clusterer or HDBSCANLogClusterer(self.settings)
        self.embedding_service = embedding_service or get_embedding_service()

    def cluster_db_logs(
        self,
        db: Session,
        req: Optional[LogClusteringRequest] = None,
    ) -> LogClusteringResponse:
        """
        Execute clustering on stored processed logs within the specified or default time window.
        """
        start_perf = time.perf_counter()

        now = datetime.now(timezone.utc)
        start_time = req.start_time if (req and req.start_time) else (now - timedelta(seconds=self.settings.CLUSTER_WINDOW_SECONDS))
        end_time = req.end_time if (req and req.end_time) else now
        service = req.service if req else None
        environment = req.environment if req else None
        min_cluster_size = req.min_cluster_size if req else None
        min_samples = req.min_samples if req else None
        include_noise = req.include_noise if req else True

        # Fetch logs from DB
        db_records = LogRepository.get_logs_for_clustering(
            db=db,
            start_time=start_time,
            end_time=end_time,
            service=service,
            environment=environment,
            limit=2000,
        )

        formatted_logs = []
        for log_obj, vec in db_records:
            formatted_logs.append({
                "id": log_obj.id,
                "source_event_id": log_obj.source_event_id,
                "timestamp": log_obj.timestamp,
                "service": log_obj.service,
                "environment": log_obj.environment,
                "severity": log_obj.severity,
                "category": log_obj.category,
                "raw_message": log_obj.raw_message,
                "normalized_message": log_obj.normalized_message,
                "template": log_obj.template,
                "trace_id": log_obj.trace_id,
                "embedding": vec,
            })

        # Run clustering
        clusters = self.clusterer.cluster_logs(
            logs=formatted_logs,
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            include_noise=include_noise,
        )

        duration_sec = time.perf_counter() - start_perf
        duration_ms = duration_sec * 1000.0

        # Record metrics
        total_logs = len(formatted_logs)
        non_noise_clusters = [c for c in clusters if not c.is_noise]
        noise_clusters = [c for c in clusters if c.is_noise]
        noise_count = sum(c.size for c in noise_clusters)

        LOG_CLUSTERING_DURATION_SECONDS.labels(status="success").observe(duration_sec)
        for c in non_noise_clusters:
            LOG_CLUSTERS_CREATED_TOTAL.labels(category=c.category.value).inc()
        for svc in {l["service"] for l in formatted_logs if l.get("service")}:
            LOGS_CLUSTERED_TOTAL.labels(service=svc, environment=environment or "default").inc(
                sum(1 for l in formatted_logs if l.get("service") == svc)
            )
        if noise_count > 0:
            for c in noise_clusters:
                for svc in c.services:
                    LOG_CLUSTER_NOISE_TOTAL.labels(service=svc).inc()

        logger.info(
            "Log clustering completed in %.2fms: %d logs -> %d clusters, %d noise",
            duration_ms,
            total_logs,
            len(non_noise_clusters),
            noise_count,
        )

        return LogClusteringResponse(
            total_logs=total_logs,
            total_clusters=len(non_noise_clusters),
            noise_count=noise_count,
            duration_ms=round(duration_ms, 2),
            clusters=clusters,
        )

    def cluster_in_memory_logs(
        self,
        logs: List[Dict[str, Any]],
        min_cluster_size: Optional[int] = None,
        min_samples: Optional[int] = None,
        include_noise: bool = True,
    ) -> LogClusteringResponse:
        """
        Cluster a list of in-memory log dictionaries. Generates embeddings on-the-fly if missing.
        """
        start_perf = time.perf_counter()

        # Generate missing embeddings if needed
        unembedded_indices = [i for i, l in enumerate(logs) if not l.get("embedding")]
        if unembedded_indices:
            texts = [
                self.embedding_service.format_embedding_input(
                    service=logs[i].get("service", "unknown"),
                    severity=logs[i].get("severity", "INFO"),
                    category=logs[i].get("category", "UNKNOWN"),
                    message=logs[i].get("raw_message") or logs[i].get("message", ""),
                )
                for i in unembedded_indices
            ]
            vectors = self.embedding_service.embed_batch(texts)
            for idx, vec in zip(unembedded_indices, vectors):
                logs[idx]["embedding"] = vec

        clusters = self.clusterer.cluster_logs(
            logs=logs,
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            include_noise=include_noise,
        )

        duration_ms = (time.perf_counter() - start_perf) * 1000.0
        non_noise = [c for c in clusters if not c.is_noise]
        noise_count = sum(c.size for c in clusters if c.is_noise)

        return LogClusteringResponse(
            total_logs=len(logs),
            total_clusters=len(non_noise),
            noise_count=noise_count,
            duration_ms=round(duration_ms, 2),
            clusters=clusters,
        )

    @staticmethod
    def to_correlation_signals(clusters: List[LogClusterItem]) -> List[SignalInput]:
        """
        Convert significant log clusters into structured SignalInput objects
        for consumption by the Vermithor Correlation Engine.
        """
        signals: List[SignalInput] = []
        for cluster in clusters:
            if cluster.is_noise:
                continue

            primary_service = cluster.services[0] if cluster.services else "unknown"
            primary_env = cluster.environments[0] if cluster.environments else "production"

            # Determine dominant severity
            top_severity = "ERROR"
            if cluster.severity_distribution:
                sorted_sev = sorted(
                    cluster.severity_distribution.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
                top_severity = sorted_sev[0][0]

            signal = SignalInput(
                signal_id=f"log-cluster-{cluster.cluster_id}-{cluster.label}",
                signal_type=SignalType.ALERT,
                timestamp=cluster.last_seen,
                service=primary_service,
                environment=primary_env,
                severity=top_severity,
                source_reference=f"cluster-{cluster.cluster_id}",
                metadata={
                    "cluster_id": cluster.cluster_id,
                    "cluster_label": cluster.label,
                    "cluster_category": cluster.category.value,
                    "cluster_size": cluster.size,
                    "affected_services": cluster.services,
                    "representative_messages": cluster.representative_messages,
                    "first_seen": cluster.first_seen.isoformat(),
                    "last_seen": cluster.last_seen.isoformat(),
                    "trace_ids": cluster.trace_ids,
                    "confidence": cluster.confidence,
                },
            )
            signals.append(signal)

        return signals
