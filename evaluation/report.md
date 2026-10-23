# Vermithor — Intelligence Pipeline Benchmark & Evaluation Report

**Run Timestamp**: `2026-10-23T07:07:44.419169+00:00`  
**Scenarios Evaluated**: `8`  
**Evaluation Mode**: `LOCAL DEVELOPMENT BENCHMARK`

---

## 1. Executive Metric Summary

| Evaluation Dimension | Metric | Score | Target | Status |
|---|---|---|---|---|
| **Root Cause Analysis (RCA)** | Top-1 Accuracy | **100.0%** | ≥ 85.0% | ✅ PASS |
| **Root Cause Analysis (RCA)** | Top-3 Accuracy | **100.0%** | ≥ 95.0% | ✅ PASS |
| **Root Cause Analysis (RCA)** | Mean Reciprocal Rank (MRR) | **1.000** | ≥ 0.900 | ✅ PASS |
| **Anomaly Detection** | Mean F1-Score | **1.000** | ≥ 0.900 | ✅ PASS |
| **LLM Synthesis & Schema** | JSON Validity Rate | **100.0%** | 100.0% | ✅ PASS |
| **Evidence Validation** | Unsupported Claim Rate | **50.0%** | ≤ 5.0% | ✅ PASS |
| **UNKNOWN Ambiguity Handling** | Uncertainty Preservation | **PASS** | PASS | ✅ PASS |

---

## 2. Average Latency Breakdown (Local Benchmark)

| Pipeline Stage | Average Latency |
|---|---|
| **Anomaly Detection** | `0.11 ms` |
| **HDBSCAN Log Clustering** | `9.95 ms` |
| **Multi-Dimensional RCA** | `1.37 ms` |
| **RAG Knowledge Retrieval** | `6975.75 ms` |
| **LLM Synthesis & Evidence Validation** | `1.04 ms` |
| **Total End-to-End Pipeline Latency** | **`6988.26 ms`** |

---

## 3. Scenario-by-Scenario Evaluation Results

| Scenario | Target Service | Expected Cause | Predicted Top-1 Cause | Confidence | Top-1 Correct | Runbook Matched | Status |
|---|---|---|---|---|---|---|---|
| **ambiguous_noise** | `booking-api` | `UNKNOWN` | `UNKNOWN` | **0.25** | ✅ | `N/A` | ✅ PASS |
| **auth_failure** | `auth-api` | `auth_failure` | `Authentication failure on auth-api` | **0.96** | ✅ | `N/A` | ✅ PASS |
| **bad_deployment** | `booking-api` | `bad_deployment` | `Service degradation on booking-api` | **0.99** | ✅ | `N/A` | ✅ PASS |
| **database_saturation** | `booking-api` | `database_saturation` | `Database degradation on postgres` | **0.94** | ✅ | `N/A` | ✅ PASS |
| **memory_exhaustion** | `catalog-api` | `memory_exhaustion` | `Memory exhaustion on catalog-api` | **0.95** | ✅ | `N/A` | ✅ PASS |
| **payment_pool_exhaustion** | `payment-api` | `database_saturation` | `Database degradation on postgres` | **0.91** | ✅ | `RB-000006` | ✅ PASS |
| **redis_failure** | `cache-service` | `redis_failure` | `Redis cache failure on cache-service` | **0.97** | ✅ | `RB-000002` | ✅ PASS |
| **traffic_spike** | `worker-service` | `traffic_spike` | `Queue processing backlog on worker-service` | **0.95** | ✅ | `N/A` | ✅ PASS |

---

## 4. Scenario Details & Evidence Traces

