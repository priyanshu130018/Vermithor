# Vermithor Cloud Multi-Model Architecture & Evaluation Report

**Generated At:** 2026-10-23T17:17:32.266600+00:00  
**Benchmark Version:** 1.0.0  
**Reproduction Command:** `py -3.10 evaluation/run_cloud_benchmark.py`  
**Pipeline Architecture:** Cloud-Only LangGraph Multi-Model Routing (Hugging Face Inference Providers)

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
- **Client Latency Timing:** Strict wall-clock request timing (`time.perf_counter()`). No unmeasurable internal reasoning times are claimed.
- **Safety Boundaries:** All proposed diagnostic and repair procedures require explicit human approval (`requires_human_approval: true`).

---

## 2. Live Cloud Evaluation Audit (Hugging Face Inference Providers)

**Live Evaluation Status:** **`BLOCKED`**  
**Audit Finding:** `HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits.`

### Live Model Connectivity Probes

| Task | Model ID | HTTP Status | Probe Latency | Status & Reason |
| :--- | :--- | :--- | :--- | :--- |
| **investigation** | `meta-llama/Llama-3.1-8B-Instruct` | `402` | `435.55 ms` | `BLOCKED`: HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits. |
| **summary** | `meta-llama/Llama-3.1-8B-Instruct` | `402` | `288.93 ms` | `BLOCKED`: HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits. |
| **report_review** | `meta-llama/Llama-3.1-8B-Instruct` | `402` | `294.25 ms` | `BLOCKED`: HTTP 402 Payment Required: You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get monthly included credits. |

> [!IMPORTANT]
> **Evaluation Rigor Guarantee:**  
> Per benchmark rigor guidelines, deterministic fallback activations are **NEVER** counted as live cloud model calls. Because the configured Hugging Face Inference Providers account (`apriyanshu13`) returned `HTTP 402 Payment Required: PrepaidCreditsRequired`, live cloud evaluation is formally recorded as **BLOCKED**. No benchmark metrics are fabricated.

---

## 3. Deterministic Baseline Benchmark Results

Tested across a fixed, labeled set of **8 synthetic incident scenarios** (24 repeated trials) including known ground-truth failure families (Database, Deployment, Cache, Memory/OOM, Ingress/Traffic, Auth) and an explicit **ambiguous noise control case** (`ambiguous_noise.yaml`).

### Accuracy & Schema Conformance

| Metric | Measured Baseline | Target Gate | Verification Verdict |
| :--- | :--- | :--- | :--- |
| **RCA Top-1 Accuracy** | **100.0%** | ≥ 75.0% | **PASSED** |
| **RCA Top-3 Accuracy** | **100.0%** | ≥ 85.0% | **PASSED** |
| **Mean Reciprocal Rank (MRR)** | **1.0000** | ≥ 0.7000 | **PASSED** |
| **Valid JSON Schema Rate** | **100.0%** | 100.0% | **PASSED** |
| **Evidence Citation Validity Rate** | **100.0%** | ≥ 95.0% | **PASSED** |
| **Unsupported-Claim Rate** | **0.0%** | ≤ 5.0% | **PASSED** |
| **Deterministic Fallback Rate** | **100.0%** | 100.0% (Live Blocked) | **VERIFIED (NON-LLM)** |

---

### Client-Observed Latency Percentiles (End-to-End)

| Metric | Latency (ms) |
| :--- | :--- |
| **Mean Latency** | `942.51 ms` |
| **p50 Latency** | `834.23 ms` |
| **p90 Latency** | `1207.39 ms` |
| **p95 Latency** | `1578.68 ms` |

---

## 4. Per-Scenario Trial Breakdown

