import collections
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sklearn.cluster import HDBSCAN

from backend.app.common.config import Settings, get_settings
from backend.app.log_intelligence.schemas.logs import LogCategory, LogClusterItem

logger = logging.getLogger(__name__)


class HDBSCANLogClusterer:
    """
    Performs deterministic density-based clustering (HDBSCAN) over dense log vector embeddings.
    Groups semantically related error logs, identifies noise points, computes medoid representative
    messages, and deterministically generates human-readable cluster labels.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def cluster_logs(
        self,
        logs: List[Dict[str, Any]],
        min_cluster_size: Optional[int] = None,
        min_samples: Optional[int] = None,
        include_noise: bool = True,
    ) -> List[LogClusterItem]:
        """
        Execute HDBSCAN clustering on a collection of processed logs with embeddings.

        Args:
            logs: List of log dictionaries containing 'id', 'raw_message', 'normalized_message',
                  'template', 'category', 'service', 'environment', 'severity', 'timestamp',
                  'trace_id', and 'embedding'.
            min_cluster_size: Minimum number of samples in a cluster.
            min_samples: Number of samples in a neighborhood for a core point.
            include_noise: Whether to include noise points in the return list.

        Returns:
            List[LogClusterItem]: List of structured cluster result items.
        """
        if not logs:
            return []

        min_c_size = min_cluster_size or self.settings.HDBSCAN_MIN_CLUSTER_SIZE
        min_samp = min_samples or self.settings.HDBSCAN_MIN_SAMPLES
        metric = self.settings.HDBSCAN_METRIC
        method = self.settings.HDBSCAN_CLUSTER_SELECTION_METHOD
        max_rep = self.settings.CLUSTER_MAX_REPRESENTATIVE_LOGS

        # If total logs are fewer than min_cluster_size, treat all as noise
        if len(logs) < min_c_size:
            if not include_noise:
                return []
            noise_cluster = self._build_cluster_item(
                cluster_id=-1,
                cluster_logs=logs,
                probabilities=[0.0] * len(logs),
                is_noise=True,
                max_representative=max_rep,
            )
            return [noise_cluster]

        # Prepare embeddings matrix
        vectors = []
        for l in logs:
            emb = l.get("embedding")
            if emb is None:
                emb = [0.0] * self.settings.EMBEDDING_DIMENSION
            vectors.append(emb)

        X = np.array(vectors, dtype=np.float32)

        # L2-normalize vectors for cosine-equivalent Euclidean clustering
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        X_norm = X / norms

        # Execute HDBSCAN
        clusterer = HDBSCAN(
            min_cluster_size=min_c_size,
            min_samples=min_samp,
            metric=metric,
            cluster_selection_method=method,
        )
        labels = clusterer.fit_predict(X_norm)
        probabilities = getattr(clusterer, "probabilities_", np.ones(len(logs), dtype=np.float32))

        # Group logs by assigned cluster label
        clusters_map: Dict[int, List[Tuple[Dict[str, Any], float, np.ndarray]]] = collections.defaultdict(list)
        for idx, (log_item, label, prob) in enumerate(zip(logs, labels, probabilities)):
            clusters_map[int(label)].append((log_item, float(prob), X_norm[idx]))

        cluster_results: List[LogClusterItem] = []

        # Process non-noise clusters first (sorted by cluster_id)
        cluster_ids = sorted([cid for cid in clusters_map.keys() if cid != -1])
        for cid in cluster_ids:
            group = clusters_map[cid]
            group_logs = [item[0] for item in group]
            group_probs = [item[1] for item in group]
            group_vecs = np.array([item[2] for item in group])

            cluster_item = self._build_cluster_item(
                cluster_id=cid,
                cluster_logs=group_logs,
                probabilities=group_probs,
                vectors=group_vecs,
                is_noise=False,
                max_representative=max_rep,
            )
            cluster_results.append(cluster_item)

        # Process noise cluster (-1) if present and requested
        if include_noise and -1 in clusters_map:
            noise_group = clusters_map[-1]
            noise_logs = [item[0] for item in noise_group]
            noise_probs = [item[1] for item in noise_group]
            noise_vecs = np.array([item[2] for item in noise_group])

            noise_item = self._build_cluster_item(
                cluster_id=-1,
                cluster_logs=noise_logs,
                probabilities=noise_probs,
                vectors=noise_vecs,
                is_noise=True,
                max_representative=max_rep,
            )
            cluster_results.append(noise_item)

        # Sort clusters by size descending (putting noise at the end)
        cluster_results.sort(key=lambda c: (not c.is_noise, c.size), reverse=True)
        return cluster_results

    def _build_cluster_item(
        self,
        cluster_id: int,
        cluster_logs: List[Dict[str, Any]],
        probabilities: List[float],
        vectors: Optional[np.ndarray] = None,
        is_noise: bool = False,
        max_representative: int = 3,
    ) -> LogClusterItem:
        """Construct a validated LogClusterItem model from grouped logs."""
        size = len(cluster_logs)
        services = sorted(list({l.get("service", "unknown") for l in cluster_logs if l.get("service")}))
        environments = sorted(list({l.get("environment", "unknown") for l in cluster_logs if l.get("environment")}))
        trace_ids = sorted(list({str(l.get("trace_id")) for l in cluster_logs if l.get("trace_id")}))
        log_ids = [l["id"] for l in cluster_logs if "id" in l]

        # Timestamps
        timestamps = [self._parse_ts(l["timestamp"]) for l in cluster_logs if l.get("timestamp")]
        first_seen = min(timestamps) if timestamps else datetime.now()
        last_seen = max(timestamps) if timestamps else datetime.now()

        # Severity distribution
        sev_counts: Dict[str, int] = collections.Counter(
            [str(l.get("severity", "INFO")).upper() for l in cluster_logs]
        )

        # Category distribution
        cat_counter: Dict[str, int] = collections.Counter(
            [str(l.get("category", "UNKNOWN")).upper() for l in cluster_logs]
        )
        dominant_cat_str = cat_counter.most_common(1)[0][0] if cat_counter else "UNKNOWN"
        try:
            category = LogCategory(dominant_cat_str)
        except Exception:
            category = LogCategory.UNKNOWN

        # Representative logs (Medoid calculation)
        representative_messages = self._compute_representative_messages(
            cluster_logs=cluster_logs,
            vectors=vectors,
            max_representative=max_representative,
        )

        # Deterministic cluster label
        label = self._generate_cluster_label(
            category=category,
            services=services,
            representative_messages=representative_messages,
            is_noise=is_noise,
            cluster_id=cluster_id,
        )

        # Confidence score
        avg_prob = float(np.mean(probabilities)) if probabilities else 1.0

        return LogClusterItem(
            cluster_id=cluster_id,
            label=label,
            category=category,
            size=size,
            is_noise=is_noise,
            representative_messages=representative_messages,
            services=services,
            environments=environments,
            first_seen=first_seen,
            last_seen=last_seen,
            severity_distribution=dict(sev_counts),
            log_ids=log_ids,
            trace_ids=trace_ids,
            confidence=avg_prob,
        )

    def _compute_representative_messages(
        self,
        cluster_logs: List[Dict[str, Any]],
        vectors: Optional[np.ndarray],
        max_representative: int,
    ) -> List[str]:
        """Compute the most representative messages for the cluster using vector centroid proximity."""
        if not cluster_logs:
            return []

        # If few logs, deduplicate templates/messages directly
        messages = [
            l.get("template") or l.get("normalized_message") or l.get("raw_message", "")
            for l in cluster_logs
        ]

        if vectors is None or len(cluster_logs) <= max_representative or vectors.shape[0] != len(cluster_logs):
            seen = set()
            rep = []
            for m in messages:
                if m and m not in seen:
                    seen.add(m)
                    rep.append(m)
                if len(rep) >= max_representative:
                    break
            return rep or [messages[0]]

        # Compute centroid of normalized embeddings
        centroid = np.mean(vectors, axis=0)
        c_norm = np.linalg.norm(centroid)
        if c_norm > 0:
            centroid = centroid / c_norm

        # Distances from centroid
        distances = np.linalg.norm(vectors - centroid, axis=1)
        sorted_indices = np.argsort(distances)

        seen_msgs = set()
        rep_msgs = []
        for idx in sorted_indices:
            msg = messages[idx]
            if msg and msg not in seen_msgs:
                seen_msgs.add(msg)
                rep_msgs.append(msg)
            if len(rep_msgs) >= max_representative:
                break

        return rep_msgs or [messages[0]]

    def _generate_cluster_label(
        self,
        category: LogCategory,
        services: List[str],
        representative_messages: List[str],
        is_noise: bool,
        cluster_id: int,
    ) -> str:
        """
        Generate a deterministic, human-readable slug label from category and dominant patterns.
        No LLM is invoked.
        """
        if is_noise:
            return "unclustered_noise"

        cat_prefix = category.value.lower()

        # Extract semantic terms from representative messages
        text_sample = " ".join(representative_messages).lower()

        keywords = []
        if any(k in text_sample for k in ["timeout", "timed out", "deadline"]):
            keywords.append("timeout")
        elif any(k in text_sample for k in ["connection refused", "econnrefused", "connect"]):
            keywords.append("connection_refused")
        elif any(k in text_sample for k in ["pool", "exhausted", "slots", "full"]):
            keywords.append("pool_exhaustion")
        elif any(k in text_sample for k in ["unauthorized", "401", "jwt", "token", "auth"]):
            keywords.append("auth_failure")
        elif any(k in text_sample for k in ["forbidden", "403", "permission"]):
            keywords.append("permission_denied")
        elif any(k in text_sample for k in ["redis", "cache", "miss"]):
            keywords.append("cache_error")
        elif any(k in text_sample for k in ["500", "internal server error", "502", "503"]):
            keywords.append("http_error")
        elif any(k in text_sample for k in ["oom", "memory", "cpu", "heap"]):
            keywords.append("resource_exhaustion")
        elif any(k in text_sample for k in ["deadlock", "lock"]):
            keywords.append("deadlock")

        if not keywords:
            # Clean first representative template into a short keyword slug
            first_msg = representative_messages[0] if representative_messages else "event"
            clean_terms = re.findall(r"\b[a-zA-Z]{3,}\b", first_msg.lower())
            filtered = [t for t in clean_terms if t not in ["the", "and", "for", "with", "from", "service", "error", "failed"]][:2]
            if filtered:
                keywords.append("_".join(filtered))
            else:
                keywords.append("anomaly")

        slug = f"{cat_prefix}_{keywords[0]}"
        return slug

    @staticmethod
    def _parse_ts(ts: Any) -> datetime:
        if isinstance(ts, datetime):
            return ts
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
