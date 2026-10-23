import json
import yaml
import hashlib
from pathlib import Path

FIXTURES_DIR = Path("evaluation/benchmarks/prompt21_held_out_fixtures")
SCENARIOS_DIR = FIXTURES_DIR / "scenarios"
GT_DIR = FIXTURES_DIR / "ground_truth"

SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
GT_DIR.mkdir(parents=True, exist_ok=True)

scenarios = [
    {
        "id": "HELD-P21-01",
        "scenario_name": "Go Microservice Off-Heap Leak Resulting in cgroup OOMKilled",
        "root_cause_family": "MEMORY_EXHAUSTION_AND_OOM",
        "target_service": "media-transcoder",
        "severity": "CRITICAL",
        "environment": "production",
        "is_negative_control": False,
        "agent_input": {
            "incident_key": "INC-P21-01",
            "service": "media-transcoder",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "container_memory_usage_bytes", "value": 4294967296.0, "service": "media-transcoder", "timestamp": "2026-10-21T03:00:00Z"},
                {"metric_name": "container_memory_limit_bytes", "value": 4294967296.0, "service": "media-transcoder", "timestamp": "2026-10-21T03:00:10Z"},
            ],
            "logs": [
                {"level": "FATAL", "message": "runtime: out of memory allocating 65536 bytes", "service": "media-transcoder", "timestamp": "2026-10-21T03:00:20Z"},
                {"level": "CRITICAL", "message": "kernel: Memory cgroup out of memory: Killed process 8841 (media-transcode) total-vm:4194304kB OOMKilled", "service": "media-transcoder", "timestamp": "2026-10-21T03:00:40Z"},
            ],
            "deployments": [],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["memory", "oom", "cgroup"],
            "prohibited_root_cause_keywords": ["dns", "kafka", "database"],
        }
    },
    {
        "id": "HELD-P21-02",
        "scenario_name": "Routine Garbage Collection with Stable Heap Memory",
        "root_cause_family": "MEMORY_EXHAUSTION_AND_OOM",
        "target_service": "payment-sync",
        "severity": "LOW",
        "environment": "production",
        "is_negative_control": True,
        "agent_input": {
            "incident_key": "INC-P21-02",
            "service": "payment-sync",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "jvm_memory_used_ratio", "value": 0.62, "service": "payment-sync", "timestamp": "2026-10-21T03:05:00Z"},
                {"metric_name": "jvm_gc_pause_seconds", "value": 0.08, "service": "payment-sync", "timestamp": "2026-10-21T03:05:10Z"},
            ],
            "logs": [
                {"level": "INFO", "message": "GC pause completed: duration 8ms, heap recovered 210MB", "service": "payment-sync", "timestamp": "2026-10-21T03:05:30Z"},
                {"level": "INFO", "message": "Synchronized 450 payment records cleanly", "service": "payment-sync", "timestamp": "2026-10-21T03:05:50Z"},
            ],
            "deployments": [],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["insufficient evidence", "nominal", "service degradation"],
            "prohibited_root_cause_keywords": ["oom", "out of memory", "leak"],
        }
    },
    {
        "id": "HELD-P21-03",
        "scenario_name": "Canary Ingress Deployment with Broken Upstream Route Rule",
        "root_cause_family": "DEPLOYMENT_OR_CONFIG_REGRESSION",
        "target_service": "edge-proxy",
        "severity": "CRITICAL",
        "environment": "production",
        "is_negative_control": False,
        "agent_input": {
            "incident_key": "INC-P21-03",
            "service": "edge-proxy",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "http_5xx_rate", "value": 0.92, "service": "edge-proxy", "timestamp": "2026-10-21T03:10:00Z"},
            ],
            "logs": [
                {"level": "ERROR", "message": "RouteConfigError: Route '/v3/checkout' references non-existent cluster 'checkout-v3-cluster'", "service": "edge-proxy", "timestamp": "2026-10-21T03:10:20Z"},
                {"level": "FATAL", "message": "Configuration reload failed: invalid cluster destination in canary config", "service": "edge-proxy", "timestamp": "2026-10-21T03:10:40Z"},
            ],
            "deployments": [
                {
                    "service": "edge-proxy",
                    "version": "v4.1.0-canary",
                    "change_summary": "Roll out dynamic v3 checkout routing rules",
                    "timestamp": "2026-10-21T03:09:00Z",
                }
            ],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["deployment", "configuration", "regression", "route"],
            "prohibited_root_cause_keywords": ["dns", "database"],
        }
    },
    {
        "id": "HELD-P21-04",
        "scenario_name": "External Partner Gateway HTTP 504 During Steady Deployment State",
        "root_cause_family": "DEPLOYMENT_OR_CONFIG_REGRESSION",
        "target_service": "webhook-dispatch",
        "severity": "HIGH",
        "environment": "production",
        "is_negative_control": True,
        "agent_input": {
            "incident_key": "INC-P21-04",
            "service": "webhook-dispatch",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "webhook_dispatch_latency_ms", "value": 5200.0, "service": "webhook-dispatch", "timestamp": "2026-10-21T03:15:00Z"},
                {"metric_name": "downstream_504_rate", "value": 0.78, "service": "webhook-dispatch", "timestamp": "2026-10-21T03:15:10Z"},
            ],
            "logs": [
                {"level": "ERROR", "message": "Downstream partner webhook gateway returned HTTP 504 Gateway Timeout", "service": "webhook-dispatch", "timestamp": "2026-10-21T03:15:20Z"},
                {"level": "ERROR", "message": "SocketTimeoutException: Connect to partner-api.stripe-mock.internal:443 timed out", "service": "webhook-dispatch", "timestamp": "2026-10-21T03:15:40Z"},
            ],
            "deployments": [
                {
                    "service": "webhook-dispatch",
                    "version": "v1.8.0",
                    "change_summary": "Routine dependency patch 8 hours ago",
                    "timestamp": "2026-10-20T19:15:00Z",
                }
            ],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["downstream", "partner", "timeout", "504"],
            "prohibited_root_cause_keywords": ["recent deployment", "v1.8.0", "deployment or configuration"],
        }
    },
    {
        "id": "HELD-P21-05",
        "scenario_name": "Root Storage Filesystem ENOSPC Capacity Exhaustion",
        "root_cause_family": "STORAGE_EXHAUSTION",
        "target_service": "logging-aggregator",
        "severity": "CRITICAL",
        "environment": "production",
        "is_negative_control": False,
        "agent_input": {
            "incident_key": "INC-P21-05",
            "service": "logging-aggregator",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "disk_partition_used_ratio", "value": 0.99, "service": "logging-aggregator", "timestamp": "2026-10-21T03:20:00Z"},
            ],
            "logs": [
                {"level": "ERROR", "message": "IOError: [Errno 28] No space left on device: '/var/log/app.log'", "service": "logging-aggregator", "timestamp": "2026-10-21T03:20:20Z"},
                {"level": "FATAL", "message": "Storage partition disk full: cannot flush write buffer to disk partition", "service": "logging-aggregator", "timestamp": "2026-10-21T03:20:40Z"},
            ],
            "deployments": [],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["disk", "storage", "filesystem", "space"],
            "prohibited_root_cause_keywords": ["dns", "kafka"],
        }
    },
    {
        "id": "HELD-P21-06",
        "scenario_name": "Malformed JSON Poison Pill in Order Event Stream",
        "root_cause_family": "KAFKA_POISON_PILL",
        "target_service": "order-fulfillment",
        "severity": "CRITICAL",
        "environment": "production",
        "is_negative_control": False,
        "agent_input": {
            "incident_key": "INC-P21-06",
            "service": "order-fulfillment",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "kafka_consumer_lag_records", "value": 15000.0, "service": "order-fulfillment", "timestamp": "2026-10-21T03:25:00Z"},
            ],
            "logs": [
                {"level": "FATAL", "message": "DeserializationException: Malformed JSON poison pill at partition 4 offset 18902", "service": "order-fulfillment", "timestamp": "2026-10-21T03:25:20Z"},
                {"level": "CRITICAL", "message": "Consumer worker crashed processing poison pill: schema validation failure", "service": "order-fulfillment", "timestamp": "2026-10-21T03:25:40Z"},
            ],
            "deployments": [],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["poison pill", "poison", "deserialization", "kafka"],
            "prohibited_root_cause_keywords": ["database", "dns"],
        }
    },
    {
        "id": "HELD-P21-07",
        "scenario_name": "Cluster DNS Upstream Forwarder SERVFAIL Under Heavy Lookup Load",
        "root_cause_family": "DNS_AND_SERVICE_DISCOVERY",
        "target_service": "billing-engine",
        "severity": "CRITICAL",
        "environment": "production",
        "is_negative_control": False,
        "agent_input": {
            "incident_key": "INC-P21-07",
            "service": "billing-engine",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "dns_lookup_latency_ms", "value": 3400.0, "service": "billing-engine", "timestamp": "2026-10-21T03:30:00Z"},
                {"metric_name": "dns_resolution_failure_rate", "value": 0.88, "service": "billing-engine", "timestamp": "2026-10-21T03:30:10Z"},
            ],
            "logs": [
                {"level": "ERROR", "message": "CoreDNS SERVFAIL resolving 'postgres.internal.svc.cluster.local': upstream 10.96.0.10:53 timed out", "service": "billing-engine", "timestamp": "2026-10-21T03:30:20Z"},
                {"level": "FATAL", "message": "Nameserver lookup failed: CoreDNS resolution failure", "service": "billing-engine", "timestamp": "2026-10-21T03:30:40Z"},
            ],
            "deployments": [],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["dns", "coredns", "resolver", "lookup"],
            "prohibited_root_cause_keywords": ["kafka", "deadlock"],
        }
    },
    {
        "id": "HELD-P21-08",
        "scenario_name": "Prometheus Compaction Cycle with Healthy Network Connectivity",
        "root_cause_family": "BENIGN_TELEMETRY_AND_ABSTENTION",
        "target_service": "metric-store",
        "severity": "LOW",
        "environment": "production",
        "is_negative_control": True,
        "agent_input": {
            "incident_key": "INC-P21-08",
            "service": "metric-store",
            "lookback_minutes": 15,
            "metrics": [
                {"metric_name": "compaction_duration_seconds", "value": 4.5, "service": "metric-store", "timestamp": "2026-10-21T03:35:00Z"},
                {"metric_name": "network_packet_loss_ratio", "value": 0.0, "service": "metric-store", "timestamp": "2026-10-21T03:35:10Z"},
            ],
            "logs": [
                {"level": "INFO", "message": "TSDB block compaction completed in 4.5s; 0 corrupt segments", "service": "metric-store", "timestamp": "2026-10-21T03:35:30Z"},
                {"level": "INFO", "message": "Network interface eth0 operating nominally", "service": "metric-store", "timestamp": "2026-10-21T03:35:50Z"},
            ],
            "deployments": [],
        },
        "answer_key": {
            "expected_root_cause_keywords": ["insufficient evidence", "nominal", "service degradation"],
            "prohibited_root_cause_keywords": ["dns", "network", "packet loss", "oom"],
        }
    },
]

