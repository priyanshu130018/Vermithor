# Held-Out Benchmark Ground-Truth Isolation

## Architecture Overview
This directory contains the held-out evaluation answer keys (`answer_keys.json`) used exclusively by the independent benchmark runner (`evaluation/run_held_out_benchmark.py`).

## Physical and Logical Isolation Rules
1. **Zero Exposure to Agent Code:**
   The Vermithor LangGraph Investigation Agent, Evidence Gathering node, RCA Analyzer, Candidate Generator, Scoring Engine, and Repair Agent receive strictly the observational telemetry stored in `../scenarios/holdout_XX.yaml`.
2. **Evaluator-Only Access:**
   Only the evaluation harness reads `answer_keys.json` after the investigation engine finishes execution to compute objective metrics:
   - Top-1 Root Cause Accuracy
   - Top-3 Recall
   - Mean Reciprocal Rank (MRR)
   - Correct Abstention Rate
   - False-Positive Diagnosis Rate
   - Evidence Reference Validity
3. **No Metric or Log Label Pollution:**
   The filenames (`holdout_01.yaml` through `holdout_24.yaml`), event descriptions, metric names, and mock service names contain zero ground-truth labels, answer hints, or diagnostic classifications.
4. **Leakage Verification:**
   Automated unit tests in `backend/tests/agent/test_evaluation_rigor.py` independently inspect the agent runtime state to guarantee no fields matching `expected_root_cause_keywords`, `ground_truth`, or `injected_cause` are present in state graphs, prompts, or LLM contexts.
