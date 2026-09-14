# Vermithor Evaluation Benchmark Framework

Vermithor incorporates a quantitative evaluation benchmark suite (`evaluation/evaluator.py`) designed to measure incident management performance across 7 operational incident scenarios.

---

## 1. Operational Incident Scenarios

The benchmark suite tests the platform against 7 deterministic operational scenarios in `evaluation/scenarios/`:

1. `database_saturation.yaml` — PostgreSQL connection pool exhaustion causing cascading checkout HTTP 500 errors.
2. `bad_deployment.yaml` — Regression introduced in release v2.4.8 causing widespread NullPointerExceptions.
3. `redis_failure.yaml` — Redis cache node failure tripping circuit breakers on cache-service.
4. `memory_exhaustion.yaml` — JVM heap memory exhaustion, GC thrashing, and container OOMKilled events.
5. `traffic_spike.yaml` — Sudden ingress traffic spike causing worker pool CPU starvation.
6. `auth_failure.yaml` — Expired JWKS signing key rotation causing HTTP 401 Unauthorized spikes.
7. `ambiguous_noise.yaml` — Isolated transient socket jitter with uncoordinated noise preserving `UNKNOWN` root cause.

---

## 2. Evaluation Metrics

The framework evaluates the following quantitative metrics:

- **RCA Top-1 Accuracy**: Proportion of scenarios where the true root cause service is ranked #1.
- **RCA Top-3 Accuracy**: Proportion of scenarios where the true root cause service appears in the top 3 candidates.
- **RCA Mean Reciprocal Rank (MRR)**: Average reciprocal rank of the true root cause service:
  $$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$
- **Anomaly Detection F1 Score**: Harmonic mean of precision and recall for anomaly identification:
  $$F1 = 2 \cdot \frac{\text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$
- **LLM JSON Validity Rate**: Percentage of LLM synthesis outputs conforming strictly to JSON schema.
- **Ambiguity Preservation Rate**: Accuracy in preserving `UNKNOWN` root cause when signal confidence $\le 0.40$.

---

## 3. Running the Evaluator

Execute the benchmark suite using Python:

```bash
python evaluation/evaluator.py
```

Generated evaluation reports are written to:
- **JSON Output**: `evaluation/results/latest.json`
- **Markdown Report**: `evaluation/report.md`

---

## 4. Benchmark Target SLAs vs Repository Results

| Metric | Benchmark SLA Target | Verified Result | Status |
|---|---|---|---|
| **RCA Top-1 Accuracy** | $\ge 80.0\%$ | **100.0%** (7/7) | ✅ PASSED |
| **RCA Top-3 Accuracy** | $\ge 95.0\%$ | **100.0%** (7/7) | ✅ PASSED |
| **RCA Mean Reciprocal Rank (MRR)** | $\ge 0.850$ | **1.000** | ✅ PASSED |
| **Anomaly Detection F1 Score** | $\ge 0.950$ | **1.000** | ✅ PASSED |
| **LLM JSON Schema Validity** | $100.0\%$ | **100.0%** | ✅ PASSED |
| **Ambiguity Preservation (`UNKNOWN`)** | $100.0\%$ | **100.0%** | ✅ PASSED |
