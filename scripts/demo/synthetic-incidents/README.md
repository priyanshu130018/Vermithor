# Vermithor Synthetic Incident Generator

The **Synthetic Incident Generator** provides deterministic, causally-linked telemetry generation for automated testing, end-to-end incident verification, and live SRE demonstrations.

---

## 1. Scenario: Database Connection Saturation

The primary scenario (`scenarios/database_connection_saturation.yaml`) reproduces a cascading production outage in `booking-api`:

```text
T+00s: Normal Baseline Traffic
       (DB latency: 100ms, Pool utilization: 40%, API latency: 150ms, HTTP 5xx: 0.5%)
         │
         ▼
T+30s: Latency Degradation
       (DB latency: 450ms, Pool utilization: 75%, API latency: 550ms)
         │
         ▼
T+60s: Pool Saturation & Queue Timeouts
       (Pool utilization: 98%, DB query latency: 1200ms, ConnectionAcquisitionTimeoutError logs)
         │
         ▼
T+90s: Critical API Failure Cascade
       (API latency: 2200ms, HTTP 500 error rate: 25%, Transaction timeout logs)
         │
         ▼
T+120s: Deployment Event Linkage
       (v2.4.7 deployment introducing reduced pool max_size from 100 to 50)
```

---

## 2. CLI Usage

### Fast Mode (Default)
Generates the entire scenario timeline instantly ($\approx 1$ second) with relative historical timestamps:
```bash
python tools/synthetic-incidents/generator.py --scenario database_connection_saturation
```

### Dry-Run Mode
Inspect the telemetry batch and metadata counts without transmitting requests:
```bash
python tools/synthetic-incidents/generator.py --scenario database_connection_saturation --dry-run
```

### Live Mode
Emits events with real-time delays between stages:
```bash
python tools/synthetic-incidents/generator.py --scenario database_connection_saturation --live
```

### Target Custom Gateway URL
```bash
python tools/synthetic-incidents/generator.py \
  --scenario database_connection_saturation \
  --api-url http://localhost:8080
```

---

## 3. End-to-End Pipeline Verification

When run against the active Vermithor cluster, this scenario exercises:
1. **Ingestion Service (:8001)**: Parses and persists events, metrics, logs, and deployment markers.
2. **Anomaly Service (:8003)**: Computes statistical z-scores and flags latency/saturation outliers.
3. **Correlation Engine (:8004)**: Correlates DB metrics and API 500s into a unified incident.
4. **Incident Service (:8002)**: Updates incident status and attaches correlated evidence.
5. **RCA Service (:8005)**: Builds causal dependency graph and identifies database pool saturation as the #1 root cause.
6. **Log Intelligence Service (:8006)**: Surfaces semantically similar timeout logs via vector search.
7. **Retrieval Service (:8007)**: RAG matches relevant runbooks and historical postmortems.
8. **Summary Service (:8008)**: Produces an evidence-grounded AI incident summary.
