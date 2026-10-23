# Vermithor Rate Limiting & Distributed Failure Audit

**Audit Date:** October 20, 2026  
**Component:** `backend/app/common/rate_limiter.py` & Ingress Security Middleware  
**Auditor:** Application Security & Distributed Systems SRE Team  
**Verification Test Suite:** `backend/tests/common/test_distributed_rate_limiter_audit.py` (6/6 Passing)  

---

## 1. Executive Summary

As part of the SaaS readiness verification for Vermithor's pilot deployment, this audit investigates the failure modes of the sliding-window rate limiter under **multi-worker**, **multi-tenant**, and **infrastructure outage** conditions.

Specifically, standard in-memory fallback mechanisms in distributed web frameworks often suffer from a silent **$N$-fold quota multiplication** vulnerability when the central coordination store (Redis) fails. Furthermore, naive client IP extraction can expose public endpoints to **IP spoofing attacks** via forged headers.

This audit details the mathematical mechanisms, security risks, implemented mitigations, and empirical verification test results for Vermithor's ingress rate-limiting architecture.

---

## 2. Distributed Sliding-Window Architecture

Vermithor implements a multi-tier sliding-window rate limiter supporting both distributed Redis coordination and localized per-worker in-memory tracking:

```
                            [ Ingress Request ]
                                    │
                                    ▼
                     [ Client Identity Resolution ]
                     ├─ Authenticated: org_id + user_id
                     └─ Unauthenticated: Direct Socket IP (Anti-Spoofing)
                                    │
                                    ▼
                         [ Redis Central Store ]
                                    │
                  ┌─────────────────┴─────────────────┐
           [ Available ]                       [ Unavailable ]
                  │                                   │
                  ▼                                   ▼
      [ Global Sliding Window ]             [ Policy Decision ]
      (Lua script atomicity)                          │
                                    ┌─────────────────┴─────────────────┐
                             [ Fail-Closed ]                     [ Degraded-Bounded ]
                             (HTTP 503 Error)                    (Partitioned Quota)
```

### Key Composition
Each rate limit window is partitioned into a distinct namespace:
$$\text{Key} = \texttt{"rl:"} + \text{scope} + \texttt{":org:"} + \text{org\_id} + \texttt{":"} + \text{user\_id}$$
For unauthenticated requests:
$$\text{Key} = \texttt{"rl:"} + \text{scope} + \texttt{":ip:"} + \text{client\_ip}$$

This ensures that tenant quotas are mathematically isolated—traffic spikes from Tenant A cannot exhaust or throttle Tenant B.

---

## 3. The Multi-Worker Quota Multiplication Vulnerability

### Mathematical Problem Statement
In a production deployment, Uvicorn runs with $N$ worker processes (or $K$ Kubernetes pods each running $N$ workers, totaling $W = K \times N$ worker processes).

Under normal operations, all $W$ workers coordinate through Redis using a shared sliding window:
$$\text{Cluster Rate Limit} = L \text{ requests per window } T$$

When Redis suffers an outage, network partition, or connection timeout, typical rate limiters degrade to a local in-memory fallback (e.g., Python `collections.deque` or timestamp arrays). If each worker independently enforces the limit $L$:
$$\text{Effective Degraded Cluster Capacity} = W \times L$$

For example, with a configured limit of $L = 15 \text{ requests/min}$ and $W = 4 \text{ workers}$:
$$\text{Aggregate Allowed Throughput} = 4 \times 15 = 60 \text{ requests/min}$$

During a database or backend outage (which often triggers the Redis outage), inbound traffic can surge to **400% of the intended rate limit**, overwhelming recovering downstream systems.

### Hardened Mitigation: Partitioned In-Memory Quotas
Vermithor introduces bounded degraded mode (`RATE_LIMIT_DEGRADED_QUOTA_BOUNDED = True`):

$$\text{Effective Local Limit} = \max\left(1, \left\lfloor \frac{L}{W} \right\rfloor\right)$$

Where $W$ is configured via `RATE_LIMIT_WORKER_PROCESS_COUNT` (or detected via process topology).

```python
# Implementation excerpt from backend/app/common/rate_limiter.py
if settings.RATE_LIMIT_DEGRADED_QUOTA_BOUNDED and settings.RATE_LIMIT_WORKER_PROCESS_COUNT > 1:
    limit = max(1, limit // settings.RATE_LIMIT_WORKER_PROCESS_COUNT)
```

### Empirical Verification
In `test_multi_worker_quota_partitioning_on_redis_outage`:
- Configured Limit $L = 8$ calls/min, $W = 4$ workers.
- When Redis connection fails, the per-worker quota immediately adjusts to $8 // 4 = 2$ calls/min.
- The 1st and 2nd requests within the window succeed.
- The 3rd request is rejected with `HTTP 429 Too Many Requests`.
- Result: Aggregate cluster capacity across all 4 workers cannot exceed $4 \times 2 = 8$ calls/min.