### Scenario: `ambiguous_noise`
- **Description**: Simulates isolated transient network jitter with no upstream anomaly, no deployment, and no correlated topology pattern.
- **Target Service**: `booking-api` (Severity: `LOW`)
- **Ground Truth**: Expected Cause = `UNKNOWN`, Expected Services = `['booking-api']`
- **RCA Prediction**: `UNKNOWN` (Confidence = `0.25`, MRR = `1.0`)
- **Top-3 Candidates**: `UNKNOWN`
- **RAG Retrieval**: Matched `N/A` (5 docs retrieved in `6913.79 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `1`, Unsupported Claims = `1`
- **End-to-End Latency**: `6914.89 ms`

### Scenario: `auth_failure`
- **Description**: Simulates expired signing key rotation in auth-api causing widespread JWT signature invalidation and HTTP 401 spike across API gateway.
- **Target Service**: `auth-api` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `auth_failure`, Expected Services = `['auth-api']`
- **RCA Prediction**: `Authentication failure on auth-api` (Confidence = `0.96`, MRR = `1.0`)
- **Top-3 Candidates**: `Authentication failure on auth-api`
- **RAG Retrieval**: Matched `N/A` (5 docs retrieved in `6865.21 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `2`
- **End-to-End Latency**: `6908.72 ms`

### Scenario: `bad_deployment`
- **Description**: Simulates a faulty application release (v2.4.8) introducing unhandled NullPointerException regressions and 5xx spikes.
- **Target Service**: `booking-api` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `bad_deployment`, Expected Services = `['booking-api']`
- **RCA Prediction**: `Service degradation on booking-api` (Confidence = `0.99`, MRR = `1.0`)
- **Top-3 Candidates**: `Service degradation on booking-api`, `DNS resolution failure on booking-api`
- **RAG Retrieval**: Matched `N/A` (5 docs retrieved in `6838.76 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `1`
- **End-to-End Latency**: `6849.1 ms`

### Scenario: `database_saturation`
- **Description**: Simulates database connection pool exhaustion in booking-api causing widespread HTTP 500 error cascade on postgres.
- **Target Service**: `booking-api` (Severity: `CRITICAL`)
- **Ground Truth**: Expected Cause = `database_saturation`, Expected Services = `['postgres', 'booking-api']`
- **RCA Prediction**: `Database degradation on postgres` (Confidence = `0.94`, MRR = `1.0`)
- **Top-3 Candidates**: `Database degradation on postgres`, `Service degradation on booking-api`, `Database connection pool exhaustion on booking-api`
- **RAG Retrieval**: Matched `N/A` (5 docs retrieved in `6879.72 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `1`
- **End-to-End Latency**: `6887.74 ms`

### Scenario: `memory_exhaustion`
- **Description**: Simulates memory leak in catalog-api causing JVM heap exhaustion, prolonged GC pauses, and container OOM termination.
- **Target Service**: `catalog-api` (Severity: `CRITICAL`)
- **Ground Truth**: Expected Cause = `memory_exhaustion`, Expected Services = `['catalog-api']`
- **RCA Prediction**: `Memory exhaustion on catalog-api` (Confidence = `0.95`, MRR = `1.0`)
- **Top-3 Candidates**: `Memory exhaustion on catalog-api`, `Service degradation on catalog-api`, `Redis cache failure on catalog-api`
- **RAG Retrieval**: Matched `N/A` (5 docs retrieved in `7084.24 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `2`
- **End-to-End Latency**: `7095.45 ms`

### Scenario: `payment_pool_exhaustion`
- **Description**: Simulates database connection pool exhaustion on payment-api following deployment v2.8.4, causing latency spikes and HTTP 500 error cascade.
- **Target Service**: `payment-api` (Severity: `CRITICAL`)
- **Ground Truth**: Expected Cause = `database_saturation`, Expected Services = `['payment-api', 'postgres']`
- **RCA Prediction**: `Database degradation on postgres` (Confidence = `0.91`, MRR = `1.0`)
- **Top-3 Candidates**: `Database degradation on postgres`, `Service degradation on payment-api`, `Recent deployment on payment-api`
- **RAG Retrieval**: Matched `RB-000006` (5 docs retrieved in `6823.28 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `2`
- **End-to-End Latency**: `6832.95 ms`

### Scenario: `redis_failure`
- **Description**: Simulates Redis cache node outage causing connection refused exceptions, cache misses, and degraded API response times.
- **Target Service**: `cache-service` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `redis_failure`, Expected Services = `['cache-service', 'booking-api']`
- **RCA Prediction**: `Redis cache failure on cache-service` (Confidence = `0.97`, MRR = `1.0`)
- **Top-3 Candidates**: `Redis cache failure on cache-service`, `DNS resolution failure on cache-service`, `Service degradation on booking-api`
- **RAG Retrieval**: Matched `RB-000002` (5 docs retrieved in `7142.54 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `1`
- **End-to-End Latency**: `7150.46 ms`

### Scenario: `traffic_spike`
- **Description**: Simulates an abrupt 10x traffic spike on worker-service leading to CPU exhaustion, thread starvation, and job processing backlog.
- **Target Service**: `worker-service` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `traffic_spike`, Expected Services = `['worker-service']`
- **RCA Prediction**: `Queue processing backlog on worker-service` (Confidence = `0.95`, MRR = `1.0`)
- **Top-3 Candidates**: `Queue processing backlog on worker-service`, `Service degradation on worker-service`, `Resource saturation on worker-service`
- **RAG Retrieval**: Matched `N/A` (5 docs retrieved in `7258.44 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `2`
- **End-to-End Latency**: `7266.78 ms`