| Trial | Scenario Name | Target Service | Expected Cause | Top-1 Hit | Top-3 Hit | MRR | Latency | Fallback Mode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #1 | `ambiguous_noise` | `booking-api` | `UNKNOWN` | PASS | PASS | 1.00 | 667.93 ms | `fallback` (deterministic-rules (non-LLM)) |
| #2 | `ambiguous_noise` | `booking-api` | `UNKNOWN` | PASS | PASS | 1.00 | 987.03 ms | `fallback` (deterministic-rules (non-LLM)) |
| #3 | `ambiguous_noise` | `booking-api` | `UNKNOWN` | PASS | PASS | 1.00 | 942.57 ms | `fallback` (deterministic-rules (non-LLM)) |
| #4 | `auth_failure` | `auth-api` | `auth_failure` | PASS | PASS | 1.00 | 1087.43 ms | `fallback` (deterministic-rules (non-LLM)) |
| #5 | `auth_failure` | `auth-api` | `auth_failure` | PASS | PASS | 1.00 | 1015.29 ms | `fallback` (deterministic-rules (non-LLM)) |
| #6 | `auth_failure` | `auth-api` | `auth_failure` | PASS | PASS | 1.00 | 936.16 ms | `fallback` (deterministic-rules (non-LLM)) |
| #7 | `bad_deployment` | `booking-api` | `bad_deployment` | PASS | PASS | 1.00 | 1258.8 ms | `fallback` (deterministic-rules (non-LLM)) |
| #8 | `bad_deployment` | `booking-api` | `bad_deployment` | PASS | PASS | 1.00 | 841.27 ms | `fallback` (deterministic-rules (non-LLM)) |
| #9 | `bad_deployment` | `booking-api` | `bad_deployment` | PASS | PASS | 1.00 | 827.19 ms | `fallback` (deterministic-rules (non-LLM)) |
| #10 | `database_saturation` | `booking-api` | `database_saturation` | PASS | PASS | 1.00 | 843.41 ms | `fallback` (deterministic-rules (non-LLM)) |
| #11 | `database_saturation` | `booking-api` | `database_saturation` | PASS | PASS | 1.00 | 993.15 ms | `fallback` (deterministic-rules (non-LLM)) |
| #12 | `database_saturation` | `booking-api` | `database_saturation` | PASS | PASS | 1.00 | 3001.54 ms | `fallback` (deterministic-rules (non-LLM)) |
| #13 | `memory_exhaustion` | `catalog-api` | `memory_exhaustion` | PASS | PASS | 1.00 | 721.09 ms | `fallback` (deterministic-rules (non-LLM)) |
| #14 | `memory_exhaustion` | `catalog-api` | `memory_exhaustion` | PASS | PASS | 1.00 | 857.56 ms | `fallback` (deterministic-rules (non-LLM)) |
| #15 | `memory_exhaustion` | `catalog-api` | `memory_exhaustion` | PASS | PASS | 1.00 | 697.31 ms | `fallback` (deterministic-rules (non-LLM)) |
| #16 | `payment_pool_exhaustion` | `payment-api` | `database_saturation` | PASS | PASS | 1.00 | 792.41 ms | `fallback` (deterministic-rules (non-LLM)) |
| #17 | `payment_pool_exhaustion` | `payment-api` | `database_saturation` | PASS | PASS | 1.00 | 660.78 ms | `fallback` (deterministic-rules (non-LLM)) |
| #18 | `payment_pool_exhaustion` | `payment-api` | `database_saturation` | PASS | PASS | 1.00 | 647.25 ms | `fallback` (deterministic-rules (non-LLM)) |
| #19 | `redis_failure` | `cache-service` | `redis_failure` | PASS | PASS | 1.00 | 656.56 ms | `fallback` (deterministic-rules (non-LLM)) |
| #20 | `redis_failure` | `cache-service` | `redis_failure` | PASS | PASS | 1.00 | 647.19 ms | `fallback` (deterministic-rules (non-LLM)) |
| #21 | `redis_failure` | `cache-service` | `redis_failure` | PASS | PASS | 1.00 | 1635.13 ms | `fallback` (deterministic-rules (non-LLM)) |
| #22 | `traffic_spike` | `worker-service` | `traffic_spike` | PASS | PASS | 1.00 | 645.78 ms | `fallback` (deterministic-rules (non-LLM)) |
| #23 | `traffic_spike` | `worker-service` | `traffic_spike` | PASS | PASS | 1.00 | 584.89 ms | `fallback` (deterministic-rules (non-LLM)) |
| #24 | `traffic_spike` | `worker-service` | `traffic_spike` | PASS | PASS | 1.00 | 672.48 ms | `fallback` (deterministic-rules (non-LLM)) |

---

## 5. How to Reproduce Benchmark Results

Run the standalone benchmark script directly using Python:

```bash
# Set your Hugging Face credentials in .env or environment
export HF_TOKEN="hf_your_token"
export HF_BASE_URL="https://router.huggingface.co/v1"

# Run the 24-trial benchmark suite
python evaluation/run_cloud_benchmark.py
```
