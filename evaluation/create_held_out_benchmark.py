"""
Generates the 24 held-out evaluation scenarios with strict physical and logical ground-truth isolation.

- Scenarios are written to: evaluation/benchmarks/held_out_incidents/scenarios/holdout_XX.yaml
  (containing exclusively observational telemetry: incident_key, service, lookback_minutes, metrics, logs, deployments, dependencies)
- Ground-truth answer keys are written to: evaluation/benchmarks/held_out_incidents/ground_truth/answer_keys.json
  (containing expected root cause keywords, categories, abstention requirements, and repair expectations)
"""

import json
from pathlib import Path
import yaml

SCENARIOS_DIR = Path("evaluation/benchmarks/held_out_incidents/scenarios")
GROUND_TRUTH_DIR = Path("evaluation/benchmarks/held_out_incidents/ground_truth")

SCENARIO_DEFINITIONS = [
    # 01. Database Pool Exhaustion
    {
        "id": "HELD-OUT-01",
        "file": "holdout_01.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-101",
            "service": "billing-core",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "hikari_active_connections_ratio",
                    "service": "billing-core",
                    "value": 1.0,
                    "timestamp": "2026-10-20T08:15:00Z",
                },
                {
                    "metric_name": "db_connection_acquisition_latency_ms",
                    "service": "billing-core",
                    "value": 15400.0,
                    "timestamp": "2026-10-20T08:15:00Z",
                },
                {
                    "metric_name": "http_5xx_error_rate_ratio",
                    "service": "billing-core",
                    "value": 0.44,
                    "timestamp": "2026-10-20T08:16:00Z",
                },
            ],
            "logs": [
                {
                    "service": "billing-core",
                    "level": "WARN",
                    "message": "HikariPool-billing: connection acquisition wait duration exceeded 5000ms (active: 80/80, idle: 0)",
                    "timestamp": "2026-10-20T08:14:30Z",
                },
                {
                    "service": "billing-core",
                    "level": "ERROR",
                    "message": "SQLTransientConnectionException: HikariPool-billing - Connection is not available, request timed out after 30000ms",
                    "timestamp": "2026-10-20T08:15:20Z",
                },
            ],
            "deployments": [],
            "dependencies": ["postgres-billing"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-01",
            "scenario_name": "billing_database_connection_pool_starvation",
            "category": "database_pool_exhaustion",
            "injected_cause": "Database connection pool exhaustion on billing-core under sustained invoice settlement load",
            "expected_root_cause_keywords": ["database", "pool", "connection", "hikari"],
            "target_services": ["billing-core", "postgres-billing"],
            "abstain_required": False,
            "repair_appropriate": True,
            "repair_expected_defect": "max_pool_size",
        },
    },

    # 02. Faulty Application Deployment
    {
        "id": "HELD-OUT-02",
        "file": "holdout_02.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-102",
            "service": "identity-service",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "http_500_internal_server_error_ratio",
                    "service": "identity-service",
                    "value": 0.92,
                    "timestamp": "2026-10-20T09:05:00Z",
                },
                {
                    "metric_name": "user_session_validation_latency_ms",
                    "service": "identity-service",
                    "value": 180.0,
                    "timestamp": "2026-10-20T09:05:00Z",
                },
            ],
            "logs": [
                {
                    "service": "identity-service",
                    "level": "ERROR",
                    "message": "NullPointerException: Cannot invoke String.trim() on null subject in JwtClaimsParser.java:84",
                    "timestamp": "2026-10-20T09:02:15Z",
                },
                {
                    "service": "identity-service",
                    "level": "ERROR",
                    "message": "Unhandled servlet exception during POST /api/v2/auth/validate: NullPointerException at parseClaims",
                    "timestamp": "2026-10-20T09:03:00Z",
                },
            ],
            "deployments": [
                {
                    "service": "identity-service",
                    "version": "v2.4.0",
                    "change_summary": "Refactored claims deserializer in JWT payload parser for compliance",
                    "timestamp": "2026-10-20T09:00:00Z",
                }
            ],
            "dependencies": ["redis-session"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-02",
            "scenario_name": "identity_jwt_claims_parser_nullpointer_regression",
            "category": "faulty_deployment",
            "injected_cause": "Faulty application release v2.4.0 introducing NullPointerException during JWT claims parsing",
            "expected_root_cause_keywords": ["deployment", "release", "nullpointer", "npe", "parser"],
            "target_services": ["identity-service"],
            "abstain_required": False,
            "repair_appropriate": True,
            "repair_expected_defect": "null_check",
        },
    },

    # 03. Redis Cache Failure
    {
        "id": "HELD-OUT-03",
        "file": "holdout_03.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-103",
            "service": "catalog-query-service",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "redis_evicted_keys_rate_per_sec",
                    "service": "catalog-query-service",
                    "value": 14500.0,
                    "timestamp": "2026-10-20T09:30:00Z",
                },
                {
                    "metric_name": "redis_memory_used_ratio",
                    "service": "catalog-query-service",
                    "value": 0.98,
                    "timestamp": "2026-10-20T09:30:00Z",
                },
                {
                    "metric_name": "cache_lookup_error_ratio",
                    "service": "catalog-query-service",
                    "value": 0.35,
                    "timestamp": "2026-10-20T09:32:00Z",
                },
            ],
            "logs": [
                {
                    "service": "catalog-query-service",
                    "level": "ERROR",
                    "message": "RedisCommandExecutionException: OOM command not allowed when used memory > 'maxmemory'",
                    "timestamp": "2026-10-20T09:29:40Z",
                },
                {
                    "service": "catalog-query-service",
                    "level": "WARN",
                    "message": "JedisConnectionException: Redis cluster node 10.0.14.8:6379 failed health check during key eviction storm",
                    "timestamp": "2026-10-20T09:30:10Z",
                },
            ],
            "deployments": [],
            "dependencies": ["redis-cluster"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-03",
            "scenario_name": "catalog_redis_maxmemory_eviction_oom",
            "category": "cache_failure",
            "injected_cause": "Redis memory saturation and key eviction storm violating maxmemory constraint",
            "expected_root_cause_keywords": ["redis", "cache", "eviction", "oom", "memory"],
            "target_services": ["catalog-query-service", "redis-cluster"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 04. CPU Saturation / ReDoS Regex
    {
        "id": "HELD-OUT-04",
        "file": "holdout_04.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-104",
            "service": "email-dispatcher",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "node_cpu_utilization_ratio",
                    "service": "email-dispatcher",
                    "value": 0.99,
                    "timestamp": "2026-10-20T10:00:00Z",
                },
                {
                    "metric_name": "active_worker_threads_count",
                    "service": "email-dispatcher",
                    "value": 64.0,
                    "timestamp": "2026-10-20T10:00:00Z",
                },
                {
                    "metric_name": "dispatch_task_latency_ms",
                    "service": "email-dispatcher",
                    "value": 8500.0,
                    "timestamp": "2026-10-20T10:05:00Z",
                },
            ],
            "logs": [
                {
                    "service": "email-dispatcher",
                    "level": "WARN",
                    "message": "Thread starvation detected: 32 worker threads in RUNNABLE state blocked in java.util.regex.Pattern.matcher()",
                    "timestamp": "2026-10-20T09:58:30Z",
                },
                {
                    "service": "email-dispatcher",
                    "level": "WARN",
                    "message": "CFS quota throttling: process email-dispatcher throttled for 78% of runtime period",
                    "timestamp": "2026-10-20T09:59:45Z",
                },
            ],
            "deployments": [],
            "dependencies": ["smtp-relay"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-04",
            "scenario_name": "email_dispatcher_regex_cpu_starvation",
            "category": "cpu_saturation",
            "injected_cause": "High CPU utilization and thread starvation triggered by catastrophic regex backtracking",
            "expected_root_cause_keywords": ["cpu", "thread", "starvation", "utilization", "worker"],
            "target_services": ["email-dispatcher"],
            "abstain_required": False,
            "repair_appropriate": True,
            "repair_expected_defect": "regex_optimization",
        },
    },

    # 05. Memory Leak / Heap Saturation
    {
        "id": "HELD-OUT-05",
        "file": "holdout_05.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-105",
            "service": "telemetry-aggregator",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "jvm_heap_utilization_ratio",
                    "service": "telemetry-aggregator",
                    "value": 0.97,
                    "timestamp": "2026-10-20T10:30:00Z",
                },
                {
                    "metric_name": "jvm_gc_pause_duration_ms",
                    "service": "telemetry-aggregator",
                    "value": 3200.0,
                    "timestamp": "2026-10-20T10:30:00Z",
                },
                {
                    "metric_name": "http_5xx_error_rate_ratio",
                    "service": "telemetry-aggregator",
                    "value": 0.52,
                    "timestamp": "2026-10-20T10:35:00Z",
                },
            ],
            "logs": [
                {
                    "service": "telemetry-aggregator",
                    "level": "ERROR",
                    "message": "java.lang.OutOfMemoryError: Java heap space at java.util.concurrent.ConcurrentLinkedQueue.offer()",
                    "timestamp": "2026-10-20T10:28:40Z",
                },
                {
                    "service": "telemetry-aggregator",
                    "level": "WARN",
                    "message": "GC overhead limit exceeded: 98% of CPU time spent in full garbage collection releasing < 2% heap",
                    "timestamp": "2026-10-20T10:29:10Z",
                },
            ],
            "deployments": [],
            "dependencies": ["clickhouse"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-05",
            "scenario_name": "telemetry_aggregator_unbounded_queue_heap_exhaustion",
            "category": "memory_leak",
            "injected_cause": "Unbounded queue accumulation causing JVM heap exhaustion and OutOfMemoryError",
            "expected_root_cause_keywords": ["memory", "heap", "oom", "leak", "gc"],
            "target_services": ["telemetry-aggregator"],
            "abstain_required": False,
            "repair_appropriate": True,
            "repair_expected_defect": "queue_bounding",
        },
    },

    # 06. Downstream Dependency Timeout
    {
        "id": "HELD-OUT-06",
        "file": "holdout_06.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-106",
            "service": "checkout-orchestrator",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "downstream_call_duration_seconds",
                    "service": "checkout-orchestrator",
                    "value": 30.0,
                    "timestamp": "2026-10-20T11:00:00Z",
                },
                {
                    "metric_name": "http_504_gateway_timeout_ratio",
                    "service": "checkout-orchestrator",
                    "value": 0.86,
                    "timestamp": "2026-10-20T11:00:00Z",
                },
            ],
            "logs": [
                {
                    "service": "checkout-orchestrator",
                    "level": "ERROR",
                    "message": "HttpClientTimeoutException: HTTP 504 Gateway Timeout connecting to partner endpoint https://api.partnerpay.external/v3/authorize",
                    "timestamp": "2026-10-20T10:58:10Z",
                },
                {
                    "service": "checkout-orchestrator",
                    "level": "WARN",
                    "message": "Circuit breaker OPEN for external partner service 'PartnerPayGateway' due to consecutive 30s timeouts",
                    "timestamp": "2026-10-20T10:59:00Z",
                },
            ],
            "deployments": [],
            "dependencies": ["partner-pay-gateway"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-06",
            "scenario_name": "checkout_external_partner_pay_504_timeout",
            "category": "downstream_timeout",
            "injected_cause": "External partner payment gateway outage resulting in persistent HTTP 504 timeouts",
            "expected_root_cause_keywords": ["downstream", "partner", "gateway timeout", "timeout", "504"],
            "target_services": ["checkout-orchestrator", "partner-pay-gateway"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 07. Network Degradation / VPC Latency Spike
    {
        "id": "HELD-OUT-07",
        "file": "holdout_07.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-107",
            "service": "fulfillment-worker",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "network_packet_loss_ratio",
                    "service": "fulfillment-worker",
                    "value": 0.16,
                    "timestamp": "2026-10-20T11:30:00Z",
                },
                {
                    "metric_name": "network_round_trip_latency_ms",
                    "service": "fulfillment-worker",
                    "value": 620.0,
                    "timestamp": "2026-10-20T11:30:00Z",
                },
                {
                    "metric_name": "tcp_retrans_rate_per_sec",
                    "service": "fulfillment-worker",
                    "value": 1400.0,
                    "timestamp": "2026-10-20T11:31:00Z",
                },
            ],
            "logs": [
                {
                    "service": "fulfillment-worker",
                    "level": "WARN",
                    "message": "Netty transport connection drop across VPC peering interface: read timeout after 5000ms",
                    "timestamp": "2026-10-20T11:29:45Z",
                },
                {
                    "service": "fulfillment-worker",
                    "level": "WARN",
                    "message": "TCP socket retransmit counter escalated on interface eth0 (16% packet loss observed)",
                    "timestamp": "2026-10-20T11:30:30Z",
                },
            ],
            "deployments": [],
            "dependencies": ["warehouse-api"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-07",
            "scenario_name": "fulfillment_vpc_network_packet_loss",
            "category": "network_degradation",
            "injected_cause": "Cloud VPC peering network degradation causing 16% packet loss and elevated TCP retransmissions",
            "expected_root_cause_keywords": ["network", "packet", "latency", "loss", "retransmit", "vpc"],
            "target_services": ["fulfillment-worker"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 08. Queue Backlog / Kafka Rebalance Loop
    {
        "id": "HELD-OUT-08",
        "file": "holdout_08.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-108",
            "service": "order-fulfillment-consumer",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "kafka_consumer_lag_records",
                    "service": "order-fulfillment-consumer",
                    "value": 85000.0,
                    "timestamp": "2026-10-20T12:00:00Z",
                },
                {
                    "metric_name": "consumer_rebalance_rate_per_hour",
                    "service": "order-fulfillment-consumer",
                    "value": 12.0,
                    "timestamp": "2026-10-20T12:00:00Z",
                },
            ],
            "logs": [
                {
                    "service": "order-fulfillment-consumer",
                    "level": "ERROR",
                    "message": "CommitFailedException: Consumer group rebalance triggered; offset commit expired due to max.poll.interval.ms exceedance",
                    "timestamp": "2026-10-20T11:58:20Z",
                },
                {
                    "service": "order-fulfillment-consumer",
                    "level": "WARN",
                    "message": "Kafka partition revoked from worker consumer-1 during repeated group stabilization",
                    "timestamp": "2026-10-20T11:59:10Z",
                },
            ],
            "deployments": [],
            "dependencies": ["kafka-cluster"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-08",
            "scenario_name": "order_fulfillment_kafka_consumer_lag_stall",
            "category": "queue_backlog",
            "injected_cause": "Kafka consumer group rebalance loop causing consumer stall and message backlog accumulation",
            "expected_root_cause_keywords": ["queue", "kafka", "backlog", "consumer", "broker", "lag"],
            "target_services": ["order-fulfillment-consumer"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 09. Disk Inode Exhaustion
    {
        "id": "HELD-OUT-09",
        "file": "holdout_09.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-109",
            "service": "document-renderer",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "filesystem_inode_utilization_ratio",
                    "service": "document-renderer",
                    "value": 1.0,
                    "timestamp": "2026-10-20T12:30:00Z",
                },
                {
                    "metric_name": "disk_space_utilization_ratio",
                    "service": "document-renderer",
                    "value": 0.52,
                    "timestamp": "2026-10-20T12:30:00Z",
                },
                {
                    "metric_name": "render_job_failure_ratio",
                    "service": "document-renderer",
                    "value": 0.94,
                    "timestamp": "2026-10-20T12:32:00Z",
                },
            ],
            "logs": [
                {
                    "service": "document-renderer",
                    "level": "ERROR",
                    "message": "IOException: No space left on device: cannot allocate inode in /tmp/render_cache",
                    "timestamp": "2026-10-20T12:28:15Z",
                },
                {
                    "service": "document-renderer",
                    "level": "ERROR",
                    "message": "PosixException: ENOSPC error creating file descriptor for temporary PDF page artifact",
                    "timestamp": "2026-10-20T12:29:05Z",
                },
            ],
            "deployments": [],
            "dependencies": ["storage-nfs"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-09",
            "scenario_name": "document_renderer_disk_inode_exhaustion",
            "category": "disk_exhaustion",
            "injected_cause": "Filesystem inode table exhaustion on /tmp partition preventing temporary file creation",
            "expected_root_cause_keywords": ["disk", "inode", "storage", "filesystem", "enospc"],
            "target_services": ["document-renderer"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 10. Authentication Failure / Expired Certificate
    {
        "id": "HELD-OUT-10",
        "file": "holdout_10.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-110",
            "service": "customer-portal-gateway",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "http_401_unauthorized_rate_ratio",
                    "service": "customer-portal-gateway",
                    "value": 0.96,
                    "timestamp": "2026-10-20T13:00:00Z",
                },
                {
                    "metric_name": "jwt_token_validation_failure_ratio",
                    "service": "customer-portal-gateway",
                    "value": 0.98,
                    "timestamp": "2026-10-20T13:00:00Z",
                },
            ],
            "logs": [
                {
                    "service": "customer-portal-gateway",
                    "level": "ERROR",
                    "message": "SignatureVerificationException: JWT signature rejected: IdP signing certificate expired on 2026-10-19T23:59:59Z",
                    "timestamp": "2026-10-20T12:58:30Z",
                },
                {
                    "service": "customer-portal-gateway",
                    "level": "WARN",
                    "message": "JwksClient: public key kid 'cert-2024-oct' revoked or expired by upstream authorization server",
                    "timestamp": "2026-10-20T12:59:15Z",
                },
            ],
            "deployments": [],
            "dependencies": ["auth0-idp"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-10",
            "scenario_name": "customer_portal_jwt_idp_cert_expiry",
            "category": "authentication_failure",
            "injected_cause": "Upstream Identity Provider signing certificate expiration triggering systemic JWT verification failure",
            "expected_root_cause_keywords": ["auth", "unauthorized", "jwt", "token", "signature", "certificate", "idp"],
            "target_services": ["customer-portal-gateway", "auth0-idp"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 11. Two Simultaneous Contributing Failures (Redis Cache Eviction -> DB Saturation)
    {
        "id": "HELD-OUT-11",
        "file": "holdout_11.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-111",
            "service": "pricing-calculator",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "redis_cache_miss_ratio",
                    "service": "pricing-calculator",
                    "value": 0.99,
                    "timestamp": "2026-10-20T13:30:00Z",
                },
                {
                    "metric_name": "db_pool_active_connections_ratio",
                    "service": "pricing-calculator",
                    "value": 1.0,
                    "timestamp": "2026-10-20T13:31:00Z",
                },
                {
                    "metric_name": "calculation_response_latency_ms",
                    "service": "pricing-calculator",
                    "value": 4500.0,
                    "timestamp": "2026-10-20T13:32:00Z",
                },
            ],
            "logs": [
                {
                    "service": "pricing-calculator",
                    "level": "WARN",
                    "message": "Cache stampede: Redis cache eviction evicted 100,000 item prices simultaneously",
                    "timestamp": "2026-10-20T13:29:45Z",
                },
                {
                    "service": "pricing-calculator",
                    "level": "ERROR",
                    "message": "HikariPool-pricing: active connections saturated (50/50) following sudden cache miss surge",
                    "timestamp": "2026-10-20T13:31:00Z",
                },
            ],
            "deployments": [],
            "dependencies": ["redis-cache", "postgres-pricing"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-11",
            "scenario_name": "pricing_redis_eviction_cascading_to_db_pool",
            "category": "multi_cause_cascading",
            "injected_cause": "Redis cache eviction storm cascading into database connection pool exhaustion",
            "expected_root_cause_keywords": ["redis", "cache", "database", "pool", "cascade"],
            "target_services": ["pricing-calculator"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 12. Misleading Coincidental Documentation Deployment with DB Deadlock
    {
        "id": "HELD-OUT-12",
        "file": "holdout_12.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-112",
            "service": "subscription-api",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "db_active_connections_ratio",
                    "service": "subscription-api",
                    "value": 0.98,
                    "timestamp": "2026-10-20T14:25:00Z",
                },
                {
                    "metric_name": "http_5xx_error_rate_ratio",
                    "service": "subscription-api",
                    "value": 0.38,
                    "timestamp": "2026-10-20T14:26:00Z",
                },
            ],
            "logs": [
                {
                    "service": "subscription-api",
                    "level": "ERROR",
                    "message": "PSQLException: ERROR: deadlock detected between transaction 849201 and 849208 on table subscription_leases",
                    "timestamp": "2026-10-20T14:24:30Z",
                },
                {
                    "service": "subscription-api",
                    "level": "WARN",
                    "message": "Transaction aborted due to PostgreSQL lock acquisition deadlock graph cycle",
                    "timestamp": "2026-10-20T14:25:10Z",
                },
            ],
            "deployments": [
                {
                    "service": "subscription-api",
                    "version": "v1.4.2",
                    "change_summary": "Updated swagger openapi documentation and markdown changelog",
                    "timestamp": "2026-10-20T14:00:00Z",
                }
            ],
            "dependencies": ["postgres-sub"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-12",
            "scenario_name": "subscription_db_deadlock_with_coincidental_docs_release",
            "category": "database_deadlock",
            "injected_cause": "PostgreSQL transaction deadlock contention on subscription_leases (deployment was docs-only and unplausible)",
            "expected_root_cause_keywords": ["database", "deadlock", "postgres", "sql", "pool"],
            "target_services": ["subscription-api", "postgres-sub"],
            "abstain_required": False,
            "repair_appropriate": True,
            "repair_expected_defect": "transaction_ordering",
        },
    },

    # 13. Stale Telemetry (Abstention Test)
    {
        "id": "HELD-OUT-13",
        "file": "holdout_13.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-113",
            "service": "invoice-generator",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "LOW",
            "metrics": [
                {
                    "metric_name": "cpu_utilization_ratio",
                    "service": "invoice-generator",
                    "value": 0.15,
                    "timestamp": "2026-10-06T10:00:00Z",  # 14 days old
                },
                {
                    "metric_name": "http_error_rate_ratio",
                    "service": "invoice-generator",
                    "value": 0.001,
                    "timestamp": "2026-10-06T10:00:00Z",
                },
            ],
            "logs": [
                {
                    "service": "invoice-generator",
                    "level": "INFO",
                    "message": "Routine hourly batch invoice generator completed successfully with 0 errors",
                    "timestamp": "2026-10-20T14:50:00Z",
                }
            ],
            "deployments": [],
            "dependencies": ["postgres-invoice"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-13",
            "scenario_name": "invoice_stale_telemetry_abstention",
            "category": "stale_telemetry_abstention",
            "injected_cause": "Telemetry metrics are 14 days stale; agent must recognize missing current telemetry and abstain",
            "expected_root_cause_keywords": ["insufficient", "stale", "missing", "inconclusive", "unknown"],
            "target_services": ["invoice-generator"],
            "abstain_required": True,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 14. Nominal Maintenance Window (Abstention Test)
    {
        "id": "HELD-OUT-14",
        "file": "holdout_14.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-114",
            "service": "inventory-sync",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "LOW",
            "metrics": [
                {
                    "metric_name": "cpu_utilization_ratio",
                    "service": "inventory-sync",
                    "value": 0.42,
                    "timestamp": "2026-10-20T15:10:00Z",
                },
                {
                    "metric_name": "memory_utilization_ratio",
                    "service": "inventory-sync",
                    "value": 0.51,
                    "timestamp": "2026-10-20T15:10:00Z",
                },
                {
                    "metric_name": "http_5xx_error_rate_ratio",
                    "service": "inventory-sync",
                    "value": 0.002,
                    "timestamp": "2026-10-20T15:15:00Z",
                },
            ],
            "logs": [
                {
                    "service": "inventory-sync",
                    "level": "WARN",
                    "message": "Scheduled maintenance window active: worker paused for 120s awaiting cloud replica sync",
                    "timestamp": "2026-10-20T15:12:00Z",
                }
            ],
            "deployments": [],
            "dependencies": ["warehouse-db"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-14",
            "scenario_name": "inventory_sync_nominal_maintenance_abstention",
            "category": "nominal_maintenance_abstention",
            "injected_cause": "Scheduled maintenance window with transient non-error pause; metrics nominal; must abstain",
            "expected_root_cause_keywords": ["insufficient", "nominal", "healthy", "maintenance", "inconclusive", "unknown"],
            "target_services": ["inventory-sync"],
            "abstain_required": True,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 15. Ambiguous Multi-Signal Telemetry (Abstention Test)
    {
        "id": "HELD-OUT-15",
        "file": "holdout_15.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-115",
            "service": "search-federator",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "MEDIUM",
            "metrics": [
                {
                    "metric_name": "cpu_utilization_ratio",
                    "service": "search-federator",
                    "value": 0.64,
                    "timestamp": "2026-10-20T15:30:00Z",
                },
                {
                    "metric_name": "request_latency_ms",
                    "service": "search-federator",
                    "value": 280.0,
                    "timestamp": "2026-10-20T15:30:00Z",
                },
                {
                    "metric_name": "memory_utilization_ratio",
                    "service": "search-federator",
                    "value": 0.69,
                    "timestamp": "2026-10-20T15:30:00Z",
                },
            ],
            "logs": [
                {
                    "service": "search-federator",
                    "level": "INFO",
                    "message": "Cluster rebalance task running in background",
                    "timestamp": "2026-10-20T15:28:00Z",
                },
                {
                    "service": "search-federator",
                    "level": "WARN",
                    "message": "Moderate latency increase on GET /search/suggest (280ms)",
                    "timestamp": "2026-10-20T15:29:10Z",
                },
            ],
            "deployments": [],
            "dependencies": ["ranking-service", "snippet-service"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-15",
            "scenario_name": "search_federator_ambiguous_weak_telemetry",
            "category": "ambiguous_multi_cause",
            "injected_cause": "Simultaneous weak non-anomalous signals across CPU (64%) and memory (69%); must abstain",
            "expected_root_cause_keywords": ["ambiguous", "multiple", "uncertain", "competing", "inconclusive", "insufficient"],
            "target_services": ["search-federator"],
            "abstain_required": True,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 16. Sparse Telemetry with Solitary Client Disconnect (Abstention Test)
    {
        "id": "HELD-OUT-16",
        "file": "holdout_16.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-116",
            "service": "recommendation-engine",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "LOW",
            "metrics": [],  # Agent collection down; zero metrics
            "logs": [
                {
                    "service": "recommendation-engine",
                    "level": "WARN",
                    "message": "Client closed HTTP connection prematurely before response payload fully streamed",
                    "timestamp": "2026-10-20T16:00:00Z",
                }
            ],
            "deployments": [],
            "dependencies": ["user-graph-db"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-16",
            "scenario_name": "recommendation_sparse_telemetry_abstention",
            "category": "sparse_telemetry_abstention",
            "injected_cause": "Sparse telemetry with zero metrics and single client disconnect warning; must abstain",
            "expected_root_cause_keywords": ["insufficient", "sparse", "missing", "inconclusive", "unknown"],
            "target_services": ["recommendation-engine"],
            "abstain_required": True,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 17. PostgreSQL Transaction ID Wraparound Threat
    {
        "id": "HELD-OUT-17",
        "file": "holdout_17.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-117",
            "service": "user-profiles",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "pg_oldest_txid_age_ratio",
                    "service": "user-profiles",
                    "value": 0.95,
                    "timestamp": "2026-10-20T16:30:00Z",
                },
                {
                    "metric_name": "db_read_iops_saturation_ratio",
                    "service": "user-profiles",
                    "value": 0.98,
                    "timestamp": "2026-10-20T16:30:00Z",
                },
            ],
            "logs": [
                {
                    "service": "user-profiles",
                    "level": "ERROR",
                    "message": "PSQLException: database 'profiles' must be vacuumed within 1000000 transactions to prevent wraparound failure",
                    "timestamp": "2026-10-20T16:28:10Z",
                },
                {
                    "service": "user-profiles",
                    "level": "WARN",
                    "message": "Autovacuum worker starved on table 'user_attributes_history' due to active exclusive locks",
                    "timestamp": "2026-10-20T16:29:00Z",
                },
            ],
            "deployments": [],
            "dependencies": ["postgres-profiles"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-17",
            "scenario_name": "user_profiles_postgres_txid_wraparound",
            "category": "database_wraparound",
            "injected_cause": "PostgreSQL database transaction ID wraparound failure threat requiring immediate table vacuum",
            "expected_root_cause_keywords": ["database", "postgres", "vacuum", "wraparound", "sql"],
            "target_services": ["user-profiles", "postgres-profiles"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 18. Bad Application Release with Broken SQL Migration
    {
        "id": "HELD-OUT-18",
        "file": "holdout_18.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-118",
            "service": "notification-service",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "http_500_error_rate_ratio",
                    "service": "notification-service",
                    "value": 0.88,
                    "timestamp": "2026-10-20T17:05:00Z",
                }
            ],
            "logs": [
                {
                    "service": "notification-service",
                    "level": "ERROR",
                    "message": "AlembicMigrationError: syntax error at or near 'CONSTRAIN' in 008_delivery_pref.py: relation does not exist",
                    "timestamp": "2026-10-20T17:01:20Z",
                },
                {
                    "service": "notification-service",
                    "level": "ERROR",
                    "message": "Service startup failed: failed to apply database migration revision 008_delivery_pref",
                    "timestamp": "2026-10-20T17:02:10Z",
                },
            ],
            "deployments": [
                {
                    "service": "notification-service",
                    "version": "v3.2.0",
                    "change_summary": "Added user delivery preferences schema migration",
                    "timestamp": "2026-10-20T17:00:00Z",
                }
            ],
            "dependencies": ["postgres-notif"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-18",
            "scenario_name": "notification_broken_migration_release",
            "category": "faulty_deployment",
            "injected_cause": "Release v3.2.0 contained broken Alembic SQL migration syntax blocking service startup",
            "expected_root_cause_keywords": ["deployment", "release", "migration", "schema", "alembic", "sql"],
            "target_services": ["notification-service"],
            "abstain_required": False,
            "repair_appropriate": True,
            "repair_expected_defect": "sql_migration_syntax",
        },
    },

    # 19. Celery Worker Pool Stall
    {
        "id": "HELD-OUT-19",
        "file": "holdout_19.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-119",
            "service": "report-worker",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "celery_unacknowledged_tasks_count",
                    "service": "report-worker",
                    "value": 12500.0,
                    "timestamp": "2026-10-20T17:30:00Z",
                },
                {
                    "metric_name": "active_worker_concurrency_ratio",
                    "service": "report-worker",
                    "value": 1.0,
                    "timestamp": "2026-10-20T17:30:00Z",
                },
            ],
            "logs": [
                {
                    "service": "report-worker",
                    "level": "WARN",
                    "message": "Celery: Worker hard time limit (300s) exceeded for task generate_monthly_pdf",
                    "timestamp": "2026-10-20T17:28:40Z",
                },
                {
                    "service": "report-worker",
                    "level": "ERROR",
                    "message": "TaskRevokedException: Celery worker processes frozen on unyielding socket IO; queue backlog growing",
                    "timestamp": "2026-10-20T17:29:30Z",
                },
            ],
            "deployments": [],
            "dependencies": ["rabbitmq-broker"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-19",
            "scenario_name": "report_worker_celery_task_timeout_stall",
            "category": "queue_stall",
            "injected_cause": "Celery worker concurrency saturation and task timeout stall causing queue backlog accumulation",
            "expected_root_cause_keywords": ["queue", "celery", "rabbitmq", "worker", "backlog", "stall"],
            "target_services": ["report-worker"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 20. Disk Partition Saturation from Debug Logs
    {
        "id": "HELD-OUT-20",
        "file": "holdout_20.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-120",
            "service": "audit-logger",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "disk_space_used_bytes_ratio",
                    "service": "audit-logger",
                    "value": 0.99,
                    "timestamp": "2026-10-20T18:00:00Z",
                }
            ],
            "logs": [
                {
                    "service": "audit-logger",
                    "level": "ERROR",
                    "message": "Logback Appender failed: no space left on device (/var/log/audit/audit.log)",
                    "timestamp": "2026-10-20T17:58:10Z",
                },
                {
                    "service": "audit-logger",
                    "level": "ERROR",
                    "message": "POSIX error ENOSPC: volume /var/log capacity exhausted by verbose debug trace logging",
                    "timestamp": "2026-10-20T17:59:00Z",
                },
            ],
            "deployments": [],
            "dependencies": ["local-disk"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-20",
            "scenario_name": "audit_logger_disk_partition_saturation",
            "category": "disk_exhaustion",
            "injected_cause": "Local disk partition capacity exhaustion on /var/log preventing application write operations",
            "expected_root_cause_keywords": ["disk", "storage", "filesystem", "enospc", "partition", "volume"],
            "target_services": ["audit-logger"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 21. Native Resident Memory Leak (OOM Killer)
    {
        "id": "HELD-OUT-21",
        "file": "holdout_21.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-121",
            "service": "crypto-signer",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "process_resident_memory_bytes_ratio",
                    "service": "crypto-signer",
                    "value": 0.97,
                    "timestamp": "2026-10-20T18:30:00Z",
                },
                {
                    "metric_name": "system_oom_killer_invocations",
                    "service": "crypto-signer",
                    "value": 3.0,
                    "timestamp": "2026-10-20T18:30:00Z",
                },
            ],
            "logs": [
                {
                    "service": "crypto-signer",
                    "level": "ERROR",
                    "message": "Kernel: Out of memory: Kill process (crypto-signer) score 950 or sacrifice child",
                    "timestamp": "2026-10-20T18:28:15Z",
                },
                {
                    "service": "crypto-signer",
                    "level": "WARN",
                    "message": "Container crypto-signer terminated with exit code 137 (SIGKILL by oom-killer)",
                    "timestamp": "2026-10-20T18:29:00Z",
                },
            ],
            "deployments": [],
            "dependencies": ["hsm-gateway"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-21",
            "scenario_name": "crypto_signer_native_memory_leak_oom",
            "category": "memory_leak",
            "injected_cause": "Process resident memory leak leading to Linux kernel OOM killer termination",
            "expected_root_cause_keywords": ["memory", "oom", "heap", "leak", "resident"],
            "target_services": ["crypto-signer"],
            "abstain_required": False,
            "repair_appropriate": True,
            "repair_expected_defect": "buffer_free",
        },
    },

    # 22. Partner Identity Provider Token Verification Revocation
    {
        "id": "HELD-OUT-22",
        "file": "holdout_22.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-122",
            "service": "b2b-gateway",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "CRITICAL",
            "metrics": [
                {
                    "metric_name": "http_401_unauthorized_rate_ratio",
                    "service": "b2b-gateway",
                    "value": 0.89,
                    "timestamp": "2026-10-20T19:00:00Z",
                },
                {
                    "metric_name": "idp_validation_error_ratio",
                    "service": "b2b-gateway",
                    "value": 0.92,
                    "timestamp": "2026-10-20T19:00:00Z",
                },
            ],
            "logs": [
                {
                    "service": "b2b-gateway",
                    "level": "ERROR",
                    "message": "TokenRevocationError: Bearer token validation failed; Okta JWKS endpoint returned 401 Unauthorized for client credentials",
                    "timestamp": "2026-10-20T18:58:10Z",
                },
                {
                    "service": "b2b-gateway",
                    "level": "WARN",
                    "message": "Failed to refresh JWKS public keyset: authentication handshake rejected by auth.enterprise.okta.com",
                    "timestamp": "2026-10-20T18:59:00Z",
                },
            ],
            "deployments": [],
            "dependencies": ["okta-idp"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-22",
            "scenario_name": "b2b_gateway_okta_token_revocation_mismatch",
            "category": "authentication_failure",
            "injected_cause": "Partner Okta Identity Provider credentials revocation causing systemic Bearer token validation failure",
            "expected_root_cause_keywords": ["auth", "unauthorized", "token", "bearer", "jwks", "jwt", "idp"],
            "target_services": ["b2b-gateway", "okta-idp"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 23. External DNS Resolver Outage -> Downstream Timeout
    {
        "id": "HELD-OUT-23",
        "file": "holdout_23.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-123",
            "service": "shipping-tracker",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "HIGH",
            "metrics": [
                {
                    "metric_name": "dns_resolution_failure_ratio",
                    "service": "shipping-tracker",
                    "value": 0.95,
                    "timestamp": "2026-10-20T19:30:00Z",
                },
                {
                    "metric_name": "downstream_timeout_ratio",
                    "service": "shipping-tracker",
                    "value": 0.88,
                    "timestamp": "2026-10-20T19:30:00Z",
                },
            ],
            "logs": [
                {
                    "service": "shipping-tracker",
                    "level": "ERROR",
                    "message": "UnknownHostException: Could not resolve address 'api.shipping-partner.external' through upstream DNS resolver 10.0.0.2",
                    "timestamp": "2026-10-20T19:28:15Z",
                },
                {
                    "service": "shipping-tracker",
                    "level": "ERROR",
                    "message": "ConnectTimeoutException: 30000ms connecting to downstream tracking webhook target",
                    "timestamp": "2026-10-20T19:29:10Z",
                },
            ],
            "deployments": [],
            "dependencies": ["fedex-api", "ups-api"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-23",
            "scenario_name": "shipping_dns_resolver_failure_downstream_timeout",
            "category": "network_downstream",
            "injected_cause": "Upstream DNS resolver failure blocking domain resolution and triggering cascading downstream timeouts",
            "expected_root_cause_keywords": ["network", "dns", "downstream", "timeout", "external"],
            "target_services": ["shipping-tracker"],
            "abstain_required": False,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },

    # 24. Sub-Threshold Latency Creep (Abstention Test)
    {
        "id": "HELD-OUT-24",
        "file": "holdout_24.yaml",
        "input": {
            "incident_key": "INC-HOLDOUT-124",
            "service": "analytics-collector",
            "lookback_minutes": 60,
            "environment": "production",
            "severity": "LOW",
            "metrics": [
                {
                    "metric_name": "api_request_latency_ms",
                    "service": "analytics-collector",
                    "value": 210.0,
                    "timestamp": "2026-10-20T20:00:00Z",
                },
                {
                    "metric_name": "http_5xx_error_rate_ratio",
                    "service": "analytics-collector",
                    "value": 0.005,
                    "timestamp": "2026-10-20T20:00:00Z",
                },
                {
                    "metric_name": "cpu_utilization_ratio",
                    "service": "analytics-collector",
                    "value": 0.48,
                    "timestamp": "2026-10-20T20:00:00Z",
                },
            ],
            "logs": [
                {
                    "service": "analytics-collector",
                    "level": "INFO",
                    "message": "Processed 45,000 analytics events successfully in 210ms (latency threshold: 1000ms)",
                    "timestamp": "2026-10-20T19:58:30Z",
                }
            ],
            "deployments": [],
            "dependencies": ["kafka"],
        },
        "ground_truth": {
            "scenario_id": "HELD-OUT-24",
            "scenario_name": "analytics_subthreshold_latency_nominal_abstention",
            "category": "nominal_subthreshold_abstention",
            "injected_cause": "Sub-threshold latency creep (210ms vs 1000ms SLA) with 99.5% success; nominal operation; must abstain",
            "expected_root_cause_keywords": ["insufficient", "nominal", "healthy", "inconclusive", "unknown"],
            "target_services": ["analytics-collector"],
            "abstain_required": True,
            "repair_appropriate": False,
            "repair_expected_defect": None,
        },
    },
]

def main():
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    answer_keys = {}

    for item in SCENARIO_DEFINITIONS:
        file_path = SCENARIOS_DIR / item["file"]
        # Write ONLY observational input to scenarios/holdout_XX.yaml
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(item["input"], f, sort_keys=False, default_flow_style=False)
        print(f"Wrote scenario input: {file_path}")

        # Store ground truth separately in answer_keys map
        answer_keys[item["input"]["incident_key"]] = item["ground_truth"]

    # Write isolated answer keys
    keys_path = GROUND_TRUTH_DIR / "answer_keys.json"
    with open(keys_path, "w", encoding="utf-8") as f:
        json.dump(answer_keys, f, indent=2)
    print(f"\nWrote ground truth answer keys: {keys_path} (total: {len(answer_keys)} keys)")

if __name__ == "__main__":
    main()
