# Pilot Replay Fixtures & Ground-Truth Manifest

**Directory:** `evaluation/benchmarks/pilot_replay_fixtures/`  
**Dataset Version:** `1.0.0`  
**Evaluation Scope:** Supervised Read-Only Pilot Rehearsal & Evidence-Based Verification  
**Ground-Truth Isolation:** Answer keys physically separated in `ground_truth/answer_keys.json`

---

## 1. Provenance & Dataset Classification

These 10 cases represent **sanitized historical postmortem replay fixtures** modeled on common production failure patterns observed in distributed microservice architectures.

> [!WARNING]
> **Provenance Disclosure:**
> These scenarios are **NOT live customer production incidents** and are **NOT third-party audited external postmortems**.
> They are repository-hosted synthetic and sanitized replay scenarios constructed to simulate real-world failure patterns (HikariCP pool starvation, IdP cert expiry, Redis maxmemory, CoreDNS UDP drop, Ext4 inode depletion, cgroup OOM, Kafka poison pill, Postgres deadlock, backup window nominal telemetry, and transit network jitter).
> Live customer VPC telemetry remains **NOT VERIFIED**.

---

## 2. Fixture Catalog

| Case ID | Incident Key | Service | Failure Mode / Postmortem Reference | Ingested Signals | Abstain Required |
|---|---|---|---|---|---|
| `PILOT-CASE-01` | `INC-PILOT-201` | `payment-core` | HikariCP connection pool acquisition timeout under thread starvation (`PM-2026-084`) | Pool utilization=1.0, active=80/80, SQLTransientConnectionException | No |
| `PILOT-CASE-02` | `INC-PILOT-202` | `identity-auth` | Okta IdP signing certificate expiration (`PM-2026-091`) | Auth failure ratio=0.88, CertificateExpiredException | No |
| `PILOT-CASE-03` | `INC-PILOT-203` | `catalog-cache` | Redis maxmemory reached under unevicted session tokens (`PM-2026-103`) | Memory used=1.0, eviction rate=1520/s, RedisOOMException | No |
| `PILOT-CASE-04` | `INC-PILOT-204` | `checkout-api` | CoreDNS UDP timeout causing client checkout connection stall (`PM-2026-112`) | Timeout ratio=0.40, CoreDNS upstream UDP timeout | No |
| `PILOT-CASE-05` | `INC-PILOT-205` | `doc-renderer` | Ext4 filesystem inode exhaustion from uncleaned temp files (`PM-2026-119`) | Inode usage=1.0, IOException: No space left on device | No |
| `PILOT-CASE-06` | `INC-PILOT-206` | `ingest-worker` | Native C memory leak causing cgroup OOM killer invocation (`PM-2026-125`) | Container working set=4GB/4GB, Killed process (OOM SIGKILL 137) | No |
| `PILOT-CASE-07` | `INC-PILOT-207` | `inventory-sync` | Scheduled database backup maintenance window nominal telemetry (`PM-2026-130`) | Nominal latency, zero critical errors, maintenance notices | **Yes (Abstain)** |
| `PILOT-CASE-08` | `INC-PILOT-208` | `fulfillment-stream` | Malformed JSON poison pill causing Kafka consumer group stall (`PM-2026-141`) | Kafka consumer lag=48k, DeserializationException | No |
| `PILOT-CASE-09` | `INC-PILOT-209` | `subscription-billing` | PostgreSQL row-level deadlocks during concurrent renewal billing (`PM-2026-149`) | Deadlocks count=24, DeadlockDetected tuple lock | No |
| `PILOT-CASE-10` | `INC-PILOT-210` | `search-federator` | Transient cloud transit jitter resolving automatically (`PM-2026-155`) | Packet loss=0.002 (within SLA), nominal query latency | **Yes (Abstain)** |

---

## 3. Ground-Truth Separation Guarantee

1. Scenario YAMLs (`scenarios/*.yaml`) contain **only** telemetry that an SRE or monitoring agent would observe:
   - Target service and incident key
   - Metric series and observations
   - Log entries with log levels, timestamps, and messages
   - Deployment events and dependency topology
2. **Ground-Truth Labels** (`ground_truth/answer_keys.json`) contain:
   - Expected root cause keywords
   - Correct abstention requirements
   - Injected cause narrative
3. The evaluation harness never passes `ground_truth/` data to the agent graph. Scoring occurs strictly after the investigation completes.
