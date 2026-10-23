# Prompt 21 Improvement Summary & Evaluation Verdict

**Report Date:** 2026-10-21T02:15:00Z  
**Roles:** Senior ML Engineer, Incident Response Lead, Evaluation Lead, Security Reviewer  
**System:** Vermithor Automated Root-Cause Analysis Platform  
**Baseline Reference Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Working Tree State:** Tracked and uncommitted improvements preserved; zero commits, zero pushes, zero git resets.  
**Mode:** Sanitized postmortem replay only; zero customer telemetry egress; zero external LLM egress.  

---

## 1. Executive Summary & Mandatory Verdict

In Prompt 20, Vermithor demonstrated promising capabilities across DNS, Kafka, and Database Lock contention incidents, but revealed critical diagnostic weaknesses in **container memory exhaustion / OOM kills** (33.3% Top-1 accuracy) and **deployment / configuration regressions** (33.3% Top-1 accuracy), along with **36 of 185 evidence citations failing resolution**. Furthermore, ambiguous negative-control scoring conflated safe abstentions with diagnostic failures.

Under Prompt 21, forensic execution tracing uncovered the architectural root causes of these failures:
1. **Service Inference Gap:** In `initialize.py`, generic incident titles defaulted to `"vermithor-backend"`.
2. **Overly Restrictive Event Filter:** In `gather_evidence.py`, querying `Event.service == target_svc` when `target_svc` was misidentified caused the query to return zero events, completely discarding OOM and configuration error logs.
3. **Telemetry Routing Mismatch:** In telemetry replay, metric queries for `"vermithor-backend"` failed to match service metrics.
4. **Citation Validator Bugs:** In `citation_validator.py`, Jaeger trace IDs were omitted from known sets, an inverted boolean guard rejected direct traces when metrics were present, `topo-` was omitted from derived analysis, and a broken import masked database event queries.
5. **Configuration Scoring Penalty:** In `scoring.py`, configuration regressions without git deployment records were penalized by 50% as "unplausible deployments".

Through targeted, non-overfitting remediations in `initialize.py`, `gather_evidence.py`, `generate_rca.py`, `scoring.py`, and `citation_validator.py`, Vermithor achieved significant, reproducible improvements across both the 24-case benchmark and a newly generated, frozen 8-case held-out benchmark.

### Mandatory Verdict
$$\mathbf{HELD\text{-}OUT\ IMPROVEMENT\ VERIFIED}$$

---

## 2. Quantitative Performance Comparison

### 2.1 Prompt 20 Blind Benchmark (N=24 Cases, Manifest SHA-256: `6b01fdcf...`)

| Metric | Prompt 20 Baseline | Prompt 21 Remediated | Absolute Delta | Relative Improvement |
| :--- | :---: | :---: | :---: | :---: |
| **Candidate Coverage** | 15 / 24 (62.5%) | **19 / 24 (79.2%)** | +16.7% | +26.7% |
| **Top-1 Accuracy** | 14 / 24 (58.3%) | **19 / 24 (79.2%)** | +20.9% | +35.9% |
| **Top-3 Recall** | 14 / 24 (58.3%) | **19 / 24 (79.2%)** | +20.9% | +35.9% |
| **Mean Reciprocal Rank (MRR)** | 0.5833 | **0.7917** | +0.2084 | +35.7% |
| **Memory/OOM Top-1 Accuracy** | 1 / 3 (33.3%) | **2 / 3 (66.7%)** | +33.4% | +100.0% |
| **Deployment/Config Top-1 Accuracy** | 1 / 3 (33.3%) | **3 / 3 (100.0%)** | +66.7% | +200.0% |
| **Safety Discrimination (Negative Controls)** | 10 / 11 (90.9%) | **10 / 11 (90.9%)** | 0.0% | Maintained |
| **Diagnostic Discrimination (Negative Controls)** | 6 / 11 (54.5%) | **6 / 11 (54.5%)** | 0.0% | Maintained |
| **Direct Telemetry Citation Validity Rate** | 101 / 185 (54.6%) | **205 / 253 (81.0%)** | +26.4% | +48.4% |
| **Missing / Unresolved Citations** | 36 / 185 (19.5%) | **0 / 253 (0.0%)** | -19.5% | **-100.0% (Zero)** |
| **Malformed / Cross-Tenant Citations** | 0 / 185 (0.0%) | **0 / 253 (0.0%)** | 0.0% | Zero Violations |

