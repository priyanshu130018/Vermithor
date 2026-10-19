# Vermithor Resilience & Failure Recovery Test Suite

This directory contains automated resilience, fault injection, and self-healing validation suites for the **Vermithor** AI Production Incident Intelligence Platform.

---

## 1. Test Matrix

| Test Module | Failure Mode Tested | Expected Recovery Behavior |
| :--- | :--- | :--- |
| **`test_service_failure.py`** | Stateless pod crash / unready state | Kubernetes readiness probe halts traffic routing; replacement pod starts and assumes traffic with zero persistent data loss. |
| **`test_dependency_failure.py`** | Upstream timeout / network partitions | Gateway returns structured 502/504 error envelopes with `X-Request-ID` without hanging indefinitely. |
| **`test_database_failure.py`** | Transient PostgreSQL outage | Database connection pool fails gracefully, drops stale connections, and reconnects automatically upon database return. |
| **`test_redis_failure.py`** | Redis broker outage | Ingestion task publisher handles connection failure gracefully with fallback / log persistence. |
| **`test_llm_failure.py`** | Hugging Face / LLM provider outage / timeout | Summary service synthesizes structured fallback summary and marks `status: FAILED` or degraded mode without crashing. |
| **`test_recovery.py`** | Post-recovery end-to-end pipeline | After recovering from dependency or service fault, the full `database_connection_saturation` pipeline completes with 100% fidelity. |

---

## 2. Running Resilience Tests

```bash
python -m pytest tests/resilience -v
```
