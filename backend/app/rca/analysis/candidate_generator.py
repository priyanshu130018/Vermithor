from datetime import datetime
from typing import Any, Dict, List, Set, Tuple


class CandidateGenerator:
    """Derives structured root cause candidates from correlated observability signals."""

    DB_KEYWORDS = {
        "database", "db", "pool", "sql", "postgres", "mysql",
        "deadlock", "query", "pg_", "hikari", "jdbc", "db_connection",
    }
    CACHE_KEYWORDS = {"redis", "cache", "memcached", "eviction", "cache-service"}
    MEMORY_KEYWORDS = {"memory", "oom", "heap", "garbage", "gc", "ram", "leak"}
    CPU_KEYWORDS = {"cpu", "thread", "load", "throttling", "cfs_quota"}
    INFRA_KEYWORDS = {"cpu", "memory", "disk", "saturation", "oom", "resource", "thread", "garbage"}
    NETWORK_KEYWORDS = {"network", "refused", "econnrefused", "reset", "socket", "unreachable", "packet", "retrans"}
    DNS_KEYWORDS = {
        "dns", "coredns", "resolver", "resolving", "nameserver", "lookup",
        "nxdomain", "servfail", "dns_latency", "dns_resolution", "udp:53",
        "10.96.0.10:53", "port 53",
    }
    STORAGE_KEYWORDS = {"disk", "storage", "filesystem", "enospc", "disk partition", "inode", "volume", "iops", "no space left"}
    AUTH_KEYWORDS = {
        "jwt", "jwks", "unauthorized", "signature", "401", "bearer", "authentication",
        "auth_token", "bearer token", "signing key", "key rotation", "idp",
    }
    DOWNSTREAM_KEYWORDS = {
        "downstream", "partner", "external", "504", "sockettimeout",
        "gateway timeout", "upstream gateway", "httpclient", "http_client", "remote", "thirdparty", "third_party",
    }
    QUEUE_KEYWORDS = {
        "queue", "rabbitmq", "celery", "kafka", "backlog", "consumer",
        "broker", "stalled", "partition lag", "topic partition", "kafka partition",
        "consumergroup", "offset", "poison", "poison_pill",
        "deserialization", "poison pill",
    }
    POISON_PILL_KEYWORDS = {
        "poison", "poison_pill", "poison pill", "deserialization", "malformed json",
        "deserializationexception", "schema validation failure", "corrupt payload",
    }
    TLS_KEYWORDS = {
        "tls", "ssl", "certificate", "cert", "x509", "handshake", "pkix",
        "cert_verify", "certificate_verify_failed", "certificate expired",
    }
    CONFIG_KEYWORDS = {
        "config", "configuration", "feature_flag", "flag", "env var",
        "environment variable", "misconfiguration", "route config",
    }

    @classmethod
    def _is_signal_anomalous(cls, s: Dict[str, Any]) -> bool:
        """Inspect signal type and metric metadata to determine if signal represents an active operational anomaly."""
        if s.get("signal_type") == "ANOMALY":
            return True
        m = s.get("metadata") or s.get("metadata_json") or {}
        m_name = str(m.get("metric_name", "")).lower()
        val = m.get("value")
        if val is not None:
            try:
                fval = float(val)
                if ("utilization" in m_name or "ratio" in m_name) and fval >= 0.85:
                    return True
                if ("error" in m_name or "5xx" in m_name or "401" in m_name or "loss" in m_name or "fetch" in m_name) and fval >= 0.05:
                    return True
                if ("latency" in m_name or "duration" in m_name) and fval >= 1000.0:
                    return True
                if "dns" in m_name and fval >= 500.0:
                    return True
                if ("rate" in m_name or "retrans" in m_name) and fval >= 1000.0:
                    return True
                if ("queue" in m_name or "lag" in m_name or "backlog" in m_name) and fval >= 1000.0:
                    return True
                return False
            except (ValueError, TypeError):
                pass
        if any(k in m_name for k in ("saturation", "exhaustion", "timeout", "spike", "drop", "packet", "stalled")):
            return True
        return False

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
        # or nominal metrics with zero errors and zero anomalies
        has_anomaly_signal = any(cls._is_signal_anomalous(s) for s in signals)
        has_error_severity = any(str(s.get("severity", "")).upper() in ("ERROR", "FATAL", "CRITICAL") for s in signals)
        has_deployment = any(s.get("signal_type") == "DEPLOYMENT" for s in signals)

        if not has_anomaly_signal and not has_error_severity and not has_deployment:
            # All signals are nominal observations without anomalies or errors (transient background noise)
            return [cls._insufficient_evidence_candidate()]

        if len(signals) == 1 and signals[0].get("signal_type") == "EVENT":
            msg = str(signals[0].get("message") or (signals[0].get("metadata") or {}).get("message") or "").lower()
            all_known = (
                cls.DB_KEYWORDS | cls.CACHE_KEYWORDS | cls.INFRA_KEYWORDS | cls.NETWORK_KEYWORDS
                | cls.DNS_KEYWORDS | cls.STORAGE_KEYWORDS | cls.AUTH_KEYWORDS
                | cls.DOWNSTREAM_KEYWORDS | cls.QUEUE_KEYWORDS | cls.TLS_KEYWORDS
                | cls.CONFIG_KEYWORDS
            )
            if not any(kw in msg for kw in all_known):
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

            # Skip nominal metric observations (signals that are not anomalous and not error events)
            if sig_type in ("METRIC", "GAUGE", "COUNTER", "METRIC_OBSERVATION") and not cls._is_signal_anomalous(s):
                continue

            # 1. Authentication / JWT / Token Signing Failure
            # Must evaluate BEFORE downstream/cache checks so 'cached JWKS' or auth-service token verification is prioritized
            if any(kw in combined_text for kw in cls.AUTH_KEYWORDS):
                key = f"DEPENDENCY:{service}:auth"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DEPENDENCY",
                        "candidate_name": f"Authentication failure on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ERROR",
                                "description": f"Authentication/JWT validation failure on {service}.",
                                "strength": 0.95,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 1b. TLS / SSL Certificate Validation Failure
            # Must evaluate BEFORE downstream checks so TLS handshake failures to partners/external endpoints are classified as TLS
            elif any(kw in combined_text for kw in cls.TLS_KEYWORDS):
                key = f"DEPENDENCY:{service}:tls"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DEPENDENCY",
                        "candidate_name": f"TLS certificate or connection failure on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ERROR",
                                "description": f"TLS/SSL certificate validation or handshake failure on {service}.",
                                "strength": 0.95,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 2. DNS Resolution / CoreDNS Resolver Degradation
            # Must evaluate BEFORE downstream external checks so DNS lookups for partner services are categorized as DNS
            elif any(kw in combined_text for kw in cls.DNS_KEYWORDS):
                is_coredns = "coredns" in combined_text or "10.96.0.10:53" in combined_text
                key = f"DEPENDENCY:{service}:dns"
                cand_name = (
                    f"CoreDNS resolution failure on {service}"
                    if is_coredns
                    else f"DNS resolution failure on {service}"
                )
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DEPENDENCY",
                        "candidate_name": cand_name,
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "METRIC" if sig_type == "ANOMALY" else "ERROR",
                                "description": f"DNS resolution latency / UDP packet drop observed on {service}.",
                                "strength": 0.95,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)
                    if is_coredns:
                        candidates_by_key[key]["candidate_name"] = f"CoreDNS resolution failure on {service}"

            # 3. Queue / Message Broker / Kafka Consumer Stall
            # Must evaluate BEFORE storage/cpu so topic partitions and consumer threads are not misclassified as disk/cpu
            elif any(kw in combined_text for kw in cls.QUEUE_KEYWORDS):
                key = f"SERVICE:{service}:queue"
                is_poison_pill = any(kw in combined_text for kw in cls.POISON_PILL_KEYWORDS) and (
                    sig_type == "EVENT" or "error" in combined_text or "exception" in combined_text or str(severity).upper() in ("ERROR", "CRITICAL", "FATAL")
                )
                is_kafka = "kafka" in combined_text or "consumer" in combined_text
                default_name = f"Kafka consumer lag backlog on {service}" if is_kafka else f"Queue processing backlog on {service}"
                poison_name = f"Kafka consumer stall caused by poison pill on {service}" if is_kafka else f"Queue processing stall caused by poison pill on {service}"

                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "SERVICE",
                        "candidate_name": poison_name if is_poison_pill else default_name,
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ERROR" if is_poison_pill else ("METRIC" if sig_type == "ANOMALY" else "EVENT"),
                                "description": f"Message broker consumer lag / processing stall on {service}.",
                                "strength": 0.94 if is_poison_pill else 0.85,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)
                    if is_poison_pill:
                        candidates_by_key[key]["candidate_name"] = poison_name

            # 3. Downstream External Dependency / Partner Gateway Timeout
            # Must evaluate BEFORE database pool check so HTTPClientPool is not misclassified as DB
            elif any(kw in combined_text for kw in cls.DOWNSTREAM_KEYWORDS):
                key = f"DEPENDENCY:{service}:downstream"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DEPENDENCY",
                        "candidate_name": f"Downstream dependency timeout on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ERROR",
                                "description": f"Downstream dependency timeout/HTTP 504 on {service}.",
                                "strength": 0.92,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 3. Disk Space / Storage Partition Exhaustion
            # Must evaluate BEFORE Memory check so 'write buffer to disk partition' is not memory
            elif any(kw in combined_text for kw in cls.STORAGE_KEYWORDS):
                key = f"RESOURCE:{service}:disk"
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "RESOURCE",
                        "candidate_name": f"Disk space exhaustion on {service}",
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "METRIC" if sig_type == "ANOMALY" else "ERROR",
                                "description": f"Storage filesystem partition capacity exhaustion on {service}.",
                                "strength": 0.95,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 4. Deployment or Configuration Regression Candidate
            elif sig_type == "DEPLOYMENT" or "deploy" in combined_text or any(kw in combined_text for kw in cls.CONFIG_KEYWORDS):
                key = f"DEPLOYMENT:{service}"
                is_config = any(kw in combined_text for kw in cls.CONFIG_KEYWORDS)
                cand_name = (
                    f"Configuration regression on {service}"
                    if is_config and sig_type != "DEPLOYMENT"
                    else f"Recent deployment on {service}"
                )
                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DEPLOYMENT",
                        "candidate_name": cand_name,
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "DEPLOYMENT" if sig_type == "DEPLOYMENT" else "ERROR",
                                "description": f"Deployment or configuration regression on {service} immediately prior to operational degradation.",
                                "strength": 0.88,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)

            # 5. Redis / Cache Candidate
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

            # 6. Memory / Heap Leak Candidate
            elif any(kw in combined_text for kw in cls.MEMORY_KEYWORDS):
                key = f"RESOURCE:{service}:memory"
                if key not in candidates_by_key:
                    is_oom_event = any(okw in combined_text for okw in ("oom", "out of memory", "oomkilled", "killed process", "heap space", "leak"))
                    is_anomalous_mem = sig_type == "ANOMALY" or cls._is_signal_anomalous(s) or str(severity).upper() in ("CRITICAL", "FATAL")
                    if not (is_oom_event or is_anomalous_mem):
                        continue
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

            # 7. Infrastructure / CPU Saturation
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

            # 8. Database / Pool / Deadlock Candidate
            elif any(kw in combined_text for kw in cls.DB_KEYWORDS):
                is_pool = any(p in combined_text for p in ("pool", "hikari", "active connection", "connection acquisition"))
                is_deadlock = any(d in combined_text for d in ("deadlock", "lock wait", "lock contention", "deadlock victim", "tuple lock", "sharelock", "exclusive lock"))
                key = f"DATABASE:{service}"
                if is_pool:
                    cand_name = f"Database connection pool exhaustion on {service}"
                elif is_deadlock:
                    cand_name = f"Database deadlock or lock contention on {service}"
                else:
                    cand_name = f"Database degradation on {service}"

                if key not in candidates_by_key:
                    candidates_by_key[key] = {
                        "candidate_type": "DATABASE",
                        "candidate_name": cand_name,
                        "associated_signal_ids": [sig_id],
                        "service": service,
                        "timestamp": s.get("timestamp"),
                        "severity": severity,
                        "evidence": [
                            {
                                "type": "ANOMALY" if sig_type == "ANOMALY" else "ERROR",
                                "description": f"Database signal observed on {service} ({sig_type}: {sig_id}).",
                                "strength": 0.94 if (is_deadlock or is_pool) else 0.85,
                            }
                        ],
                    }
                else:
                    candidates_by_key[key]["associated_signal_ids"].append(sig_id)
                    if is_pool or is_deadlock:
                        candidates_by_key[key]["candidate_name"] = cand_name

            # 10. Network Candidate
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

            # 10. Generic Service Candidate
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
