# Vermithor Cloud Multi-Model Architecture & Evaluation Report

**Generated At:** 2026-10-23T18:56:33.829035+00:00  
**Benchmark Version:** 1.1.0  
**Reproduction Command:** `py -3.10 evaluation/run_cloud_benchmark.py`  
**Pipeline Architecture:** Cloud-Only LangGraph Multi-Model Routing (Hugging Face Inference Providers)  
**Matching Engine:** `ScenarioCauseMatcher` (Strict Ground-Truth & Negative Controls)

---

## 1. Multi-Model Task-Specific Routing

Vermithor implements dedicated task-specific model routing across its LangGraph investigation and summary graph. Each intelligence task is independently configurable via environment variables without hard-coded assumptions of model availability or zero-cost tiers.

| Intelligence Task | Configured Cloud Model ID | Environment Setting | Fallback Mode |
| :--- | :--- | :--- | :--- |
| **Investigation & RCA** | `meta-llama/Llama-3.1-8B-Instruct` | `HF_INVESTIGATION_MODEL` | Grounded Deterministic Rules (Non-LLM) |
| **Summary Generation** | `meta-llama/Llama-3.1-8B-Instruct` | `HF_SUMMARY_MODEL` | Grounded Deterministic Synthesizer (Non-LLM) |
| **Report Review & Verification** | `meta-llama/Llama-3.1-8B-Instruct` | `HF_REVIEW_MODEL` | Citation Integrity & Safety Checker (Non-LLM) |

- **Backend Provider:** Hugging Face Inference Providers Router (`https://router.huggingface.co/v1`).
- **Local Ollama Status:** Completely removed from active runtime configuration and setup runbooks.
- **Client Latency Timing:** Strict wall-clock request timing (`time.perf_counter()`). No unmeasurable internal provider reasoning times are claimed.
- **Safety Boundaries:** All proposed diagnostic and repair procedures require explicit human approval (`requires_human_approval: true`).

---

## 2. Live Cloud Evaluation Audit (Hugging Face Inference Providers)

**Live Evaluation Status:** **`BLOCKED`**  
**Audit Finding:** `HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits.`

### Live Model Connectivity Probes

| Task | Model ID | HTTP Status | Probe Latency | Status & Reason |
| :--- | :--- | :--- | :--- | :--- |
| **investigation** | `meta-llama/Llama-3.1-8B-Instruct` | `402` | `447.33 ms` | `BLOCKED`: HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits. |
| **summary** | `meta-llama/Llama-3.1-8B-Instruct` | `402` | `311.57 ms` | `BLOCKED`: HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits. |
| **report_review** | `meta-llama/Llama-3.1-8B-Instruct` | `402` | `313.6 ms` | `BLOCKED`: HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits. |

> [!WARNING]
> **Live Cloud AI Model Evaluation Status: BLOCKED**  
> Because the configured Hugging Face Inference Providers account returned `HTTP 402 Payment Required: PrepaidCreditsRequired`, live cloud model calls could not be executed.  
> 
> **Evaluation Rigor Guarantees:**  
> 1. **Live Accuracy Metrics:** **`UNAVAILABLE (BLOCKED)`**. Vermithor does NOT claim live AI model accuracy when cloud inference is blocked.  
> 2. **Actual Model Latency:** **`UNAVAILABLE (BLOCKED)`**. Because 0 live model requests were completed, no model request latency is claimed.  
> 3. **No Metric Conflation:** Deterministic fallback results are strictly labeled as baseline rules and NEVER reported as live LLM accuracy.

---

## 3. Deterministic Baseline Benchmark Results

Tested across a fixed, labeled corpus of **8 synthetic incident scenarios** (24 repeated trials) evaluated against ground-truth answer keys using strict domain matching (`ScenarioCauseMatcher`) with negative controls.

> [!NOTE]
> **Deterministic Baseline Notice:**  
> The metrics below measure Vermithor's rule-based candidate generation, scoring, and citation verification fallback engine (`model_name: deterministic-rules (non-LLM)`). These metrics demonstrate that the deterministic baseline achieves 100% telemetry grounding, zero hallucinations, and high diagnostic precision when external AI providers are unavailable.

### Baseline Accuracy & Schema Conformance

| Metric | Measured Baseline | Target Gate | Verification Verdict |
| :--- | :--- | :--- | :--- |
| **RCA Top-1 Accuracy** | **100.0%** | ≥ 75.0% | **PASSED (BASELINE)** |
| **RCA Top-3 Accuracy** | **100.0%** | ≥ 85.0% | **PASSED (BASELINE)** |
| **Mean Reciprocal Rank (MRR)** | **1.0000** | ≥ 0.7000 | **PASSED (BASELINE)** |
| **Valid JSON Schema Rate** | **100.0%** | 100.0% | **PASSED (BASELINE)** |
| **Evidence Citation Validity Rate** | **100.0%** | ≥ 95.0% | **PASSED (BASELINE)** |
| **Unsupported-Claim Rate** | **0.0%** | ≤ 5.0% | **PASSED (BASELINE)** |
| **Deterministic Fallback Rate** | **100.0%** | 100.0% (Live Blocked) | **VERIFIED (NON-LLM)** |

---

## 4. Timing Dimension Separation

Timing metrics are strictly divided into three distinct measurements without fabricating internal reasoning times:

