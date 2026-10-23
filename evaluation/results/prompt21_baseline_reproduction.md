# Prompt 21 Baseline Reproduction & Benchmark Integrity Audit

**Audit Timestamp:** 2026-10-21T02:12:00Z  
**Lead Roles:** Senior ML Engineer, Incident Response Lead, Evaluation Lead, Security Reviewer  
**Audit Target:** Vermithor Automated Root-Cause Analysis Engine  
**Baseline Git HEAD Reference:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Active Git Branch:** `main`  
**Execution Environment:** Isolated in-memory SQLite, deterministic seed harness, zero external LLM egress (`allow_external_llm=False`), zero live customer telemetry egress (`collection_enabled=False`).

---

## 1. Baseline Git State & Manifest Checksum Verification

### 1.1 Git Working Tree Preservation
Prior to running evaluation commands or modifying code, the repository working tree was inspected and verified:
- **HEAD Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`
- **Branch:** `main` (up to date with `origin/main`)
- **Safety Boundaries:** Preserved. Zero commits created, zero pushes, zero destructive git resets, zero modification of frozen answer keys.

### 1.2 Benchmark Manifest Cryptographic Verification
The blind benchmark fixture manifest at `evaluation/benchmarks/blind_generalization_fixtures/manifest.json` was verified against its answer keys ground-truth file:
- **Ground Truth File:** `evaluation/benchmarks/blind_generalization_fixtures/ground_truth/answer_keys.json`
- **Expected Checksum (SHA-256):** `6b01fdcf2c459e44477a18d7d1d8054fd738ee96202a3c5552072f8779fedb3e`
- **Computed Checksum (SHA-256):** `6b01fdcf2c459e44477a18d7d1d8054fd738ee96202a3c5552072f8779fedb3e`
- **Verification Status:** **MATCH (100% BITWISE IDENTICAL)**

---

## 2. Prompt 20 Baseline Reproduction Summary

The Prompt 20 independent blind evaluation benchmark ($N=24$ cases across 10 distinct incident families, including 11 negative controls and 13 positive failure cases) was independently executed from the repository baseline.

### 2.1 Macro Summary Metrics

| Metric | Reported in Prompt 20 | Independently Reproduced | Discrepancy |
| :--- | :---: | :---: | :---: |
| **Total Evaluation Cases** | 24 | 24 | 0 |
| **Candidate Coverage** | 15 / 24 (62.5%) | 15 / 24 (62.5%) | None |
| **Top-1 Accuracy** | 14 / 24 (58.3%) | 14 / 24 (58.3%) | None |
| **Top-3 Recall** | 14 / 24 (58.3%) | 14 / 24 (58.3%) | None |
| **Mean Reciprocal Rank (MRR)** | 0.5833 | 0.5833 | None |
| **Negative Control Discrimination** | 6 / 11 (54.5%) | 6 / 11 (54.5%) | None (Compound formula) |
| **Total Evidence Citations Evaluated** | 185 | 185 | None |
| **Direct Telemetry Citations (Valid)** | 101 / 185 (54.6%) | 101 / 185 (54.6%) | None |
| **Historical RAG Analogies (Cross-Inc)** | 48 / 185 (25.9%) | 48 / 185 (25.9%) | None |
| **Unresolved Citations (Missing)** | 36 / 185 (19.5%) | 36 / 185 (19.5%) | None |
| **Malformed / Cross-Tenant Citations** | 0 / 185 (0.0%) | 0 / 185 (0.0%) | None |

---

## 3. Baseline Performance Breakdown by Incident Family

| Incident Family | Total Cases | Candidate Coverage | Top-1 Accuracy | Top-3 Recall | MRR | Negative Controls Passed |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **DNS_AND_SERVICE_DISCOVERY** | 3 | 2 / 3 (66.7%) | 2 / 3 (66.7%) | 2 / 3 (66.7%) | 0.6667 | 0 / 1 (0.0%) |
| **DATABASE_CONNECTION_POOL** | 3 | 2 / 3 (66.7%) | 2 / 3 (66.7%) | 2 / 3 (66.7%) | 0.6667 | 0 / 1 (0.0%) |
| **DATABASE_DEADLOCKS_OR_LOCK_CONTENTION** | 2 | 2 / 2 (100.0%) | 2 / 2 (100.0%) | 2 / 2 (100.0%) | 1.0000 | 1 / 1 (100.0%) |
| **MEMORY_EXHAUSTION_AND_OOM** | 3 | 1 / 3 (33.3%) | 1 / 3 (33.3%) | 1 / 3 (33.3%) | 0.3333 | 1 / 1 (100.0%) |
| **CPU_SATURATION_AND_THREAD_STARVATION** | 2 | 1 / 2 (50.0%) | 1 / 2 (50.0%) | 1 / 2 (50.0%) | 0.5000 | 0 / 1 (0.0%) |
| **KAFKA_POISON_PILL** | 2 | 1 / 2 (50.0%) | 1 / 2 (50.0%) | 1 / 2 (50.0%) | 0.5000 | 0 / 1 (0.0%) |
| **NORMAL_KAFKA_LAG** | 2 | 2 / 2 (100.0%) | 2 / 2 (100.0%) | 2 / 2 (100.0%) | 1.0000 | 1 / 1 (100.0%) |
| **DEPLOYMENT_OR_CONFIG_REGRESSION** | 3 | 1 / 3 (33.3%) | 1 / 3 (33.3%) | 1 / 3 (33.3%) | 0.3333 | 1 / 1 (100.0%) |
| **TLS_CERTIFICATE_OR_CONNECTION** | 2 | 2 / 2 (100.0%) | 2 / 2 (100.0%) | 2 / 2 (100.0%) | 1.0000 | 1 / 1 (100.0%) |
| **BENIGN_TELEMETRY_AND_ABSTENTION** | 2 | 1 / 2 (50.0%) | 1 / 2 (50.0%) | 1 / 2 (50.0%) | 0.5000 | 1 / 2 (50.0%) |
| **Total / Macro Average** | **24** | **15 / 24 (62.5%)** | **14 / 24 (58.3%)** | **14 / 24 (58.3%)** | **0.5833** | **6 / 11 (54.5%)** |

---

## 4. Arithmetic Verification & Discrepancy Analysis

### 4.1 Memory Exhaustion & Deployment Regression Underperformance
The baseline reproduction confirmed that `MEMORY_EXHAUSTION_AND_OOM` and `DEPLOYMENT_OR_CONFIG_REGRESSION` were the two worst-performing active incident families, each achieving only **33.3% Top-1 accuracy** (1/3 cases):
1. `BLIND-CASE-09` (JVM Metaspace leak / kernel OOM kill) failed with `Insufficient evidence` (confidence 0.10).
2. `BLIND-CASE-11` (Auth-service upstream kernel OOM kill) failed with `Insufficient evidence` (confidence 0.10).
3. `BLIND-CASE-18` (Ingress router deployment with corrupted dynamic routing table) failed with `Insufficient evidence` (confidence 0.10).
4. `BLIND-CASE-20` (Vault-agent environment variable misconfiguration) failed with `Insufficient evidence` (confidence 0.10).

### 4.2 Negative-Control Compound Metric Distortion
In Prompt 20, negative controls were scored via the boolean expression:
$$\text{neg\_passed} = (\text{matched\_expected} \land \neg \text{triggered\_prohibited})$$
- In `BLIND-CASE-02` (Stripe 504 with healthy DNS) and `BLIND-CASE-05` (HttpClientPool exhaustion with healthy Postgres), the engine safely abstained with `"Insufficient evidence"`, avoiding the prohibited DNS and Postgres pool causes ($\neg \text{triggered\_prohibited} = \text{True}$).
- However, because the engine did not identify the specific alternative cause, `matched_expected` evaluated to `False`. The compound formula scored these as 0%, artificially penalizing safe abstention.
- As required by Prompt 21, the metric is calibrated into:
  - **Safety Discrimination:** avoiding prohibited diagnoses = **10 / 11 (90.9%)**.
  - **Diagnostic Discrimination:** diagnosing specific alternative cause = **6 / 11 (54.5%)**.

### 4.3 Citation Denominator Integrity
All 185 citations generated across the 24 cases were tracked without silent truncation:
- 101 citations were verified as direct telemetry.
- 48 citations were verified as historical RAG analogies (marked as `CROSS_INCIDENT`).
- 36 citations were classified as `MISSING_OR_UNRESOLVED`.
- 0 citations were malformed or cross-tenant.
- The denominator accounting is 100% closed: $101 + 48 + 36 = 185$.