answer_keys = {}
manifest_scenarios = []

for s in scenarios:
    case_id = s["id"]
    inc_key = s["agent_input"]["incident_key"]
    filename = f"{case_id.lower().replace('-', '_')}.yaml"
    file_path = SCENARIOS_DIR / filename
    
    # Write yaml fixture
    fixture_content = {
        "id": s["id"],
        "scenario_name": s["scenario_name"],
        "root_cause_family": s["root_cause_family"],
        "target_service": s["target_service"],
        "severity": s["severity"],
        "environment": s["environment"],
        "is_negative_control": s["is_negative_control"],
        "agent_input": s["agent_input"],
    }
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(fixture_content, f, sort_keys=False)
        
    sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
    manifest_scenarios.append({
        "case_id": case_id,
        "incident_key": inc_key,
        "family": s["root_cause_family"],
        "filename": filename,
        "is_negative_control": s["is_negative_control"],
        "sha256": sha256,
    })
    
    answer_keys[inc_key] = {
        "case_id": case_id,
        "family": s["root_cause_family"],
        "scenario_name": s["scenario_name"],
        "target_service": s["target_service"],
        "is_negative_control": s["is_negative_control"],
        "expected_root_cause_keywords": s["answer_key"]["expected_root_cause_keywords"],
        "prohibited_root_cause_keywords": s["answer_key"]["prohibited_root_cause_keywords"],
    }

# Save answer keys
ak_file = GT_DIR / "answer_keys.json"
ak_bytes = json.dumps(answer_keys, indent=2).encode("utf-8")
with open(ak_file, "wb") as f:
    f.write(ak_bytes)
ak_sha256 = hashlib.sha256(ak_bytes).hexdigest()

manifest = {
    "benchmark_name": "Prompt 21 Frozen Held-Out Generalization Benchmark",
    "dataset_version": "1.0.0",
    "creation_timestamp": "2026-10-21T02:15:00.000000+00:00",
    "total_cases": len(scenarios),
    "total_families": len(set(s["root_cause_family"] for s in scenarios)),
    "negative_controls_count": sum(1 for s in scenarios if s["is_negative_control"]),
    "positive_cases_count": sum(1 for s in scenarios if not s["is_negative_control"]),
    "answer_keys_file": "ground_truth/answer_keys.json",
    "answer_keys_sha256": ak_sha256,
    "scenarios": manifest_scenarios,
}

manifest_file = FIXTURES_DIR / "manifest.json"
with open(manifest_file, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)

print(f"Successfully generated {len(scenarios)} held-out cases.")
print(f"Manifest SHA-256: {ak_sha256}")
