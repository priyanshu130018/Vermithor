# Vermithor Deployment-Level Rate Limiting Verification Report

**Verification Date:** October 20, 2026  
**Auditor:** Senior SRE & Application Security Engineering  
**Target Systems:** Docker Compose Stack (`vermithor-gateway`, `vermithor-backend`, `vermithor-redis`, `vermithor-worker`)  
**Implementation:** `backend/app/common/rate_limiter.py`  
**Test Suite:** `backend/tests/common/test_distributed_rate_limiter_audit.py` (9/9 Passed)  

---

## 1. Deployment Topology & Configuration Audit

We inspected the production-equivalent deployment artifacts in `docker-compose.yml`, `gateway/nginx.conf`, and `backend/Dockerfile`:

### Topology Breakdown
- **Edge Reverse Proxy (`gateway`):**  
  NGINX 1.25 Alpine reverse proxying public port `8080` to internal backend `backend:8000`. Configures `proxy_set_header X-Real-IP $remote_addr;` and `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`.
- **Backend Application (`backend`):**  
  FastAPI Modular Monolith running Uvicorn (`uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`). Default process count is 1 per container; scaled in multi-worker or Kubernetes pod topologies via `RATE_LIMIT_WORKER_PROCESS_COUNT` or `WEB_CONCURRENCY`.
- **Distributed Coordination Store (`redis`):**  
  Redis 7-alpine with Append-Only File persistence (`command: ["redis-server", "--appendonly", "yes"]`) exposed on internal network `vermithor-network` and bound locally to `127.0.0.1:6379`.
- **Background Worker (`worker`):**  
  Celery 5 worker with `--concurrency=2` attached to `redis://redis:6379/0`.

---

## 2. Global Consistency vs. Degraded Local Limits