| Timing Dimension | Measured Time | Description |
| :--- | :--- | :--- |
| **Provider Health-Check Time** | `1075.77 ms` | Total wall-clock time to probe HF router endpoints. |
| **Benchmark Pipeline Total Time** | `34.4 ms` | Total execution duration across all 24 scenario trials. |
| **Deterministic Pipeline Latency (Mean)** | `1.05 ms` | Mean execution time per trial of the deterministic pipeline. |
| **Deterministic Pipeline Latency (p50)** | `0.91 ms` | Median execution time per trial of the deterministic pipeline. |
| **Deterministic Pipeline Latency (p90)** | `1.74 ms` | 90th percentile execution time per trial. |
| **Deterministic Pipeline Latency (p95)** | `1.76 ms` | 95th percentile execution time per trial. |
| **Actual Model Request Latency** | `UNAVAILABLE (BLOCKED)` | Client-observed HTTP round-trip latency to live LLM. |

---

## 5. Per-Scenario Trial Breakdown

| Trial | Scenario Name | Target Service | Expected Cause | Top-1 Hit | Top-3 Hit | MRR | Pipeline Latency | Execution Mode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #1 | `ambiguous_noise` | `booking-api` | `UNKNOWN` | PASS | PASS | 1.00 | 0.81 ms | `fallback` (deterministic-rules (non-LLM)) |
| #2 | `ambiguous_noise` | `booking-api` | `UNKNOWN` | PASS | PASS | 1.00 | 0.24 ms | `fallback` (deterministic-rules (non-LLM)) |
| #3 | `ambiguous_noise` | `booking-api` | `UNKNOWN` | PASS | PASS | 1.00 | 0.15 ms | `fallback` (deterministic-rules (non-LLM)) |
| #4 | `auth_failure` | `auth-api` | `auth_failure` | PASS | PASS | 1.00 | 0.47 ms | `fallback` (deterministic-rules (non-LLM)) |
| #5 | `auth_failure` | `auth-api` | `auth_failure` | PASS | PASS | 1.00 | 0.4 ms | `fallback` (deterministic-rules (non-LLM)) |
| #6 | `auth_failure` | `auth-api` | `auth_failure` | PASS | PASS | 1.00 | 0.34 ms | `fallback` (deterministic-rules (non-LLM)) |
| #7 | `bad_deployment` | `booking-api` | `bad_deployment` | PASS | PASS | 1.00 | 0.94 ms | `fallback` (deterministic-rules (non-LLM)) |
| #8 | `bad_deployment` | `booking-api` | `bad_deployment` | PASS | PASS | 1.00 | 0.8 ms | `fallback` (deterministic-rules (non-LLM)) |
| #9 | `bad_deployment` | `booking-api` | `bad_deployment` | PASS | PASS | 1.00 | 0.77 ms | `fallback` (deterministic-rules (non-LLM)) |
| #10 | `database_saturation` | `booking-api` | `database_saturation` | PASS | PASS | 1.00 | 2.71 ms | `fallback` (deterministic-rules (non-LLM)) |
| #11 | `database_saturation` | `booking-api` | `database_saturation` | PASS | PASS | 1.00 | 1.72 ms | `fallback` (deterministic-rules (non-LLM)) |
| #12 | `database_saturation` | `booking-api` | `database_saturation` | PASS | PASS | 1.00 | 1.76 ms | `fallback` (deterministic-rules (non-LLM)) |
| #13 | `memory_exhaustion` | `catalog-api` | `memory_exhaustion` | PASS | PASS | 1.00 | 1.1 ms | `fallback` (deterministic-rules (non-LLM)) |
| #14 | `memory_exhaustion` | `catalog-api` | `memory_exhaustion` | PASS | PASS | 1.00 | 0.86 ms | `fallback` (deterministic-rules (non-LLM)) |
| #15 | `memory_exhaustion` | `catalog-api` | `memory_exhaustion` | PASS | PASS | 1.00 | 0.77 ms | `fallback` (deterministic-rules (non-LLM)) |
| #16 | `payment_pool_exhaustion` | `payment-api` | `database_saturation` | PASS | PASS | 1.00 | 1.41 ms | `fallback` (deterministic-rules (non-LLM)) |
| #17 | `payment_pool_exhaustion` | `payment-api` | `database_saturation` | PASS | PASS | 1.00 | 1.75 ms | `fallback` (deterministic-rules (non-LLM)) |
| #18 | `payment_pool_exhaustion` | `payment-api` | `database_saturation` | PASS | PASS | 1.00 | 1.68 ms | `fallback` (deterministic-rules (non-LLM)) |
| #19 | `redis_failure` | `cache-service` | `redis_failure` | PASS | PASS | 1.00 | 1.17 ms | `fallback` (deterministic-rules (non-LLM)) |
| #20 | `redis_failure` | `cache-service` | `redis_failure` | PASS | PASS | 1.00 | 1.35 ms | `fallback` (deterministic-rules (non-LLM)) |
| #21 | `redis_failure` | `cache-service` | `redis_failure` | PASS | PASS | 1.00 | 1.13 ms | `fallback` (deterministic-rules (non-LLM)) |
| #22 | `traffic_spike` | `worker-service` | `traffic_spike` | PASS | PASS | 1.00 | 1.16 ms | `fallback` (deterministic-rules (non-LLM)) |
| #23 | `traffic_spike` | `worker-service` | `traffic_spike` | PASS | PASS | 1.00 | 0.88 ms | `fallback` (deterministic-rules (non-LLM)) |
| #24 | `traffic_spike` | `worker-service` | `traffic_spike` | PASS | PASS | 1.00 | 0.76 ms | `fallback` (deterministic-rules (non-LLM)) |

---

## 6. How to Reproduce Benchmark Results

Run the standalone benchmark script directly using Python:

```bash
# Set your Hugging Face credentials in .env or environment
export HF_TOKEN="hf_your_token"
export HF_BASE_URL="https://router.huggingface.co/v1"

# Run the 24-trial benchmark suite
python evaluation/run_cloud_benchmark.py
```
