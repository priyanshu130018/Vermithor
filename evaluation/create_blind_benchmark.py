"""
Generator for the Prompt 20 Independent Blind Evaluation Benchmark.

Creates 24 distinct, versioned synthetic incidents across 10 root-cause families:
1. DNS and service discovery
2. Database connection pool exhaustion
3. Database deadlocks or lock contention
4. Memory exhaustion and OOM kills
5. CPU saturation or thread starvation
6. Kafka poison-pill processing failures
7. Normal Kafka lag or partition rebalancing
8. Deployment or configuration regressions
9. TLS certificate or connection failures
10. Transient network jitter and benign telemetry (Abstention)

Computes SHA-256 checksums and produces a frozen manifest.json.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import yaml

BENCHMARK_DIR = Path(__file__).resolve().parent / "benchmarks" / "blind_generalization_fixtures"
SCENARIOS_DIR = BENCHMARK_DIR / "scenarios"
GT_DIR = BENCHMARK_DIR / "ground_truth"


def generate_cases():
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)

    base_time = "2026-10-21T02:00:00Z"

    cases = [
        # Family 1: DNS and service discovery
        {
            "id": "BLIND-CASE-01",
            "incident_key": "INC-BLIND-501",
            "family": "DNS_AND_SERVICE_DISCOVERY",
            "scenario_name": "CoreDNS Resolver UDP Packet Drop Causing Cache Discovery Failure",
            "target_service": "cart-service",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["dns", "coredns", "resolver"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-501",
                "service": "cart-service",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "dns_resolution_latency_ms", "value": 3400.0, "service": "cart-service", "timestamp": "2026-10-21T02:05:00Z"},
                    {"metric_name": "coredns_forward_request_duration_seconds", "value": 3.2, "service": "cart-service", "timestamp": "2026-10-21T02:05:10Z"},
                ],
                "logs": [
                    {"level": "WARN", "message": "CoreDNS: Resolving redis-cart.internal.net via upstream UDP 10.96.0.10:53 timed out after 3000ms", "service": "cart-service", "timestamp": "2026-10-21T02:06:00Z"},
                    {"level": "ERROR", "message": "ConnectTimeoutException: Timeout resolving redis-cart.internal.net (CoreDNS drop)", "service": "cart-service", "timestamp": "2026-10-21T02:06:15Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-02",
            "incident_key": "INC-BLIND-502",
            "family": "DNS_AND_SERVICE_DISCOVERY",
            "scenario_name": "Stripe Gateway 504 with Healthy 1.4ms DNS Lookup",
            "target_service": "checkout-gateway",
            "severity": "HIGH",
            "is_negative_control": True,
            "expected_keywords": ["downstream", "external", "partner", "gateway timeout"],
            "prohibited_keywords": ["dns", "coredns", "resolver"],
            "agent_input": {
                "incident_key": "INC-BLIND-502",
                "service": "checkout-gateway",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "dns_resolution_latency_ms", "value": 1.4, "service": "checkout-gateway", "timestamp": "2026-10-21T02:05:00Z"},
                    {"metric_name": "http_client_request_timeout_ratio", "value": 0.75, "service": "checkout-gateway", "timestamp": "2026-10-21T02:05:10Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "DNS resolution healthy: api.stripe.com resolved in 1.4ms via 10.96.0.10", "service": "checkout-gateway", "timestamp": "2026-10-21T02:05:30Z"},
                    {"level": "ERROR", "message": "HTTP 504 Gateway Timeout received from external partner payment provider https://api.stripe.com", "service": "checkout-gateway", "timestamp": "2026-10-21T02:06:00Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-03",
            "incident_key": "INC-BLIND-503",
            "family": "DNS_AND_SERVICE_DISCOVERY",
            "scenario_name": "Upstream CoreDNS SERVFAIL Causing Cascading Downstream Gateway Timeout",
            "target_service": "inventory-api",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["dns", "coredns", "resolver", "servfail"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-503",
                "service": "inventory-api",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "dns_resolution_latency_ms", "value": 2850.0, "service": "inventory-api", "timestamp": "2026-10-21T02:05:00Z"},
                    {"metric_name": "http_request_duration_seconds", "value": 6.5, "service": "inventory-api", "timestamp": "2026-10-21T02:05:20Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "CoreDNS: Nameserver 10.96.0.10:53 returned SERVFAIL resolving supplier-db.corp.internal", "service": "inventory-api", "timestamp": "2026-10-21T02:05:40Z"},
                    {"level": "ERROR", "message": "Failed resolving backend supplier: CoreDNS lookup failed with SERVFAIL", "service": "inventory-api", "timestamp": "2026-10-21T02:06:00Z"},
                ],
                "deployments": [],
            },
        },

        # Family 2: Database connection pool exhaustion
        {
            "id": "BLIND-CASE-04",
            "incident_key": "INC-BLIND-504",
            "family": "DATABASE_CONNECTION_POOL",
            "scenario_name": "HikariCP Active Connection Pool Saturation Under Traffic Spike",
            "target_service": "payment-processor",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["database", "pool", "hikaripool", "connection pool"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-504",
                "service": "payment-processor",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "db_connection_pool_utilization", "value": 1.0, "service": "payment-processor", "timestamp": "2026-10-21T02:10:00Z"},
                    {"metric_name": "db_connection_acquisition_latency_ms", "value": 12500.0, "service": "payment-processor", "timestamp": "2026-10-21T02:10:15Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "Connection acquisition timeout: HikariPool-1 - Connection is not available, request timed out after 10000ms (active=100/100)", "service": "payment-processor", "timestamp": "2026-10-21T02:11:00Z"},
                    {"level": "ERROR", "message": "Cannot open connection to PostgreSQL: database connection pool exhausted", "service": "payment-processor", "timestamp": "2026-10-21T02:11:10Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-05",
            "incident_key": "INC-BLIND-505",
            "family": "DATABASE_CONNECTION_POOL",
            "scenario_name": "HttpClientPool Exhaustion with Database Pool Fully Healthy",
            "target_service": "shipping-tracker",
            "severity": "HIGH",
            "is_negative_control": True,
            "expected_keywords": ["downstream", "external", "partner", "httpclient"],
            "prohibited_keywords": ["database", "db", "postgres", "sql"],
            "agent_input": {
                "incident_key": "INC-BLIND-505",
                "service": "shipping-tracker",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "db_connection_pool_utilization", "value": 0.10, "service": "shipping-tracker", "timestamp": "2026-10-21T02:10:00Z"},
                    {"metric_name": "http_client_pool_pending_requests", "value": 85.0, "service": "shipping-tracker", "timestamp": "2026-10-21T02:10:10Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "HikariPool healthy: active=5/50 connections", "service": "shipping-tracker", "timestamp": "2026-10-21T02:10:30Z"},
                    {"level": "ERROR", "message": "HttpClientConnectionPool: Connection pool exhausted while waiting for free route connection to thirdparty-dhl-api.com", "service": "shipping-tracker", "timestamp": "2026-10-21T02:11:00Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-06",
            "incident_key": "INC-BLIND-506",
            "family": "DATABASE_CONNECTION_POOL",
            "scenario_name": "Cascading API 500 Caused by Database Pool Leak",
            "target_service": "order-service",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["database", "pool", "connection pool"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-506",
                "service": "order-service",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "db_connection_pool_utilization", "value": 0.99, "service": "order-service", "timestamp": "2026-10-21T02:10:00Z"},
                    {"metric_name": "http_500_rate", "value": 0.65, "service": "order-service", "timestamp": "2026-10-21T02:10:30Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "Active connection leak: db connection acquisition timeout after 15000ms", "service": "order-service", "timestamp": "2026-10-21T02:10:50Z"},
                    {"level": "ERROR", "message": "HTTP 500: Internal Server Error failed to persist order", "service": "order-service", "timestamp": "2026-10-21T02:11:00Z"},
                ],
                "deployments": [],
            },
        },

        # Family 3: Database deadlocks or lock contention
        {
            "id": "BLIND-CASE-07",
            "incident_key": "INC-BLIND-507",
            "family": "DATABASE_DEADLOCKS_OR_LOCK_CONTENTION",
            "scenario_name": "PostgreSQL Concurrent Transaction Deadlock on Ledger Accounts",
            "target_service": "ledger-service",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["deadlock", "lock", "database"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-507",
                "service": "ledger-service",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "db_deadlocks_total", "value": 48.0, "service": "ledger-service", "timestamp": "2026-10-21T02:15:00Z"},
                    {"metric_name": "db_lock_wait_seconds", "value": 22.0, "service": "ledger-service", "timestamp": "2026-10-21T02:15:15Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "ERROR: deadlock detected: Process 9182 waits for ShareLock on transaction 81920; Process 8192 waits for ExclusiveLock on tuple (4, 12) of relation ledger_accounts", "service": "ledger-service", "timestamp": "2026-10-21T02:15:40Z"},
                    {"level": "ERROR", "message": "TransactionAbortException: Deadlock victim chosen; transaction rolled back", "service": "ledger-service", "timestamp": "2026-10-21T02:16:00Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-08",
            "incident_key": "INC-BLIND-508",
            "family": "DATABASE_DEADLOCKS_OR_LOCK_CONTENTION",
            "scenario_name": "Long-Running Analytical Aggregate Query Without Deadlocks",
            "target_service": "analytics-service",
            "severity": "MEDIUM",
            "is_negative_control": True,
            "expected_keywords": ["database", "degradation", "query"],
            "prohibited_keywords": ["deadlock", "lock contention", "poison"],
            "agent_input": {
                "incident_key": "INC-BLIND-508",
                "service": "analytics-service",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "db_query_duration_seconds", "value": 24.5, "service": "analytics-service", "timestamp": "2026-10-21T02:15:00Z"},
                    {"metric_name": "db_deadlocks_total", "value": 0.0, "service": "analytics-service", "timestamp": "2026-10-21T02:15:10Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "Locks check: 0 deadlocks detected, lock wait count = 0", "service": "analytics-service", "timestamp": "2026-10-21T02:15:30Z"},
                    {"level": "WARN", "message": "Slow query warning: SELECT count(*) FROM event_logs took 24500ms to complete", "service": "analytics-service", "timestamp": "2026-10-21T02:16:00Z"},
                ],
                "deployments": [],
            },
        },

        # Family 4: Memory exhaustion and OOM kills
        {
            "id": "BLIND-CASE-09",
            "incident_key": "INC-BLIND-509",
            "family": "MEMORY_EXHAUSTION_AND_OOM",
            "scenario_name": "JVM Metaspace Leak Causing Linux Kernel OOM Kill",
            "target_service": "catalog-search",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["memory", "oom", "metaspace"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-509",
                "service": "catalog-search",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "container_memory_usage_bytes", "value": 2147483648.0, "service": "catalog-search", "timestamp": "2026-10-21T02:20:00Z"},
                    {"metric_name": "container_memory_limit_bytes", "value": 2147483648.0, "service": "catalog-search", "timestamp": "2026-10-21T02:20:10Z"},
                ],
                "logs": [
                    {"level": "FATAL", "message": "java.lang.OutOfMemoryError: Metaspace limit exceeded under continuous dynamic classloader reload", "service": "catalog-search", "timestamp": "2026-10-21T02:20:30Z"},
                    {"level": "CRITICAL", "message": "kernel: Memory cgroup out of memory: Killed process 1421 (java) total-vm:2097152kB OOMKilled", "service": "catalog-search", "timestamp": "2026-10-21T02:20:45Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-10",
            "incident_key": "INC-BLIND-510",
            "family": "MEMORY_EXHAUSTION_AND_OOM",
            "scenario_name": "Java Heap at 78% During Scheduled Compacting GC Cycle",
            "target_service": "data-sync-worker",
            "severity": "LOW",
            "is_negative_control": True,
            "expected_keywords": ["insufficient", "inconclusive", "nominal"],
            "prohibited_keywords": ["oom", "out of memory", "leak"],
            "agent_input": {
                "incident_key": "INC-BLIND-510",
                "service": "data-sync-worker",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "jvm_memory_used_ratio", "value": 0.78, "service": "data-sync-worker", "timestamp": "2026-10-21T02:20:00Z"},
                    {"metric_name": "jvm_gc_pause_seconds", "value": 0.12, "service": "data-sync-worker", "timestamp": "2026-10-21T02:20:10Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "GC pause young gen: 12ms duration, 420MB freed, heap operating nominally", "service": "data-sync-worker", "timestamp": "2026-10-21T02:20:30Z"},
                    {"level": "INFO", "message": "Data sync batch iteration 180 processed with 0 errors", "service": "data-sync-worker", "timestamp": "2026-10-21T02:21:00Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-11",
            "incident_key": "INC-BLIND-511",
            "family": "MEMORY_EXHAUSTION_AND_OOM",
            "scenario_name": "HTTP 502 Bad Gateway Caused by Upstream Kernel OOM Kill",
            "target_service": "auth-service",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["memory", "oom"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-511",
                "service": "auth-service",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "container_memory_usage_bytes", "value": 1073741824.0, "service": "auth-service", "timestamp": "2026-10-21T02:20:00Z"},
                    {"metric_name": "container_memory_limit_bytes", "value": 1073741824.0, "service": "auth-service", "timestamp": "2026-10-21T02:20:10Z"},
                ],
                "logs": [
                    {"level": "FATAL", "message": "kernel: oom-killer invoked on auth-service pid 2894 container memory exhaustion", "service": "auth-service", "timestamp": "2026-10-21T02:20:30Z"},
                    {"level": "ERROR", "message": "Service process terminated abnormally (exit code 137 OOMKilled)", "service": "auth-service", "timestamp": "2026-10-21T02:20:45Z"},
                ],
                "deployments": [],
            },
        },

        # Family 5: CPU saturation or thread starvation
        {
            "id": "BLIND-CASE-12",
            "incident_key": "INC-BLIND-512",
            "family": "CPU_SATURATION_AND_THREAD_STARVATION",
            "scenario_name": "Linux CFS Quota Throttling Causing Thread Starvation",
            "target_service": "pdf-generator",
            "severity": "HIGH",
            "is_negative_control": False,
            "expected_keywords": ["cpu", "resource saturation", "thread", "throttling"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-512",
                "service": "pdf-generator",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "container_cpu_cfs_throttled_seconds_total", "value": 160.0, "service": "pdf-generator", "timestamp": "2026-10-21T02:25:00Z"},
                    {"metric_name": "cpu_utilization_ratio", "value": 0.99, "service": "pdf-generator", "timestamp": "2026-10-21T02:25:10Z"},
                ],
                "logs": [
                    {"level": "WARN", "message": "CFS cpu quota exceeded: container throttled for 160000ms", "service": "pdf-generator", "timestamp": "2026-10-21T02:25:30Z"},
                    {"level": "ERROR", "message": "ThreadPoolTaskExecutor: Maximum pool size reached; thread starvation on worker threads", "service": "pdf-generator", "timestamp": "2026-10-21T02:26:00Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-13",
            "incident_key": "INC-BLIND-513",
            "family": "CPU_SATURATION_AND_THREAD_STARVATION",
            "scenario_name": "Scheduled Batch Job Running at 92% CPU Without Dropped Tasks",
            "target_service": "nightly-batch-runner",
            "severity": "LOW",
            "is_negative_control": True,
            "expected_keywords": ["insufficient", "inconclusive", "nominal"],
            "prohibited_keywords": ["crash", "poison", "deadlock"],
            "agent_input": {
                "incident_key": "INC-BLIND-513",
                "service": "nightly-batch-runner",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "cpu_utilization_ratio", "value": 0.92, "service": "nightly-batch-runner", "timestamp": "2026-10-21T02:25:00Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "Scheduled compression job running as configured at 92% CPU usage", "service": "nightly-batch-runner", "timestamp": "2026-10-21T02:25:30Z"},
                    {"level": "INFO", "message": "Batch compression chunk 45/50 completed successfully; 0 dropped tasks", "service": "nightly-batch-runner", "timestamp": "2026-10-21T02:26:00Z"},
                ],
                "deployments": [],
            },
        },

        # Family 6: Kafka poison-pill processing failures
        {
            "id": "BLIND-CASE-14",
            "incident_key": "INC-BLIND-514",
            "family": "KAFKA_POISON_PILL",
            "scenario_name": "Corrupt Protobuf Binary Poison Pill Stalling Kafka Consumer",
            "target_service": "analytics-stream",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["poison pill", "kafka", "deserialization"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-514",
                "service": "analytics-stream",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "kafka_consumer_lag_records", "value": 75000.0, "service": "analytics-stream", "timestamp": "2026-10-21T02:30:00Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "DeserializationException: Malformed Protobuf header byte 0xFF at offset 492019", "service": "analytics-stream", "timestamp": "2026-10-21T02:30:30Z"},
                    {"level": "FATAL", "message": "Consumer thread terminated: poison pill message blocking partition 5", "service": "analytics-stream", "timestamp": "2026-10-21T02:31:00Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-15",
            "incident_key": "INC-BLIND-515",
            "family": "KAFKA_POISON_PILL",
            "scenario_name": "Disk Partition ENOSPC on Broker with Partition Keyword in Path",
            "target_service": "kafka-broker-node-3",
            "severity": "CRITICAL",
            "is_negative_control": True,
            "expected_keywords": ["disk space", "disk", "storage"],
            "prohibited_keywords": ["poison pill", "deserialization"],
            "agent_input": {
                "incident_key": "INC-BLIND-515",
                "service": "kafka-broker-node-3",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "disk_space_utilization", "value": 0.99, "service": "kafka-broker-node-3", "timestamp": "2026-10-21T02:30:00Z"},
                ],
                "logs": [
                    {"level": "FATAL", "message": "ENOSPC: No space left on disk partition /var/lib/kafka/data/partition-4 segment flush failed", "service": "kafka-broker-node-3", "timestamp": "2026-10-21T02:30:30Z"},
                    {"level": "ERROR", "message": "Disk volume /var/lib/kafka/data filesystem full", "service": "kafka-broker-node-3", "timestamp": "2026-10-21T02:31:00Z"},
                ],
                "deployments": [],
            },
        },

        # Family 7: Normal Kafka lag or partition rebalancing
        {
            "id": "BLIND-CASE-16",
            "incident_key": "INC-BLIND-516",
            "family": "NORMAL_KAFKA_LAG",
            "scenario_name": "Consumer Group Rebalance Inducing Transient Partition Lag",
            "target_service": "billing-stream-worker",
            "severity": "MEDIUM",
            "is_negative_control": False,
            "expected_keywords": ["kafka consumer lag backlog", "lag backlog", "queue processing"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-516",
                "service": "billing-stream-worker",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "kafka_consumer_lag_records", "value": 18500.0, "service": "billing-stream-worker", "timestamp": "2026-10-21T02:35:00Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "ConsumerCoordinator: PreparingRebalance for group billing-workers", "service": "billing-stream-worker", "timestamp": "2026-10-21T02:35:20Z"},
                    {"level": "INFO", "message": "ConsumerCoordinator: Successfully joined group with 8 assigned partitions; resuming normal fetch loop", "service": "billing-stream-worker", "timestamp": "2026-10-21T02:35:40Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-17",
            "incident_key": "INC-BLIND-517",
            "family": "NORMAL_KAFKA_LAG",
            "scenario_name": "Traffic Spike Lag Backlog With Zero Message Deserialization Errors",
            "target_service": "event-notifier",
            "severity": "MEDIUM",
            "is_negative_control": True,
            "expected_keywords": ["kafka consumer lag backlog", "queue processing"],
            "prohibited_keywords": ["poison pill", "poison_pill", "corrupt message", "deserialization"],
            "agent_input": {
                "incident_key": "INC-BLIND-517",
                "service": "event-notifier",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "kafka_consumer_lag_records", "value": 14200.0, "service": "event-notifier", "timestamp": "2026-10-21T02:35:00Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "Ingestion backlog increasing due to marketing campaign push; processing 1200 msg/sec", "service": "event-notifier", "timestamp": "2026-10-21T02:35:30Z"},
                    {"level": "INFO", "message": "Offset commit succeeded for all active consumer partitions; zero errors", "service": "event-notifier", "timestamp": "2026-10-21T02:36:00Z"},
                ],
                "deployments": [],
            },
        },

        # Family 8: Deployment or configuration regressions
        {
            "id": "BLIND-CASE-18",
            "incident_key": "INC-BLIND-518",
            "family": "DEPLOYMENT_OR_CONFIG_REGRESSION",
            "scenario_name": "Recent Ingress Deployment with Corrupted Dynamic Routing Table",
            "target_service": "api-router",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["deployment", "configuration", "regression"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-518",
                "service": "api-router",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "http_500_rate", "value": 0.85, "service": "api-router", "timestamp": "2026-10-21T02:40:00Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "RouteConfigError: Route '/api/v2/orders' references invalid upstream cluster 'orders-v2-svc'", "service": "api-router", "timestamp": "2026-10-21T02:40:20Z"},
                    {"level": "FATAL", "message": "Configuration reload failure: invalid router ruleset", "service": "api-router", "timestamp": "2026-10-21T02:40:40Z"},
                ],
                "deployments": [
                    {"service": "api-router", "version": "v3.2.0", "change_summary": "Update dynamic ingress route config", "timestamp": "2026-10-21T02:39:00Z"},
                ],
            },
        },
        {
            "id": "BLIND-CASE-19",
            "incident_key": "INC-BLIND-519",
            "family": "DEPLOYMENT_OR_CONFIG_REGRESSION",
            "scenario_name": "Stale Deployment 6 Hours Ago with Active Redis Maxmemory Eviction",
            "target_service": "session-cache",
            "severity": "HIGH",
            "is_negative_control": True,
            "expected_keywords": ["redis", "cache"],
            "prohibited_keywords": ["recent deployment", "v2.1.0"],
            "agent_input": {
                "incident_key": "INC-BLIND-519",
                "service": "session-cache",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "redis_memory_used_ratio", "value": 1.0, "service": "session-cache", "timestamp": "2026-10-21T02:40:00Z"},
                    {"metric_name": "redis_evicted_keys_total", "value": 45000.0, "service": "session-cache", "timestamp": "2026-10-21T02:40:10Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "OOM command not allowed when used memory > 'maxmemory' on redis-cache cluster", "service": "session-cache", "timestamp": "2026-10-21T02:40:30Z"},
                    {"level": "ERROR", "message": "Redis cache eviction storm: session keys being evicted prematurely", "service": "session-cache", "timestamp": "2026-10-21T02:41:00Z"},
                ],
                "deployments": [
                    {"service": "session-cache", "version": "v2.1.0", "change_summary": "Routine image base bump", "timestamp": "2026-10-20T20:40:00Z"},
                ],
            },
        },
        {
            "id": "BLIND-CASE-20",
            "incident_key": "INC-BLIND-520",
            "family": "DEPLOYMENT_OR_CONFIG_REGRESSION",
            "scenario_name": "Environment Variable Misconfiguration Pointing to Wrong Port",
            "target_service": "vault-agent",
            "severity": "HIGH",
            "is_negative_control": False,
            "expected_keywords": ["configuration regression", "deployment or configuration", "configuration"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-520",
                "service": "vault-agent",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "vault_sync_failure_count", "value": 35.0, "service": "vault-agent", "timestamp": "2026-10-21T02:40:00Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "ConfigurationError: Invalid environment variable VAULT_ADDR='http://127.0.0.1:8201': connection refused", "service": "vault-agent", "timestamp": "2026-10-21T02:40:20Z"},
                    {"level": "FATAL", "message": "Failed to initialize vault secret store due to configuration misconfiguration", "service": "vault-agent", "timestamp": "2026-10-21T02:40:40Z"},
                ],
                "deployments": [],
            },
        },

        # Family 9: TLS certificate or connection failures
        {
            "id": "BLIND-CASE-21",
            "incident_key": "INC-BLIND-521",
            "family": "TLS_CERTIFICATE_OR_CONNECTION",
            "scenario_name": "Expired Wildcard TLS Certificate Causing SSL Handshake Failures",
            "target_service": "auth-gateway",
            "severity": "CRITICAL",
            "is_negative_control": False,
            "expected_keywords": ["tls", "certificate", "ssl", "handshake"],
            "prohibited_keywords": [],
            "agent_input": {
                "incident_key": "INC-BLIND-521",
                "service": "auth-gateway",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "tls_handshake_errors_total", "value": 240.0, "service": "auth-gateway", "timestamp": "2026-10-21T02:45:00Z"},
                ],
                "logs": [
                    {"level": "ERROR", "message": "SSL: CERTIFICATE_VERIFY_FAILED: certificate has expired (NotAfter: 2026-10-20T00:00:00Z)", "service": "auth-gateway", "timestamp": "2026-10-21T02:45:20Z"},
                    {"level": "FATAL", "message": "HandshakeFailure: Client unable to verify server certificate for *.corp.domain", "service": "auth-gateway", "timestamp": "2026-10-21T02:45:40Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-22",
            "incident_key": "INC-BLIND-522",
            "family": "TLS_CERTIFICATE_OR_CONNECTION",
            "scenario_name": "Plain HTTP Connection Timeout with Completely Valid TLS Certificate",
            "target_service": "internal-scraper",
            "severity": "MEDIUM",
            "is_negative_control": True,
            "expected_keywords": ["downstream", "network", "timeout", "service degradation"],
            "prohibited_keywords": ["tls", "certificate expired", "certificate failure"],
            "agent_input": {
                "incident_key": "INC-BLIND-522",
                "service": "internal-scraper",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "http_client_timeout_ratio", "value": 0.65, "service": "internal-scraper", "timestamp": "2026-10-21T02:45:00Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "TLS certificate on port 8443 is valid until 2027-10-20; handshake successful", "service": "internal-scraper", "timestamp": "2026-10-21T02:45:15Z"},
                    {"level": "ERROR", "message": "ConnectTimeoutException: Target plain HTTP endpoint 10.0.2.14:8080 timed out after 5000ms", "service": "internal-scraper", "timestamp": "2026-10-21T02:45:30Z"},
                ],
                "deployments": [],
            },
        },

        # Family 10: Transient network jitter and benign telemetry (Abstention)
        {
            "id": "BLIND-CASE-23",
            "incident_key": "INC-BLIND-523",
            "family": "BENIGN_TELEMETRY_AND_ABSTENTION",
            "scenario_name": "Isolated Transient Retry with Zero Anomalies and Healthy Telemetry",
            "target_service": "recommendation-worker",
            "severity": "LOW",
            "is_negative_control": True,
            "expected_keywords": ["insufficient", "inconclusive", "nominal"],
            "prohibited_keywords": ["database", "kafka", "dns", "oom", "deadlock"],
            "agent_input": {
                "incident_key": "INC-BLIND-523",
                "service": "recommendation-worker",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "cpu_utilization_ratio", "value": 0.35, "service": "recommendation-worker", "timestamp": "2026-10-21T02:50:00Z"},
                    {"metric_name": "error_rate", "value": 0.0, "service": "recommendation-worker", "timestamp": "2026-10-21T02:50:10Z"},
                ],
                "logs": [
                    {"level": "INFO", "message": "Client socket read retry 1/3 succeeded on connection pool; normal operation", "service": "recommendation-worker", "timestamp": "2026-10-21T02:50:30Z"},
                    {"level": "INFO", "message": "Recommendation worker heartbeat nominal: 0 errors recorded", "service": "recommendation-worker", "timestamp": "2026-10-21T02:51:00Z"},
                ],
                "deployments": [],
            },
        },
        {
            "id": "BLIND-CASE-24",
            "incident_key": "INC-BLIND-524",
            "family": "BENIGN_TELEMETRY_AND_ABSTENTION",
            "scenario_name": "Multiple Weak Competing Warnings Without Decisive Root Cause",
            "target_service": "user-profile-api",
            "severity": "LOW",
            "is_negative_control": True,
            "expected_keywords": ["inconclusive", "insufficient"],
            "prohibited_keywords": ["redis cache failure", "database connection pool", "dns resolution"],
            "agent_input": {
                "incident_key": "INC-BLIND-524",
                "service": "user-profile-api",
                "lookback_minutes": 15,
                "metrics": [
                    {"metric_name": "cache_hit_ratio", "value": 0.88, "service": "user-profile-api", "timestamp": "2026-10-21T02:50:00Z"},
                    {"metric_name": "p99_latency_ms", "value": 210.0, "service": "user-profile-api", "timestamp": "2026-10-21T02:50:10Z"},
                ],
                "logs": [
                    {"level": "WARN", "message": "Mild cache lookup latency increase (12ms vs nominal 4ms)", "service": "user-profile-api", "timestamp": "2026-10-21T02:50:30Z"},
                    {"level": "WARN", "message": "Minor remote profile sync delay (45ms vs nominal 20ms)", "service": "user-profile-api", "timestamp": "2026-10-21T02:50:45Z"},
                ],
                "deployments": [],
            },
        },
    ]

    answer_keys = {}
    scenario_manifest = []

    for c in cases:
        case_id = c["id"]
        inc_key = c["incident_key"]

        # Write Scenario YAML (strictly agent_input, target_service, metadata - NO answer keys)
        scn_data = {
            "id": case_id,
            "scenario_name": c["scenario_name"],
            "root_cause_family": c["family"],
            "target_service": c["target_service"],
            "severity": c["severity"],
            "environment": "production",
            "is_negative_control": c["is_negative_control"],
            "agent_input": c["agent_input"],
        }

        yaml_path = SCENARIOS_DIR / f"{case_id.lower().replace('-', '_')}.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(scn_data, f, sort_keys=False)

        # Compute SHA-256 of scenario file
        with open(yaml_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        scenario_manifest.append({
            "case_id": case_id,
            "incident_key": inc_key,
            "family": c["family"],
            "filename": yaml_path.name,
            "is_negative_control": c["is_negative_control"],
            "sha256": file_hash,
        })

        # Assemble Answer Key
        answer_keys[inc_key] = {
            "case_id": case_id,
            "family": c["family"],
            "scenario_name": c["scenario_name"],
            "target_service": c["target_service"],
            "is_negative_control": c["is_negative_control"],
            "expected_root_cause_keywords": c["expected_keywords"],
            "prohibited_root_cause_keywords": c["prohibited_keywords"],
        }

    # Write segregated answer keys
    gt_path = GT_DIR / "answer_keys.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(answer_keys, f, indent=2)

    with open(gt_path, "rb") as f:
        gt_hash = hashlib.sha256(f.read()).hexdigest()

    # Write Manifest
    manifest_data = {
        "benchmark_name": "Prompt 20 Independent Blind Evaluation Benchmark",
        "dataset_version": "2.0.0",
        "creation_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(cases),
        "total_families": 10,
        "negative_controls_count": sum(1 for c in cases if c["is_negative_control"]),
        "positive_cases_count": sum(1 for c in cases if not c["is_negative_control"]),
        "answer_keys_file": "ground_truth/answer_keys.json",
        "answer_keys_sha256": gt_hash,
        "scenarios": scenario_manifest,
    }

    manifest_path = BENCHMARK_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Write README
    readme_content = f"""# Blind Generalization Benchmark Fixtures (v2.0.0)

**Dataset Version:** 2.0.0  
**Frozen Timestamp:** {manifest_data['creation_timestamp']}  
**Total Cases:** 24  
**Root-Cause Families:** 10  
**Ground-Truth Answer Keys SHA-256:** `{gt_hash}`  

## Ground-Truth Isolation

Ground truth answer keys are stored exclusively in `ground_truth/answer_keys.json`.
Scenario fixtures in `scenarios/*.yaml` contain only raw telemetry (`agent_input`).
The investigation pipeline receives no access to answer keys, expected causes, or prohibited terms.
"""
    with open(BENCHMARK_DIR / "README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)

    print(f"Successfully generated {len(cases)} blind benchmark cases across 10 families.")
    print(f"Manifest written to {manifest_path} (Answer keys SHA-256: {gt_hash})")


if __name__ == "__main__":
    generate_cases()
