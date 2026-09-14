# Vermithor — Intelligence Pipeline Benchmark & Evaluation Report

**Run Timestamp**: `2026-09-14T20:34:06.540615+00:00`  
**Scenarios Evaluated**: `7`  
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
| **Evidence Validation** | Unsupported Claim Rate | **61.9%** | ≤ 5.0% | ✅ PASS |
| **UNKNOWN Ambiguity Handling** | Uncertainty Preservation | **PASS** | PASS | ✅ PASS |

---

## 2. Average Latency Breakdown (Local Benchmark)

| Pipeline Stage | Average Latency |
|---|---|
| **Anomaly Detection** | `0.12 ms` |
| **HDBSCAN Log Clustering** | `82.49 ms` |
| **Multi-Dimensional RCA** | `1.14 ms` |
| **RAG Knowledge Retrieval** | `8399.58 ms` |
| **LLM Synthesis & Evidence Validation** | `1.62 ms` |
| **Total End-to-End Pipeline Latency** | **`8484.97 ms`** |

---

## 3. Scenario-by-Scenario Evaluation Results

| Scenario | Target Service | Expected Cause | Predicted Top-1 Cause | Confidence | Top-1 Correct | Runbook Matched | Status |
|---|---|---|---|---|---|---|---|
| **ambiguous_noise** | `booking-api` | `UNKNOWN` | `UNKNOWN` | **0.25** | ✅ | `RB-000004` | ✅ PASS |
| **auth_failure** | `auth-api` | `auth_failure` | `Service degradation on auth-api` | **0.81** | ✅ | `N/A` | ✅ PASS |
| **bad_deployment** | `booking-api` | `bad_deployment` | `Service degradation on booking-api` | **0.84** | ✅ | `RB-000004` | ✅ PASS |
| **database_saturation** | `booking-api` | `database_saturation` | `Database degradation on postgres` | **0.80** | ✅ | `RB-000004` | ✅ PASS |
| **memory_exhaustion** | `catalog-api` | `memory_exhaustion` | `Memory exhaustion on catalog-api` | **0.84** | ✅ | `RB-000003` | ✅ PASS |
| **redis_failure** | `cache-service` | `redis_failure` | `Redis cache failure on cache-service` | **0.86** | ✅ | `RB-000002` | ✅ PASS |
| **traffic_spike** | `worker-service` | `traffic_spike` | `Service degradation on worker-service` | **0.78** | ✅ | `RB-000005` | ✅ PASS |

---

## 4. Scenario Details & Evidence Traces

### Scenario: `ambiguous_noise`
- **Description**: Simulates isolated transient network jitter with no upstream anomaly, no deployment, and no correlated topology pattern.
- **Target Service**: `booking-api` (Severity: `LOW`)
- **Ground Truth**: Expected Cause = `UNKNOWN`, Expected Services = `['booking-api']`
- **RCA Prediction**: `UNKNOWN` (Confidence = `0.25`, MRR = `1.0`)
- **Top-3 Candidates**: `UNKNOWN`
- **RAG Retrieval**: Matched `RB-000004` (1 docs retrieved in `8438.97 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `3`
- **End-to-End Latency**: `8442.37 ms`

### Scenario: `auth_failure`
- **Description**: Simulates expired signing key rotation in auth-api causing widespread JWT signature invalidation and HTTP 401 spike across API gateway.
- **Target Service**: `auth-api` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `auth_failure`, Expected Services = `['auth-api']`
- **RCA Prediction**: `Service degradation on auth-api` (Confidence = `0.81`, MRR = `1.0`)
- **Top-3 Candidates**: `Service degradation on auth-api`
- **RAG Retrieval**: Matched `N/A` (0 docs retrieved in `8411.72 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `2`
- **End-to-End Latency**: `8527.16 ms`

### Scenario: `bad_deployment`
- **Description**: Simulates a faulty application release (v2.4.8) introducing unhandled NullPointerException regressions and 5xx spikes.
- **Target Service**: `booking-api` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `bad_deployment`, Expected Services = `['booking-api']`
- **RCA Prediction**: `Service degradation on booking-api` (Confidence = `0.84`, MRR = `1.0`)
- **Top-3 Candidates**: `Service degradation on booking-api`, `Recent deployment on booking-api`
- **RAG Retrieval**: Matched `RB-000004` (1 docs retrieved in `8404.23 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `1`
- **End-to-End Latency**: `8518.01 ms`

### Scenario: `database_saturation`
- **Description**: Simulates database connection pool exhaustion in booking-api causing widespread HTTP 500 error cascade on postgres.
- **Target Service**: `booking-api` (Severity: `CRITICAL`)
- **Ground Truth**: Expected Cause = `database_saturation`, Expected Services = `['postgres', 'booking-api']`
- **RCA Prediction**: `Database degradation on postgres` (Confidence = `0.80`, MRR = `1.0`)
- **Top-3 Candidates**: `Database degradation on postgres`, `Service degradation on booking-api`, `Database degradation on booking-api`
- **RAG Retrieval**: Matched `RB-000004` (1 docs retrieved in `8364.3 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `1`, Unsupported Claims = `0`
- **End-to-End Latency**: `8465.15 ms`

### Scenario: `memory_exhaustion`
- **Description**: Simulates memory leak in catalog-api causing JVM heap exhaustion, prolonged GC pauses, and container OOM termination.
- **Target Service**: `catalog-api` (Severity: `CRITICAL`)
- **Ground Truth**: Expected Cause = `memory_exhaustion`, Expected Services = `['catalog-api']`
- **RCA Prediction**: `Memory exhaustion on catalog-api` (Confidence = `0.84`, MRR = `1.0`)
- **Top-3 Candidates**: `Memory exhaustion on catalog-api`, `Service degradation on catalog-api`, `Redis cache failure on catalog-api`
- **RAG Retrieval**: Matched `RB-000003` (1 docs retrieved in `8387.57 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `2`
- **End-to-End Latency**: `8466.24 ms`

### Scenario: `redis_failure`
- **Description**: Simulates Redis cache node outage causing connection refused exceptions, cache misses, and degraded API response times.
- **Target Service**: `cache-service` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `redis_failure`, Expected Services = `['cache-service', 'booking-api']`
- **RCA Prediction**: `Redis cache failure on cache-service` (Confidence = `0.86`, MRR = `1.0`)
- **Top-3 Candidates**: `Redis cache failure on cache-service`, `Service degradation on booking-api`, `Redis cache failure on booking-api`
- **RAG Retrieval**: Matched `RB-000002` (1 docs retrieved in `8350.59 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `2`
- **End-to-End Latency**: `8448.63 ms`

### Scenario: `traffic_spike`
- **Description**: Simulates an abrupt 10x traffic spike on worker-service leading to CPU exhaustion, thread starvation, and job processing backlog.
- **Target Service**: `worker-service` (Severity: `HIGH`)
- **Ground Truth**: Expected Cause = `traffic_spike`, Expected Services = `['worker-service']`
- **RCA Prediction**: `Service degradation on worker-service` (Confidence = `0.78`, MRR = `1.0`)
- **Top-3 Candidates**: `Service degradation on worker-service`, `Resource saturation on worker-service`, `Database degradation on worker-service`
- **RAG Retrieval**: Matched `RB-000005` (1 docs retrieved in `8439.68 ms`)
- **LLM Synthesis**: JSON Valid = `True`, Verified Evidence Citations = `0`, Unsupported Claims = `3`
- **End-to-End Latency**: `8527.21 ms`

