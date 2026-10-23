# Held-Out Evaluation Fixtures (Track B: Generalization Benchmark)

## Dataset Version: 1.0.0
**Status:** FROZEN (Created for Prompt 19 Independent Generalization Evaluation)  
**Creation Date:** 2026-10-21  

### Objective
This held-out benchmark suite evaluates whether the root-cause candidate coverage improvements implemented for DNS resolution and Kafka message broker failures generalize to unseen production topologies without overfitting to development cases (`PILOT-CASE-04` and `PILOT-CASE-08`).

### Architecture & Provenance
The benchmark comprises 4 realistic synthetic scenarios:
- **HELDOUT-CASE-01 (`INC-HELDOUT-301`):** CoreDNS upstream UDP packet drop on `billing-worker` calling internal database endpoint. (Positive DNS test).
- **HELDOUT-CASE-02 (`INC-HELDOUT-302`):** Negative Control for DNS. Outbound HTTP 504 Gateway Timeout from external Stripe partner on `checkout-gateway`. DNS resolution latency is nominal (1.8ms) and resolver logs are healthy. The engine must identify downstream gateway timeout and must NOT accuse DNS.
- **HELDOUT-CASE-03 (`INC-HELDOUT-303`):** Kafka poison-pill message stall on `event-ingest-stream`. Malformed protobuf payload at partition 2 offset 482019 triggers deserialization exception, consumer thread stall, and rising lag. (Positive Poison-Pill test).
- **HELDOUT-CASE-04 (`INC-HELDOUT-304`):** Negative Control for Kafka Poison-Pill. Consumer lag backlog on `notification-worker` following pod autoscaling rebalance with 0 errors and nominal fetch rates. The engine must identify consumer lag backlog and must NOT accuse a poison-pill.

### Ground Truth Isolation
Ground-truth answer keys are physically segregated in `ground_truth/answer_keys.json` and are never loaded or accessed by the LangGraph agent during investigation runtime.

### Limitations
- Evaluated in replay mode using in-memory SQLite (`StaticPool`).
- Ground-truth evaluation strictly enforces both positive keyword matches and negative prohibited keyword disqualifications.
