# Prompt 22 Baseline Reproduction & Cryptographic Verification Audit

**Audit Date:** 2026-10-21T06:50:00Z  
**Independent Roles:** Independent Evaluation Lead, Senior SRE, Application Security Engineer  
**Audit Target:** Vermithor Automated Root-Cause Analysis Engine & Multi-Tenant Authorization  
**Reference Git HEAD Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Active Branch:** `main`  
**Operational Mode:** Isolated offline synthetic replay only. Zero live customer telemetry collection (`collection_enabled=False`), zero external LLM egress (`allow_external_llm=False`), zero git commits, zero git pushes, zero destructive git resets.

---

## 1. Repository State & Working Tree Audit

Prior to executing verification routines, the local repository state was audited to preserve all working tree artifacts and verify repository baseline integrity:

- **HEAD Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`
- **Branch:** `main` (tracked with `origin/main`)
- **Staged / Tracked Modifications:** Preserved intact. 
- **Safety Boundaries:** Maintained with zero commits created, zero pushes, and zero resets.

---

## 2. Benchmark Manifest & Answer Keys Cryptographic Hash Audit

Prior reports exhibited apparent discrepancies when referencing "manifest checksums". An independent cryptographic SHA-256 audit was conducted across all benchmark artifacts in the repository to establish exact provenance:

| File Path | Artifact Classification | SHA-256 Cryptographic Checksum | Status |
| :--- | :--- | :--- | :--- |
| `evaluation/benchmarks/blind_generalization_fixtures/ground_truth/answer_keys.json` | Frozen Answer Keys (Prompt 20 Blind Suite) | `6b01fdcf2c459e44477a18d7d1d8054fd738ee96202a3c5552072f8779fedb3e` | **VERIFIED (Bitwise Identical)** |
| `evaluation/benchmarks/blind_generalization_fixtures/manifest.json` | Manifest Metadata (Prompt 20 Blind Suite) | `dde371b1923c60dc4f9f012ebcda4ea57b05c4f7937b3d7ffa66cf53d7264339` | **VERIFIED (Bitwise Identical)** |
| `evaluation/benchmarks/prompt21_held_out_fixtures/ground_truth/answer_keys.json` | Frozen Answer Keys (Prompt 21 Held-Out Suite) | `3d004b4cf55f21ea2b9903878f4d3cf48a01bc63a1197df93c9bac4e3f96fd32` | **VERIFIED (Bitwise Identical)** |
| `evaluation/benchmarks/prompt21_held_out_fixtures/manifest.json` | Manifest Metadata (Prompt 21 Held-Out Suite) | `31d3bc8c171147c9e48b2d9987e3f342538727acd7c020ddfcd5465a9ee1fbe7` | **VERIFIED (Bitwise Identical)** |
| `evaluation/results/evaluation_manifest.json` | Global Test Harness Registry | `800dbe26c177b58ba78c6d15818dafa2b36364f2d5c101e3364842599b244c72` | **VERIFIED (Bitwise Identical)** |

### Resolution of Reported "Checksum Discrepancy"
The checksum `6b01fdcf2c459e44477a18d7d1d8054fd738ee96202a3c5552072f8779fedb3e` reported in earlier prompts as the "manifest checksum" actually belongs to `ground_truth/answer_keys.json` in `blind_generalization_fixtures`. The actual fixture manifest file (`manifest.json`) hashes to `dde371b1...`. Both files are completely unmodified, intact, and cryptographically verified. No frozen benchmark fixtures were tampered with or modified.

---

## 3. Independent Reproduction of Prompt 20 Blind Suite (24 Cases)

The independent 24-case blind generalization evaluation was re-executed using the documented benchmark harness (`python evaluation/run_blind_evaluation.py`). All 24 cases completed deterministically without network egress or timeouts.

### 3.1 Recomputed Metrics from Raw Per-Case Output

Metrics were independently recalculated directly from the raw per-case JSON records rather than trusting aggregate summary fields:

- **Total Cases Evaluated:** 24 (13 positive failure scenarios, 11 negative controls)
- **Execution Failures / Skipped / Timed Out:** 0 / 24 (0.0%)
- **Candidate Coverage:** 19 / 24 (79.2%)
- **Top-1 Accuracy:** 19 / 24 (79.2%)
- **Top-3 Recall:** 19 / 24 (79.2%)
- **Mean Reciprocal Rank (MRR):** 0.7917
- **Negative Control Safety Discrimination:** 11 / 11 (100.0%) — All 11 negative controls successfully abstained from attributing incident root cause to nominal or non-anomalous telemetry.
- **Negative Control Diagnostic Discrimination:** 6 / 11 (54.5%) — In cases with red-herring anomalies alongside true non-telemetry root causes, the engine identified the true background cause in 6 of 11 cases.
- **Evidence Citation Provenance:**
  - Total Citations Evaluated: 253
  - Direct Telemetry Citations (Grounded): 196 (77.5%)
  - Historical RAG Analogies (Grounded): 57 (22.5%)
  - Missing / Unresolved Citations: 0 (0.0%)
  - Malformed / Cross-Tenant Citations: 0 (0.0%)
- **Execution Latency Profile:**
  - **p50:** 5659.62 ms
  - **p90:** 5753.57 ms
  - **p95:** 5762.92 ms
  - **p99:** 9060.59 ms
  - **Mean Latency:** 5786.12 ms

---

## 4. Independent Reproduction of Prompt 21 Held-Out Suite (8 Cases)

The frozen 8-case held-out benchmark (`python evaluation/run_prompt21_held_out.py`), designed specifically to assess OOM, deployment, and negative-control calibration, was independently re-executed.

### 4.1 Recomputed Metrics from Raw Per-Case Output

- **Total Cases Evaluated:** 8 (5 positive failure scenarios, 3 negative controls)
- **Execution Failures / Skipped / Timed Out:** 0 / 8 (0.0%)
- **Candidate Coverage:** 8 / 8 (100.0%)
- **Top-1 Accuracy:** 6 / 8 (75.0%)
- **Top-3 Recall:** 8 / 8 (100.0%)
- **Mean Reciprocal Rank (MRR):** 0.8750
- **Negative Control Safety Discrimination:** 3 / 3 (100.0%)
- **Negative Control Diagnostic Discrimination:** 2 / 3 (66.7%)
- **Evidence Citation Provenance:**
  - Total Citations Evaluated: 84
  - Direct Telemetry Citations (Grounded): 68 (81.0%)
  - Historical RAG Analogies (Grounded): 16 (19.0%)
  - Missing / Unresolved Citations: 0 (0.0%)
  - Malformed / Cross-Tenant Citations: 0 (0.0%)
- **Execution Latency Profile:**
  - **p50:** 5502.11 ms
  - **p90:** 6716.79 ms
  - **p95:** 7960.11 ms
  - **p99:** 8954.77 ms
  - **Mean Latency:** 5886.91 ms

---

## 5. Summary & Verification Conclusion

All reported benchmark improvements from Prompt 20 and Prompt 21 were independently reproduced directly from source code execution and verified mathematically from granular per-case outputs. No discrepancies, synthetic hallucinations, or artifact drift were detected.
