from datetime import datetime
from typing import Any, Dict, List, Set, Tuple


class CandidateGenerator:
    """Derives structured root cause candidates from correlated observability signals."""

    DB_KEYWORDS = {
        "database", "db", "pool", "connection", "sql", "postgres", "mysql",
        "deadlock", "query", "pg_",
    }
    CACHE_KEYWORDS = {"redis", "cache", "memcached", "eviction", "cache-service"}
    MEMORY_KEYWORDS = {"memory", "oom", "heap", "garbage", "gc", "ram", "leak"}
    CPU_KEYWORDS = {"cpu", "thread", "load", "utilization"}
    INFRA_KEYWORDS = {"cpu", "memory", "disk", "saturation", "oom", "resource", "thread", "garbage"}
    NETWORK_KEYWORDS = {"network", "refused", "dns", "econnrefused", "reset", "socket", "unreachable"}

    @classmethod
    def generate_candidates(cls, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate candidate root causes with associated evidence items.

        Returns:
            List[Dict[str, Any]]: Raw candidate objects containing candidate_type,
            candidate_name, associated_signal_ids, and structured evidence.
        """
        if not signals:
            return [cls._insufficient_evidence_candidate()]

        # Check if the group contains ONLY downstream symptom errors (e.g. solitary HTTP 500)
        if len(signals) == 1 and signals[0].get("signal_type") == "EVENT":
            msg = str(signals[0].get("message") or (signals[0].get("metadata") or {}).get("message") or "").lower()
            if not any(kw in msg for kw in cls.DB_KEYWORDS | cls.CACHE_KEYWORDS | cls.INFRA_KEYWORDS | cls.NETWORK_KEYWORDS):
                return [cls._insufficient_evidence_candidate()]

        candidates_by_key: Dict[str, Dict[str, Any]] = {}

        for s in signals:
            sig_id = s.get("signal_id", "unknown")
            sig_type = s.get("signal_type", "EVENT")
            service = s.get("service", "unknown")
            severity = s.get("severity", "INFO")
            metadata = s.get("metadata") or s.get("metadata_json") or {}
            metric_name = str(metadata.get("metric_name", "")).lower()
            msg = str(s.get("message") or metadata.get("message") or "").lower()
            cluster_label = str(metadata.get("cluster_label", "")).lower()
            cluster_cat = str(metadata.get("cluster_category", "")).lower()

            combined_text = f"{metric_name} {msg} {sig_id} {cluster_label} {cluster_cat}".lower()

            # 1. Deployment Candidate
            if sig_type == "DEPLOYMENT" or "deploy" in combined_text:
                key = f"DEPLOYMENT:{service}"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DEPLOYMENT",
                        "candidate_name": f"Recent deployment on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "DEPLOYMENT",
                                "description": f"Deployment executed on {service} immediately prior to operational degradation.",
                                "strength": 0.88,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 2. Redis / Cache Candidate
            elif any(kw in combined_text for kw in cls.CACHE_KEYWORDS):
                key = f"DEPENDENCY:{service}:cache"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DEPENDENCY",
                        "candidate_name": f"Redis cache failure on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ERROR" if sig_type != "ANOMALY" else "ANOMALY",
                                "description": f"Cache/Redis connection or latency failure on {service}.",
                                "strength": 0.90,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 3. Memory / Resource Saturation Candidate
            elif any(kw in combined_text for kw in cls.MEMORY_KEYWORDS):
                key = f"RESOURCE:{service}:memory"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "RESOURCE",
                        "candidate_name": f"Memory exhaustion on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "METRIC" if sig_type == "ANOMALY" else "ERROR",
                                "description": f"Memory limit exceeded / OOM anomaly on {service}.",
                                "strength": 0.92,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 4. Infrastructure / CPU Saturation
            elif any(kw in combined_text for kw in cls.CPU_KEYWORDS | {"cpu_utilization_saturation", "resource"}):
                key = f"INFRASTRUCTURE:{service}:cpu"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "INFRASTRUCTURE",
                        "candidate_name": f"Resource saturation on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "METRIC" if sig_type == "ANOMALY" else "ERROR",
                                "description": f"High CPU utilization / thread starvation on {service}.",
                                "strength": 0.85,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 5. Database Candidate
            elif any(kw in combined_text for kw in cls.DB_KEYWORDS):
                key = f"DATABASE:{service}"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DATABASE",
                        "candidate_name": f"Database degradation on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ANOMALY" if sig_type == "ANOMALY" else "ERROR",
                                "description": f"Database signal observed on {service} ({sig_type}: {sig_id}).",
                                "strength": 0.92 if sig_type == "ANOMALY" else 0.85,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 6. Network Candidate
            elif any(kw in combined_text for kw in cls.NETWORK_KEYWORDS):
                key = f"NETWORK:{service}"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "NETWORK",
                        "candidate_name": f"Network connectivity failure on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ERROR",
                                "description": f"Network connectivity error reported on {service}.",
                                "strength": 0.80,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 7. Generic Service Candidate
            else:
                key = f"SERVICE:{service}"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "SERVICE",
                        "candidate_name": f"Service degradation on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "SERVICE",
                                "description": f"Service degradation signal recorded on {service}.",
                                "strength": 0.65,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

        if not candidates_by_key:
            return [cls._insufficient_evidence_candidate()]

        return list(candidates_by_key.values())

    @staticmethod
    def _insufficient_evidence_candidate() -> Dict[str, Any]:
        return {
            "candidate_type": "UNKNOWN",
            "candidate_name": "Insufficient evidence",
            "associated_signal_ids": [],
            "service": "unknown",
            "timestamp": None,
            "severity": "LOW",
            "evidence": [
                {
                    "type": "ERROR",
                    "description": "Insufficient evidence: isolated symptoms observed without identifiable upstream root cause.",
                    "strength": 0.10,
                }
            ],
        }