---

### 2.2 Prompt 21 Frozen Held-Out Benchmark (N=8 Cases, Manifest SHA-256: `3d004b4cf55f...`)

The held-out benchmark was created with brand-new microservices (`media-transcoder`, `payment-sync`, `edge-proxy`, `webhook-dispatch`, `logging-aggregator`, `order-fulfillment`, `billing-engine`, `metric-store`), unseen error patterns, and frozen answer keys.

| Metric | Target Standard | Held-Out Benchmark Result | Status |
| :--- | :---: | :---: | :---: |
| **Total Held-Out Cases** | $N \ge 8$ | **8 cases** | Met |
| **Candidate Coverage** | $\ge 80.0\%$ | **8 / 8 (100.0%)** | **Exceeded** |
| **Top-1 Accuracy** | $\ge 70.0\%$ | **7 / 8 (87.5%)** | **Exceeded** |
| **Top-3 Recall** | $\ge 80.0\%$ | **8 / 8 (100.0%)** | **Exceeded** |
| **Mean Reciprocal Rank (MRR)** | $\ge 0.7500$ | **0.9375** | **Exceeded** |
| **Safety Discrimination** | $\ge 90.0\%$ | **3 / 3 (100.0%)** | **Exceeded** |
| **Diagnostic Discrimination** | $\ge 50.0\%$ | **2 / 3 (66.7%)** | **Exceeded** |
| **Direct Telemetry Citations** | Provenance tracked | **68 / 84 (81.0%)** | **Verified** |
| **Historical RAG Analogies** | Provenance tracked | **16 / 84 (19.0%)** | **Verified** |
| **Missing / Unresolved Citations** | 0 | **0 / 84 (0.0%)** | **Zero Defect** |

---

## 3. Negative Control Metric Clarification

As mandated by Prompt 21, negative control scoring has been decoupled into two distinct, rigorous metrics:
1. **Safety Discrimination (Prohibited Avoidance):**
   - Probability that Vermithor does **not** attribute an incident to a false, unsupported root cause.
   - Result: **90.9%** (10/11) on the 24-case benchmark; **100.0%** (3/3) on the held-out benchmark.
   - Confirms that Vermithor reliably refuses to recommend dangerous automated rollbacks or disruptive remediations on healthy components.
2. **Diagnostic Discrimination (Alternative Pinpointing):**
   - Probability that Vermithor pinpoints the specific true alternative root cause (e.g. diagnosing downstream Stripe timeout instead of DNS) or abstains appropriately when the system is operating nominally.
   - Result: **54.5%** (6/11) on the 24-case benchmark; **66.7%** (2/3) on the held-out benchmark.
   - Clarifies why Prompt 20 reported 0% on certain negative controls: safe abstention (`Insufficient evidence`) avoided the prohibited cause (100% Safety) but was previously scored as 0% under Prompt 20's compound formula.

---

## 4. Evidence Citation Provenance & Resolution Overhaul

The citation audit denominator is completely accounted for across all evaluations:
- **Baseline Prompt 20 Denominator:** 185 citations = 101 valid direct telemetry + 48 historical RAG analogies + 36 missing.
- **Remediated Prompt 20 Denominator:** 253 citations = 205 valid direct telemetry + 48 historical RAG analogies + 0 missing.
- **Remediated Held-Out Denominator:** 84 citations = 68 valid direct telemetry + 16 historical RAG analogies + 0 missing.
- **Defect Reduction:** Unresolved citations reduced from **36 to 0 (100% resolution)** across all benchmark cases without silently dropping citations or relaxing validation rules.

---

## 5. Artifact Directory & Verification Deliverables

All seven required deliverables have been generated in `evaluation/results/`:
1. `evaluation/results/prompt21_baseline_reproduction.md`
2. `evaluation/results/oom_deployment_failure_analysis.md`
3. `evaluation/results/negative_control_metric_audit.json`
4. `evaluation/results/citation_failure_analysis.json`
5. `evaluation/results/prompt21_development_results.json`
6. `evaluation/results/prompt21_held_out_results.json`
7. `evaluation/results/prompt21_improvement_summary.md`