A fundamental requirement of this audit is to **never describe partitioned in-memory counters as a globally coordinated rate limiter**. The distinction between normal operations and degraded failure states is mathematically defined below:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               OPERATIONAL STATE MATRIX                                 │
├─────────────────────────┬──────────────────────────────┬───────────────────────────────┤
│ Dimension               │ Redis Available (Normal)     │ Redis Outage (Degraded)       │
├─────────────────────────┼──────────────────────────────┼───────────────────────────────┤
│ Coordination Mechanism  │ Distributed Redis ZSET / Lua │ Local In-Memory Timestamps    │
│ Cluster-Wide Bound      │ Globally Exact ($L$)         │ Operationally Bounded ($L$)   │
│ Cross-Process Awareness │ 100% Shared State            │ 0% Shared State (Isolated)    │
│ Uneven Traffic Handling │ Perfectly Elastic Across Pods│ Can Throttle Hot Workers Early│
│ High-Cost Endpoints     │ Normal Sliding-Window Check  │ Fail-Closed (HTTP 503)        │
│ Process Crash/Restart   │ Counter Persists Out-of-Proc │ Counter Resets on That Process│
└─────────────────────────┴──────────────────────────────┴───────────────────────────────┘
```

### 1. Globally Consistent Limits (Redis Healthy)
When Redis is operational, all ingress requests across all Uvicorn processes and container replicas execute atomic sliding-window checks via an internal Lua script:
$$\text{Current Requests} = \text{ZCARD}(\text{key})$$
The quota limit $L$ is globally coordinated across the entire fleet. Regardless of how NGINX or Kubernetes load-balances requests across worker processes, a client cannot exceed $L$ requests per window $T$.

### 2. Degraded Per-Process Limits (Redis Outage)
When Redis experiences a network partition, timeout, or crash, each worker process falls back to `InMemorySlidingWindowLimiter`.
- **Without Partitioning (Vulnerable):** If each worker enforces $L$, $W$ workers permit up to $W \times L$ requests ($N$-fold quota multiplication).
- **With Vermithor Bounding (`RATE_LIMIT_DEGRADED_QUOTA_BOUNDED = True`):**  
  Each worker process automatically scales its local quota down to:
  $$\text{Worker Quota} = \max\left(1, \left\lfloor \frac{L}{W} \right\rfloor\right)$$
  Where $W$ is configured via `RATE_LIMIT_WORKER_PROCESS_COUNT`.

> [!WARNING]
> **Operational Trade-Off of Partitioned Degradation:**  
> Partitioned in-memory limits are **not globally coordinated**. If inbound requests are distributed unevenly (e.g. sticky sessions or hot IP hashing sending all traffic to Worker 0), Worker 0 will reject requests once it reaches $L / W$, even if Workers 1..$W-1$ have 100% of their quota unused. This behavior is intentional: **it prioritizes system survival and downstream stability over cluster-wide quota fairness during an infrastructure outage**.

---

## 3. Empirical Test Results & Verification

All 9 deployment-level failure and isolation scenarios were independently executed and passed in `backend/tests/common/test_distributed_rate_limiter_audit.py`:

| Test Identifier | Tested Condition | Expected Behavior | Observed Result | Status |
| :--- | :--- | :--- | :--- | :---: |
| `test_multi_tenant_quota_isolation` | Tenant A and Tenant B burst requests | Tenant A exhaustion has 0 impact on Tenant B | Tenant B retains full quota ($2/2$); Tenant A throttled with 429 | **PASS** |
| `test_anti_spoofing_unauthenticated_ip`| Attacker spoofs `X-Forwarded-For` | Gateway ignores header unless `TRUST_FORWARDED_HEADERS=True` | Socket IP `192.168.1.50` throttled; spoofed headers ignored | **PASS** |
| `test_concurrent_requests_at_limit_boundary` | 4 consecutive rapid requests on limit 3 | Requests 1-3 return 200; request 4 returns 429 | Correct `Retry-After` header returned; boundary enforced | **PASS** |
| `test_multi_worker_quota_partitioning_on_redis_outage`| 4 workers under Redis outage with limit 12 | Total allowed across all 4 workers cannot exceed 12 | Exactly 12 requests allowed ($4 \times 3$); zero $N$-fold inflation | **PASS** |
| `test_fail_closed_policy_on_redis_outage` | High-cost code repair request during Redis outage | Rejects request with HTTP 503 instead of degraded mode | Throws 503 Service Unavailable ("fail-closed policy") | **PASS** |
| `test_redis_recovery_after_outage` | Redis transitions from offline to online | Rate limiter reconnects and resumes distributed ZSET tracking | Seamlessly transitions back to Redis without service restart | **PASS** |
| `test_uneven_request_distribution_under_redis_outage` | All traffic routed to Worker 0 under Redis outage | Worker 0 caps at local limit ($3$); blocks subsequent calls | Worker 0 blocks at 3; workers 1-3 have 0 calls consumed | **PASS** |
| `test_process_restart_resets_in_memory_counter` | Worker process restarts during Redis outage | In-memory counter resets on new process | New process initializes fresh empty window queue | **PASS** |
| `test_idempotent_retries_and_forced_refresh_consume_quota` | Client repeatedly retries requests with identical payload | Inbound retries consume rate-limit tokens | Token count decrements on each call; 3rd retry rejected with 429 | **PASS** |

---

## 4. High-Cost Operation Boundaries: Fail-Closed Protection

A key principle validated during this audit is that **expensive, mutation-capable, or compute-heavy endpoints must never operate in degraded uncoordinated mode**:

1. **AI Code Repair Workflow (`POST /agent/repairs`):**  
   - Spawns isolated Docker containers and executes repository test suites.
   - Configured with `fail_closed_on_redis_outage=True`.
   - If Redis is unavailable, requests are **immediately aborted with HTTP 503 Service Unavailable**.
   - No container execution or CPU spikes can be triggered without verified global rate limiting.
2. **Incident Telemetry Ingestion (`POST /agent/investigations`):**  
   - Read-heavy and operational.
   - Operates under bounded degraded mode (`fail_closed_on_redis_outage=False`) so engineers can continue triaging active incidents even if Redis is restarting.

---

## 5. Security & SRE Recommendations for Multi-Host Scaling

1. **Kubernetes Multi-Replica Deployments:**  
   When scaling the backend across $K$ pods each with $N$ workers ($W = K \times N$), set `RATE_LIMIT_WORKER_PROCESS_COUNT` to $W$ in the Helm/Kustomize environment configuration, or deploy Redis Sentinel / Cluster for high availability so degraded fallback is rarely engaged.
2. **Reverse Proxy Header Trust:**  
   Keep `TRUST_FORWARDED_HEADERS = False` by default. Only set to `True` when Vermithor is deployed behind a secured, trusted proxy tier (e.g. AWS ALB or Cloudflare) that strips untrusted ingress `X-Forwarded-For` headers.
3. **Monitoring Alerting Thresholds:**  
   Set Prometheus alerts for rate-limiting log signatures:
   - Alert: `RateLimiterRedisFallbackEngaged` (Warning: Redis rate limit check failed; engaging in-memory fallback).
   - Alert: `RateLimiterFailClosedTriggered` (Critical: High-cost operation rejected under fail-closed security policy).