---

## 4. Fail-Closed vs. Bounded Degraded Policies

Not all endpoints should allow degraded operations during infrastructure outages. High-cost, resource-intensive, or security-sensitive actions should **fail closed** rather than permit uncoordinated degraded traffic.

### Policy Matrix

| Endpoint Category | Example Endpoints | Policy on Redis Outage | Response Code | Rationale |
| :--- | :--- | :---: | :---: | :--- |
| **Telemetry Ingestion & Triage** | `GET /agent/investigations`, `POST /agent/investigations` | **Bounded Degraded** | HTTP 200 (or 429 when local limit exceeded) | Critical operational visibility must persist during an active incident. |
| **High-Cost Agent Actions** | `POST /agent/repairs` (Code Repair & Test Sandbox) | **Fail-Closed** | **HTTP 503 Service Unavailable** | Spinning up Docker sandboxes and running test suites during an outage can crash the host. |
| **Security & Auth Endpoints** | Token refresh, User credential validation | **Fail-Closed** | **HTTP 503 Service Unavailable** | Prevents distributed brute-force attacks during caching layer downtime. |

### Implementation & Verification
When `fail_closed_on_redis_outage=True` is set on the limiter:
```python
if self.fail_closed_on_redis_outage:
    logger.error("Rate limiter backend unavailable; rejecting request under fail-closed security policy")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Rate limiter backend unavailable; request rejected under fail-closed policy",
    )
```
Verified in `test_fail_closed_policy_on_redis_outage`:
- When Redis is offline, requests to fail-closed routes receive HTTP 503 with explicit error semantics, preventing downstream cascading failure.

---

## 5. Anti-Spoofing & Client IP Resolution

### The Vulnerability
Public-facing endpoints rate-limit unauthenticated clients by IP address. Naive implementations read `request.headers.get("X-Forwarded-For")`. An attacker can bypass IP rate limits simply by rotating fake header values:
```bash
curl -H "X-Forwarded-For: 1.2.3.4" https://api.vermithor.io/health
curl -H "X-Forwarded-For: 1.2.3.5" https://api.vermithor.io/health
```

### Hardening Specification
Vermithor enforces strict anti-spoofing controls:
1. `TRUST_FORWARDED_HEADERS = False` by default.
2. When untrusted, the limiter ignores `X-Forwarded-For` and `X-Real-IP`, binding strictly to `request.client.host` (the direct TCP socket peer).
3. If deployed behind a verified reverse proxy (e.g., Cloudflare, AWS ALB, NGINX), operators must explicitly set `TRUST_FORWARDED_HEADERS = True`. When enabled, only the leftmost client IP from the reverse proxy is resolved.

### Empirical Verification
In `test_anti_spoofing_unauthenticated_ip`:
- An attacker sends 3 consecutive requests from socket IP `198.51.100.25`, spoofing `X-Forwarded-For: 203.0.113.1`, `203.0.113.2`, etc.
- With `TRUST_FORWARDED_HEADERS = False`, the limiter correctly attributes all requests to `198.51.100.25`.
- Requests 1 and 2 succeed; the 3rd request is blocked with HTTP 429. The spoofing attempt is completely neutralized.

---

## 6. Resilience & State Recovery

### Redis Outage and Dynamic Reconnection
Rate limiters must not require application restarts when the central cache recovers from a transient outage.

Verified in `test_redis_recovery_after_outage`:
1. Requests executed while Redis is unreachable fall back to bounded in-memory sliding windows.
2. When Redis connectivity is restored, the rate limiter seamlessly resumes querying Redis on the subsequent request without dropping active connections or throwing uncaught exceptions.
3. Centralized cluster-wide sliding windows immediately resume enforcement.

---

## 7. Audit Conclusion & Compliance Summary

| Requirement | Audit Status | Evidence |
| :--- | :---: | :--- |
| **Multi-Tenant Quota Isolation** | **VERIFIED** | Scoped keys (`rl:{scope}:org:{org_id}`) ensure 0 cross-tenant interference. |
| **Degraded Quota Partitioning** | **VERIFIED** | Per-process in-memory limits prevent $N$-worker throughput inflation. |
| **Fail-Closed Boundary Enforcement**| **VERIFIED** | High-cost repair endpoints fail closed with HTTP 503 during Redis outages. |
| **Anti-Spoofing IP Protection** | **VERIFIED** | Socket-level IP resolution prevents header-based rate limit evasion. |
| **Automatic Cache Reconnection** | **VERIFIED** | Zero-downtime recovery when Redis transitions from down to healthy. |

**Readiness Determination:** The ingress rate limiting architecture meets production SaaS requirements for multi-tenant isolation, resilience, and security boundary protection.
