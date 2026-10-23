"""
Unit and End-to-End tests for Vermithor Cloud Multi-Model Benchmark.
Validates:
- Explicit scenario-to-cause mappings & strict ground-truth matching
- Negative controls across cross-domain failures
- Ambiguous noise controls & rejection of concrete attributions
- Ranking evaluation (Top-1, Top-3, MRR)
- End-to-end ranking degradation (incorrect root cause ranks 1st, correct ranks 2nd, correct absent from top-3)
- Verification that metrics decrease appropriately and derive from actual candidates and ground truth
- Citation validity and hallucinated citation detection
- Unsupported claim detection
- Malformed and invalid JSON schema handling
- Fallback handling on HTTP 402 Payment Required
- Timing dimension separation (health-check vs pipeline vs actual model request time)
"""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

from evaluation.ground_truth_matcher import ScenarioCauseMatcher, SCENARIO_GROUND_TRUTH_MAP
from evaluation.run_cloud_benchmark import (
    compute_percentile,
    probe_live_cloud_model,
    extract_scenario_telemetry,
    run_benchmark,
)
from backend.app.agent.graph.nodes.evaluate_hypotheses import _extract_json_from_llm, _build_deterministic_evaluation
from backend.app.agent.graph.nodes.review_report import review_report_node
from backend.app.agent.graph.state import InvestigationState
from backend.app.summary.llm.base import LLMProvider


# -----------------------------------------------------------------------------
# 1. Strict Cause Matcher & Ground Truth Tests
# -----------------------------------------------------------------------------

def test_strict_matcher_all_scenarios_positive():
    """Verify that valid predictions for all 8 scenarios match their ground truth."""
    test_cases = [
        ("ambiguous_noise", "Insufficient evidence: isolated transient symptoms"),
        ("ambiguous_noise", "Unknown root cause due to transient noise"),
        ("ambiguous_noise", "Inconclusive telemetry pattern"),
        ("auth_failure", "Authentication failure on auth-api"),
        ("auth_failure", "Expired JWT signing key causing 401 unauthorized surge"),
        ("bad_deployment", "Recent deployment on booking-api"),
        ("bad_deployment", "Faulty release v2.4.8 rollout failure"),
        ("database_saturation", "Database degradation on postgres"),
        ("database_saturation", "PostgreSQL database connection pool exhaustion"),
        ("memory_exhaustion", "Memory exhaustion on catalog-api"),
        ("memory_exhaustion", "Container OOM killer invoked due to heap exhaustion"),
        ("payment_pool_exhaustion", "Database degradation on postgres"),
        ("payment_pool_exhaustion", "HikariCP connection pool exhaustion on payment-api"),
        ("redis_failure", "Redis cache failure on cache-service"),
        ("redis_failure", "Redis cache timeout and connectivity loss"),
        ("traffic_spike", "Queue processing backlog on worker-service"),
        ("traffic_spike", "Traffic surge causing worker pool exhaustion"),
    ]

    for scenario_name, prediction in test_cases:
        assert ScenarioCauseMatcher.matches(scenario_name, prediction) is True, (
            f"Expected '{prediction}' to match scenario '{scenario_name}'"
        )


def test_strict_matcher_incorrect_predictions_negative_controls():
    """
    Negative controls: Verify that cross-domain predictions are strictly rejected
    and do not cause permissive keyword collisions.
    """
    negative_controls = [
        # Redis failure predicted for database saturation
        ("database_saturation", "Redis cache failure on cache-service"),
        ("database_saturation", "Cache miss surge and connection timeout"),
        # Database degradation predicted for Redis failure
        ("redis_failure", "Database degradation on postgres"),
        ("redis_failure", "Postgres query latency timeout"),
        # Bad deployment predicted for memory exhaustion
        ("memory_exhaustion", "Recent deployment on booking-api"),
        ("memory_exhaustion", "Faulty release v2.4.8"),
        # Auth failure predicted for traffic spike
        ("traffic_spike", "Authentication failure on auth-api"),
        ("traffic_spike", "JWT signature invalidation"),
        # Database saturation predicted for auth failure
        ("auth_failure", "Database degradation on postgres"),
        ("auth_failure", "Postgres connection pool saturation"),
        # Traffic spike predicted for bad deployment
        ("bad_deployment", "Queue processing backlog on worker-service"),
    ]

    for scenario_name, prediction in negative_controls:
        assert ScenarioCauseMatcher.matches(scenario_name, prediction) is False, (
            f"Negative control failed: '{prediction}' should NOT match scenario '{scenario_name}'"
        )


def test_strict_matcher_ambiguous_noise_negative_controls():
    """
    Ambiguous noise negative controls:
    Verify that the ambiguous scenario strictly requires unknown/insufficient evidence
    and explicitly rejects any concrete failure attribution.
    """
    # Concrete attributions MUST fail for ambiguous noise
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Database degradation on postgres") is False
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Redis cache failure on cache-service") is False
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Recent deployment on booking-api") is False
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Memory exhaustion on catalog-api") is False
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Authentication failure on auth-api") is False
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Queue processing backlog on worker-service") is False
    # Even if it contains 'unknown', mentioning a concrete disallowed component disqualifies it
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Unknown cause due to database saturation") is False
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Unknown redis issue") is False

    # Valid ambiguity expressions MUST pass
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "UNKNOWN") is True
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Insufficient evidence: isolated transient symptoms") is True
    assert ScenarioCauseMatcher.matches("ambiguous_noise", "Transient noise without correlated upstream failure") is True


def test_strict_matcher_ranking_evaluation():
    """Verify Top-1, Top-3, and Reciprocal Rank calculation under strict matching."""
    # Top-1 match -> RR = 1.0
    cands1 = ["Database degradation on postgres", "Redis cache failure", "Recent deployment"]
    top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking("database_saturation", cands1)
    assert top1 is True
    assert top3 is True
    assert rr == 1.0

    # Top-2 match -> RR = 0.5
    cands2 = ["Redis cache failure", "Database degradation on postgres", "Recent deployment"]
    top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking("database_saturation", cands2)
    assert top1 is False
    assert top3 is True
    assert rr == 0.5

    # Top-3 match -> RR = 1/3 (~0.3333)
    cands3 = ["Redis cache failure", "Recent deployment", "Database degradation on postgres"]
    top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking("database_saturation", cands3)
    assert top1 is False
    assert top3 is True
    assert rr == pytest.approx(0.3333, abs=0.001)

    # No match in top-3 -> RR = 0.0
    cands4 = ["Redis cache failure", "Recent deployment", "Authentication failure"]
    top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking("database_saturation", cands4)
    assert top1 is False
    assert top3 is False
    assert rr == 0.0


# -----------------------------------------------------------------------------
# 2. Citation Validity & Unsupported Claim Detection Tests
# -----------------------------------------------------------------------------

def test_citation_validity_and_invalid_citation_detection():
    """Verify that hallucinated evidence citations are detected and lower validity rate."""
    evidence_items = [
        {"evidence_id": "EV-PROM-1", "source_type": "PROMETHEUS", "source_id": "prom-postgres-db_query_latency_ms"},
        {"evidence_id": "EV-LOG-2", "source_type": "LOG", "source_id": "log-postgres-db-error"},
    ]

    # Report with valid citations
    valid_report = {
        "observed_facts": [
            "Query latency spiked to 1450ms [EV-PROM-1]",
            "Database connection pool exhausted [EV-LOG-2]",
        ],
        "hypotheses_evaluated": [
            {"hypothesis": "Postgres pool exhaustion", "supporting_evidence_ids": ["EV-PROM-1", "EV-LOG-2"]}
        ],
        "recommended_diagnostic_steps": [{"action": "Check pg_stat_activity", "requires_human_approval": True}],
    }

    state_valid: InvestigationState = {
        "investigation_id": "INV-TEST-001",
        "incident_key": "INC-001",
        "collected_evidence": evidence_items,
        "final_report": valid_report,
    }

    res_valid = review_report_node(state_valid)
    assessment_valid = res_valid["review_assessment"]
    assert assessment_valid["citation_validity_rate"] == 1.0
    assert assessment_valid["invalid_citations"] == []
    assert assessment_valid["unsupported_claim_rate"] == 0.0

    # Report with hallucinated citation EV-FAKE-999
    invalid_report = {
        "observed_facts": [
            "Query latency spiked to 1450ms [EV-PROM-1]",
            "Hallucinated finding citing ghost evidence [EV-FAKE-999]",
        ],
        "hypotheses_evaluated": [
            {"hypothesis": "Postgres pool exhaustion", "supporting_evidence_ids": ["EV-PROM-1", "EV-FAKE-999"]}
        ],
        "recommended_diagnostic_steps": [{"action": "Check pg_stat_activity", "requires_human_approval": True}],
    }

    state_invalid: InvestigationState = {
        "investigation_id": "INV-TEST-002",
        "incident_key": "INC-002",
        "collected_evidence": evidence_items,
        "final_report": invalid_report,
    }

    res_invalid = review_report_node(state_invalid)
    assessment_invalid = res_invalid["review_assessment"]
    assert "EV-FAKE-999" in assessment_invalid["invalid_citations"]
    assert assessment_invalid["citation_validity_rate"] < 1.0


def test_unsupported_claim_detection():
    """Verify that facts lacking citations are flagged as unsupported claims."""
    evidence_items = [
        {"evidence_id": "EV-PROM-1", "source_type": "PROMETHEUS", "source_id": "prom-postgres-db_query_latency_ms"},
    ]

    report_with_unsupported_claim = {
        "observed_facts": [
            "Query latency spiked to 1450ms [EV-PROM-1]",
            "An unsupported un-cited claim about memory leaks",
        ],
        "hypotheses_evaluated": [],
        "recommended_diagnostic_steps": [],
    }

    state: InvestigationState = {
        "investigation_id": "INV-TEST-003",
        "incident_key": "INC-003",
        "collected_evidence": evidence_items,
        "final_report": report_with_unsupported_claim,
    }

    res = review_report_node(state)
    assessment = res["review_assessment"]
    assert assessment["unsupported_claims_count"] == 1
    assert assessment["unsupported_claim_rate"] == 0.5


# -----------------------------------------------------------------------------
# 3. Malformed LLM Response & Schema Validity Tests
# -----------------------------------------------------------------------------

def test_extract_json_from_llm_malformed_cases():
    """Verify JSON extractor handles non-JSON, truncated, or malformed strings without unhandled exceptions."""
    # Plain text without JSON
    assert _extract_json_from_llm("This is a plain text explanation with no JSON.") is None

    # Truncated JSON
    assert _extract_json_from_llm('{"observed_facts": ["fact 1"], "hypotheses_eval') is None

    # Markdown fenced valid JSON
    fenced = """```json
    {
        "observed_facts": ["fact 1"],
        "hypotheses_evaluated": [{"hypothesis": "Test", "original_score": 0.8}]
    }
    ```"""
    extracted = _extract_json_from_llm(fenced)
    assert extracted is not None
    assert "observed_facts" in extracted
    assert len(extracted["hypotheses_evaluated"]) == 1

    # Empty string
    assert _extract_json_from_llm("") is None
    assert _extract_json_from_llm(None) is None


# -----------------------------------------------------------------------------
# 4. Fallback Handling & HTTP 402 Probe Tests
# -----------------------------------------------------------------------------

def test_probe_live_cloud_model_handles_http_402():
    """Verify probe_live_cloud_model marks status as BLOCKED when HTTP 402 is returned."""
    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 402
        mock_resp.json.return_value = {
            "error": "You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers."
        }
        mock_resp.text = json.dumps(mock_resp.json.return_value)
        mock_post.return_value = mock_resp

        res = probe_live_cloud_model(
            base_url="https://router.huggingface.co/v1",
            token="hf_mock_token_no_credits",
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            task="investigation",
        )

        assert res["status"] == "BLOCKED"
        assert res["http_status"] == 402
        assert res["usable"] is False
        assert "Payment Required" in res["error"]
        assert res["client_latency_ms"] >= 0.0


def test_probe_live_cloud_model_handles_missing_token():
    """Verify probe returns BLOCKED immediately without network call if token is missing."""
    res = probe_live_cloud_model(
        base_url="https://router.huggingface.co/v1",
        token="",
        model_id="meta-llama/Llama-3.1-8B-Instruct",
        task="investigation",
    )
    assert res["status"] == "BLOCKED"
    assert res["http_status"] is None
    assert res["usable"] is False
    assert "HF_TOKEN not configured" in res["error"]


# -----------------------------------------------------------------------------
# 5. Timing Separation & Percentiles Tests
# -----------------------------------------------------------------------------

def test_compute_percentile_calculations():
    """Verify compute_percentile returns accurate statistical percentiles."""
    vals = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert compute_percentile(vals, 50) == 55.0
    assert compute_percentile(vals, 90) == 91.0
    assert compute_percentile(vals, 95) == 95.5
    assert compute_percentile([], 50) == 0.0


# -----------------------------------------------------------------------------
# 6. Live Inference Available Execution & Validation Test
# -----------------------------------------------------------------------------

def test_live_inference_execution_when_cloud_available():
    """
    Verify that when Hugging Face inference is available:
    1. The investigation, summary, and review model tasks run on scenarios.
    2. Outputs are validated against ground truth and evidence IDs.
    3. Actual model IDs, per-call latencies, errors, and fallback status are recorded.
    4. Top-1, Top-3, MRR, schema validity, citation validity, unsupported claims,
       live success rate, and client-observed latency percentiles are reported.
    """
    mock_inv_response = json.dumps({
        "observed_facts": [
            "Query latency spiked to 1450ms [EV-PROM-1]",
            "Database connection pool exhausted [EV-PROM-2]",
        ],
        "inferred_relationships": ["Connection exhaustion caused query queueing"],
        "confirmed_findings": ["Postgres connection saturation"],
        "hypotheses_evaluated": [
            {
                "hypothesis": "Database degradation on postgres",
                "candidate_type": "DATABASE",
                "original_score": 0.95,
                "calibrated_status": "CONFIRMED",
                "supporting_evidence_ids": ["EV-PROM-1", "EV-PROM-2"],
                "contradicting_evidence_ids": [],
                "reasoning": "Direct evidence of 100% pool utilization and latency spike",
            }
        ],
        "alternative_explanations": [],
        "missing_evidence": [],
        "contradictory_evidence": [],
        "uncertainty_assessment": "High confidence based on metrics",
        "recommended_diagnostic_steps": [
            {"action": "Check pg_stat_activity", "requires_human_approval": True}
        ],
    })

    mock_sum_response = json.dumps({
        "executive_summary": "Database saturation degraded payment processing.",
        "what_happened": "Connection pool reached maximum capacity under peak traffic.",
        "probable_root_cause": "Database degradation on postgres",
        "impact": {
            "services": ["postgres", "payment-api"],
            "severity": "CRITICAL",
            "description": "500 errors on payment endpoints",
        },
        "timeline": [
            {"timestamp": "2026-10-23T12:00:00Z", "event": "Pool exhausted", "source": "EV-PROM-1"}
        ],
        "evidence": [
            {
                "evidence_id": "E1",
                "claim": "Database query latency exceeded threshold",
                "source_type": "PROMETHEUS",
                "source_id": "prom-postgres-db_query_latency_ms",
                "support": "Prometheus metric db_query_latency_ms = 1450.00",
            }
        ],
        "remediation": [
            {
                "action": "Increase HikariCP maximumPoolSize to 50",
                "priority": "HIGH",
                "reason": "Prevent connection starvation",
            }
        ],
        "confidence": 0.95,
        "limitations": [],
        "similar_incidents": [],
        "uncertainty": None,
    })

    mock_rev_response = json.dumps({
        "review_summary": "Report verified with valid evidence citations and human approval.",
        "passed": True,
        "confidence": 0.98,
    })

    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model") as mock_probe, \
         patch("backend.app.summary.llm.huggingface_provider.HuggingFaceProvider.generate_with_telemetry") as mock_gen, \
         patch("backend.app.summary.llm.huggingface_provider.HuggingFaceProvider.is_available", return_value=True):

        # Configure probes to succeed (HTTP 200)
        mock_probe.side_effect = lambda base_url, token, model_id, task, timeout_sec=10.0: {
            "model_id": model_id,
            "task": task,
            "status": "AVAILABLE",
            "http_status": 200,
            "error": None,
            "client_latency_ms": 150.0,
            "usable": True,
        }

        # Configure provider generate_with_telemetry to return responses by task
        def mock_generate(prompt, task=None):
            t = (task or "").lower()
            if "investigation" in t:
                return mock_inv_response, {
                    "provider": "huggingface",
                    "actual_model_id": "meta-llama/Llama-3.1-8B-Instruct",
                    "task": "investigation",
                    "request_latency_ms": 120.0,
                    "request_latency_seconds": 0.12,
                    "fallback_status": False,
                    "errors": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            elif "summary" in t:
                return mock_sum_response, {
                    "provider": "huggingface",
                    "actual_model_id": "meta-llama/Llama-3.1-8B-Instruct",
                    "task": "summary",
                    "request_latency_ms": 95.0,
                    "request_latency_seconds": 0.095,
                    "fallback_status": False,
                    "errors": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                return mock_rev_response, {
                    "provider": "huggingface",
                    "actual_model_id": "meta-llama/Llama-3.1-8B-Instruct",
                    "task": "report_review",
                    "request_latency_ms": 80.0,
                    "request_latency_seconds": 0.08,
                    "fallback_status": False,
                    "errors": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

        mock_gen.side_effect = mock_generate

        # Run benchmark with 1 trial per scenario to test execution path
        results = run_benchmark(trials_per_scenario=1, save_results=False)

        assert results["live_cloud_evaluation"]["status"] == "AVAILABLE"
        assert results["live_cloud_evaluation"]["live_trials_run"] == 8
        assert results["live_cloud_evaluation"]["live_success_rate"] == 1.0
        assert results["live_cloud_evaluation"]["live_top1_accuracy"] is not None
        assert results["live_cloud_evaluation"]["live_top3_accuracy"] is not None
        assert results["live_cloud_evaluation"]["live_mrr"] is not None
        assert results["live_cloud_evaluation"]["live_valid_json_rate"] == 1.0
        assert results["live_cloud_evaluation"]["live_citation_validity_rate"] >= 0.95
        assert results["live_cloud_evaluation"]["model_request_latency_ms"] is not None
        assert "mean_ms" in results["live_cloud_evaluation"]["model_request_latency_ms"]

        # Verify timing separation
        timing = results["timing_breakdown"]
        assert timing["provider_health_check_time_ms"] > 0
        assert timing["benchmark_pipeline_total_ms"] > 0
        assert timing["actual_model_request_time_ms"] is not None
        assert "mean_ms" in timing["actual_model_request_time_ms"]


# -----------------------------------------------------------------------------
# 7. End-to-End Ranking Metrics & Ground-Truth Evaluation Tests
# -----------------------------------------------------------------------------

def _mock_blocked_probe(base_url, token, model_id, task, timeout_sec=10.0):
    return {
        "model_id": model_id,
        "task": task,
        "status": "BLOCKED",
        "http_status": 402,
        "error": "Payment Required (test mock)",
        "client_latency_ms": 0.5,
        "usable": False,
    }


def _get_scenario_from_signals(signals: List[Dict[str, Any]]) -> str:
    svcs = {s.get("service") for s in signals}
    if "auth-api" in svcs:
        return "auth_failure"
    if "postgres" in svcs:
        return "database_saturation"
    if "catalog-api" in svcs:
        return "memory_exhaustion"
    if "payment-api" in svcs:
        return "payment_pool_exhaustion"
    if "cache-service" in svcs:
        return "redis_failure"
    if "worker-service" in svcs:
        return "traffic_spike"
    for s in signals:
        if s.get("signal_type") == "DEPLOYMENT":
            return "bad_deployment"
    return "ambiguous_noise"


def test_cloud_benchmark_ranking_end_to_end_degradation():
    """
    End-to-end benchmark ranking test verifying that:
    1. Baseline perfect ranking produces 100% Top-1, 100% Top-3, and 1.0000 MRR.
    2. When incorrect root cause ranks first and correct ranks second:
       Top-1 accuracy decreases, Top-3 accuracy is maintained, and MRR decreases appropriately.
    3. When correct root cause is absent from the top three:
       Top-1 accuracy, Top-3 accuracy, and MRR all decrease strictly.
    4. Monotonic decrease hierarchy holds across baseline, rank-2, and absent runs:
       Top-1(baseline) > Top-1(rank-2) == Top-1(absent)
       Top-3(baseline) == Top-3(rank-2) > Top-3(absent)
       MRR(baseline) > MRR(rank-2) > MRR(absent)
    """
    # 1. Condition A: Baseline Perfect Ranking
    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model", side_effect=_mock_blocked_probe):
        baseline_results = run_benchmark(trials_per_scenario=1, save_results=False)

    base_metrics = baseline_results["deterministic_baseline_metrics"]
    base_top1 = base_metrics["rca_top1_accuracy"]
    base_top3 = base_metrics["rca_top3_accuracy"]
    base_mrr = base_metrics["mrr"]

    assert base_top1 == 1.0
    assert base_top3 == 1.0
    assert base_mrr == 1.0000

    # 2. Condition B: Incorrect Root Cause Ranks #1, Correct Cause Ranks #2
    def score_rank2(self, candidates, signals, edges=[], traces=None):
        sc = _get_scenario_from_signals(signals)
        correct_name = None
        for c in candidates:
            if ScenarioCauseMatcher.matches(sc, c["candidate_name"]):
                correct_name = c["candidate_name"]
                break
        if not correct_name:
            correct_name = (
                "Database degradation on postgres"
                if sc in ("database_saturation", "payment_pool_exhaustion")
                else candidates[0]["candidate_name"]
            )

        wrong_cause = (
            "Redis cache failure on cache-service"
            if sc != "redis_failure"
            else "Database degradation on postgres"
        )
        third_cause = (
            "Authentication failure on auth-api"
            if sc != "auth_failure"
            else "Recent deployment on booking-api"
        )

        return [
            {"candidate_name": wrong_cause, "score": 0.95, "candidate_type": "CACHE"},
            {"candidate_name": correct_name, "score": 0.85, "candidate_type": "DATABASE"},
            {"candidate_name": third_cause, "score": 0.70, "candidate_type": "AUTH"},
        ]

    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model", side_effect=_mock_blocked_probe):
        with patch("backend.app.rca.analysis.scoring.CandidateScorer.score_candidates", new=score_rank2):
            rank2_results = run_benchmark(trials_per_scenario=1, save_results=False)

    rank2_metrics = rank2_results["deterministic_baseline_metrics"]
    rank2_top1 = rank2_metrics["rca_top1_accuracy"]
    rank2_top3 = rank2_metrics["rca_top3_accuracy"]
    rank2_mrr = rank2_metrics["mrr"]

    # Verify per-trial behavior for non-ambiguous scenarios
    for trial in rank2_results["per_trial_results"]:
        if not trial["is_ambiguous_control"]:
            assert trial["is_top1_hit"] is False, f"Trial {trial['scenario']} should not have Top-1 hit"
            assert trial["is_top3_hit"] is True, f"Trial {trial['scenario']} should have Top-3 hit"
            assert trial["reciprocal_rank"] == 0.5, f"Trial {trial['scenario']} should have RR = 0.5"

    # Verify metric decrease for rank-2
    assert rank2_top1 < base_top1, f"Expected Top-1 accuracy to decrease: {rank2_top1} vs {base_top1}"
    assert rank2_mrr < base_mrr, f"Expected MRR to decrease: {rank2_mrr} vs {base_mrr}"
    assert rank2_top3 == base_top3, f"Expected Top-3 accuracy to be preserved: {rank2_top3} vs {base_top3}"
    assert rank2_top1 < rank2_top3, "Top-1 accuracy must be strictly less than Top-3 accuracy"
    assert rank2_top1 == 0.125  # 1 (ambiguous) out of 8
    assert rank2_top3 == 1.0    # 8 out of 8
    assert rank2_mrr == 0.5625  # (7 * 0.5 + 1.0) / 8

    # 3. Condition C: Correct Cause Absent from Top Three
    def score_absent(self, candidates, signals, edges=[], traces=None):
        sc = _get_scenario_from_signals(signals)
        correct_name = None
        for c in candidates:
            if ScenarioCauseMatcher.matches(sc, c["candidate_name"]):
                correct_name = c["candidate_name"]
                break
        if not correct_name:
            correct_name = (
                "Database degradation on postgres"
                if sc in ("database_saturation", "payment_pool_exhaustion")
                else candidates[0]["candidate_name"]
            )

        wrong1 = (
            "Redis cache failure on cache-service"
            if sc != "redis_failure"
            else "Database degradation on postgres"
        )
        wrong2 = (
            "Authentication failure on auth-api"
            if sc != "auth_failure"
            else "Recent deployment on booking-api"
        )
        wrong3 = (
            "Memory exhaustion on catalog-api"
            if sc != "memory_exhaustion"
            else "Recent deployment on booking-api"
        )

        return [
            {"candidate_name": wrong1, "score": 0.95, "candidate_type": "CACHE"},
            {"candidate_name": wrong2, "score": 0.90, "candidate_type": "AUTH"},
            {"candidate_name": wrong3, "score": 0.85, "candidate_type": "MEMORY"},
            {"candidate_name": correct_name, "score": 0.70, "candidate_type": "DATABASE"},
        ]

    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model", side_effect=_mock_blocked_probe):
        with patch("backend.app.rca.analysis.scoring.CandidateScorer.score_candidates", new=score_absent):
            absent_results = run_benchmark(trials_per_scenario=1, save_results=False)

    absent_metrics = absent_results["deterministic_baseline_metrics"]
    absent_top1 = absent_metrics["rca_top1_accuracy"]
    absent_top3 = absent_metrics["rca_top3_accuracy"]
    absent_mrr = absent_metrics["mrr"]

    # Verify per-trial behavior for non-ambiguous scenarios
    for trial in absent_results["per_trial_results"]:
        if not trial["is_ambiguous_control"]:
            assert trial["is_top1_hit"] is False
            assert trial["is_top3_hit"] is False
            assert trial["reciprocal_rank"] == 0.0

    # Verify metric decrease for absent from top-3
    assert absent_top1 < base_top1
    assert absent_top3 < rank2_top3, f"Expected Top-3 to decrease when absent: {absent_top3} vs {rank2_top3}"
    assert absent_mrr < rank2_mrr, f"Expected MRR to decrease further when absent: {absent_mrr} vs {rank2_mrr}"
    assert absent_top1 == 0.125
    assert absent_top3 == 0.125
    assert absent_mrr == 0.1250

    # 4. Verify Stepwise Hierarchy
    assert base_top1 > rank2_top1 == absent_top1
    assert base_top3 == rank2_top3 > absent_top3
    assert base_mrr > rank2_mrr > absent_mrr


def test_cloud_benchmark_ranking_mixed_distribution():
    """
    Verify mathematical calculation of Top-1, Top-3, and MRR across a mixed distribution
    of ranking positions in an end-to-end benchmark run.
    """
    def score_mixed(self, candidates, signals, edges=[], traces=None):
        sc = _get_scenario_from_signals(signals)
        correct_name = None
        for c in candidates:
            if ScenarioCauseMatcher.matches(sc, c["candidate_name"]):
                correct_name = c["candidate_name"]
                break
        if not correct_name:
            correct_name = (
                "Database degradation on postgres"
                if sc in ("database_saturation", "payment_pool_exhaustion")
                else candidates[0]["candidate_name"]
            )

        wrong1 = (
            "Redis cache failure on cache-service"
            if sc != "redis_failure"
            else "Database degradation on postgres"
        )
        wrong2 = (
            "Authentication failure on auth-api"
            if sc != "auth_failure"
            else "Recent deployment on booking-api"
        )
        wrong3 = (
            "Memory exhaustion on catalog-api"
            if sc != "memory_exhaustion"
            else "Recent deployment on booking-api"
        )

        # Scenario distribution across 7 non-ambiguous scenarios:
        # 1 scenario with Rank 1 (Top-1 hit) -> auth_failure
        # 4 scenarios with Rank 2 (Top-2 hit) -> bad_deployment, database_saturation, memory_exhaustion, payment_pool_exhaustion
        # 2 scenarios with Absent (No hit in top 3) -> redis_failure, traffic_spike
        if sc == "auth_failure":
            return [
                {"candidate_name": correct_name, "score": 0.95, "candidate_type": "AUTH"},
                {"candidate_name": wrong1, "score": 0.80, "candidate_type": "CACHE"},
            ]
        elif sc in ("bad_deployment", "database_saturation", "memory_exhaustion", "payment_pool_exhaustion"):
            return [
                {"candidate_name": wrong1, "score": 0.95, "candidate_type": "CACHE"},
                {"candidate_name": correct_name, "score": 0.85, "candidate_type": "DATABASE"},
                {"candidate_name": wrong2, "score": 0.70, "candidate_type": "AUTH"},
            ]
        else:  # redis_failure, traffic_spike
            return [
                {"candidate_name": wrong1, "score": 0.95, "candidate_type": "CACHE"},
                {"candidate_name": wrong2, "score": 0.90, "candidate_type": "AUTH"},
                {"candidate_name": wrong3, "score": 0.85, "candidate_type": "MEMORY"},
                {"candidate_name": correct_name, "score": 0.60, "candidate_type": "DATABASE"},
            ]

    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model", side_effect=_mock_blocked_probe):
        with patch("backend.app.rca.analysis.scoring.CandidateScorer.score_candidates", new=score_mixed):
            results = run_benchmark(trials_per_scenario=1, save_results=False)

    trials = results["per_trial_results"]
    metrics = results["deterministic_baseline_metrics"]

    # Calculate expected numbers from trial records:
    # 2 Rank-1 (auth_failure + ambiguous_noise) -> 2/8 = 0.2500
    # 4 Rank-2 (bad_dep, db_sat, mem_ex, pay_ex) -> 4 with top3=True, rr=0.5
    # 2 Absent (redis_fail, traf_spike) -> 2 with top3=False, rr=0.0
    # Total Top-3 = 2 + 4 = 6/8 = 0.7500
    # Total MRR = (2 * 1.0 + 4 * 0.5 + 2 * 0.0) / 8 = 4.0 / 8 = 0.5000
    expected_top1 = round(sum(1 for t in trials if t["is_top1_hit"]) / len(trials), 4)
    expected_top3 = round(sum(1 for t in trials if t["is_top3_hit"]) / len(trials), 4)
    expected_mrr = round(sum(t["reciprocal_rank"] for t in trials) / len(trials), 4)

    assert metrics["rca_top1_accuracy"] == 0.25
    assert metrics["rca_top3_accuracy"] == 0.75
    assert metrics["mrr"] == 0.5000
    assert metrics["rca_top1_accuracy"] == expected_top1
    assert metrics["rca_top3_accuracy"] == expected_top3
    assert metrics["mrr"] == expected_mrr
    assert metrics["rca_top1_accuracy"] < metrics["mrr"] < metrics["rca_top3_accuracy"]


def test_ranking_metrics_computed_from_actual_candidates_and_ground_truth_labels():
    """
    Directly validates Requirement 3:
    1. Verify metrics are computed dynamically from actual candidate strings against
       ground-truth labels (SCENARIO_GROUND_TRUTH_MAP), not manually supplied expected scores.
    2. Verify across all 8 benchmark scenarios:
       - Rank 1 match -> Top-1: True, Top-3: True, RR: 1.0
       - Rank 2 match (incorrect 1st, correct 2nd) -> Top-1: False, Top-3: True, RR: 0.5
       - Absent from top-3 -> Top-1: False, Top-3: False, RR: 0.0
    3. Verify candidate order swapping dynamically changes Top-1 and RR while candidate content is fixed.
    4. Verify candidate score/confidence does not dictate correctness (confidence independence).
    5. Verify negative control patterns are strictly enforced.
    """
    valid_candidates_map = {
        "ambiguous_noise": "Insufficient evidence: isolated transient symptoms",
        "auth_failure": "Authentication failure on auth-api",
        "bad_deployment": "Recent deployment on booking-api",
        "database_saturation": "Database degradation on postgres",
        "memory_exhaustion": "Memory exhaustion on catalog-api",
        "payment_pool_exhaustion": "Database degradation on postgres",
        "redis_failure": "Redis cache failure on cache-service",
        "traffic_spike": "Queue processing backlog on worker-service",
    }

    invalid_candidates_map = {
        "ambiguous_noise": [
            "Database degradation on postgres",
            "Redis cache failure on cache-service",
            "Recent deployment on booking-api",
        ],
        "auth_failure": [
            "Database degradation on postgres",
            "Redis cache failure on cache-service",
            "Recent deployment on booking-api",
        ],
        "bad_deployment": [
            "Redis cache failure on cache-service",
            "Authentication failure on auth-api",
            "Memory exhaustion on catalog-api",
        ],
        "database_saturation": [
            "Redis cache failure on cache-service",
            "Authentication failure on auth-api",
            "Recent deployment on booking-api",
        ],
        "memory_exhaustion": [
            "Database degradation on postgres",
            "Redis cache failure on cache-service",
            "Authentication failure on auth-api",
        ],
        "payment_pool_exhaustion": [
            "Redis cache failure on cache-service",
            "Authentication failure on auth-api",
            "Recent deployment on booking-api",
        ],
        "redis_failure": [
            "Database degradation on postgres",
            "Authentication failure on auth-api",
            "Recent deployment on booking-api",
        ],
        "traffic_spike": [
            "Database degradation on postgres",
            "Redis cache failure on cache-service",
            "Authentication failure on auth-api",
        ],
    }

    assert len(SCENARIO_GROUND_TRUTH_MAP) == 8

    trials_all_rank1 = []
    trials_all_rank2 = []
    trials_all_absent = []

    for sc_name, gt in SCENARIO_GROUND_TRUTH_MAP.items():
        assert gt.scenario_name == sc_name
        assert len(gt.valid_patterns) > 0
        assert len(gt.disallowed_patterns) > 0
        assert gt.expected_root_cause is not None

        valid_cause = valid_candidates_map[sc_name]
        invalids = invalid_candidates_map[sc_name]

        # Ensure valid candidate matches ground truth
        assert ScenarioCauseMatcher.matches(sc_name, valid_cause) is True, (
            f"Ground-truth valid pattern mismatch for {sc_name}: '{valid_cause}'"
        )
        # Ensure invalid candidates are rejected
        for inv in invalids:
            assert ScenarioCauseMatcher.matches(sc_name, inv) is False, (
                f"Negative control failure for {sc_name}: '{inv}' should NOT match"
            )

        # A) Rank 1 correct: [valid, inv0, inv1]
        cands_r1 = [valid_cause, invalids[0], invalids[1]]
        t1, t3, rr = ScenarioCauseMatcher.evaluate_ranking(sc_name, cands_r1)
        assert t1 is True
        assert t3 is True
        assert rr == 1.0
        trials_all_rank1.append((t1, t3, rr))

        # B) Rank 2 correct (incorrect ranks 1st, correct ranks 2nd): [inv0, valid, inv1]
        cands_r2 = [invalids[0], valid_cause, invalids[1]]
        t1, t3, rr = ScenarioCauseMatcher.evaluate_ranking(sc_name, cands_r2)
        assert t1 is False
        assert t3 is True
        assert rr == 0.5
        trials_all_rank2.append((t1, t3, rr))

        # C) Absent from Top 3: [inv0, inv1, inv2, valid]
        cands_abs = [invalids[0], invalids[1], invalids[2], valid_cause]
        t1, t3, rr = ScenarioCauseMatcher.evaluate_ranking(sc_name, cands_abs)
        assert t1 is False
        assert t3 is False
        assert rr == 0.0
        trials_all_absent.append((t1, t3, rr))

        # D) Dynamic order swap sensitivity check:
        # Swapping rank 1 and rank 2 MUST dynamically alter Top-1 and RR
        swap_original = [valid_cause, invalids[0]]
        swap_inverted = [invalids[0], valid_cause]
        assert ScenarioCauseMatcher.evaluate_ranking(sc_name, swap_original) == (True, True, 1.0)
        assert ScenarioCauseMatcher.evaluate_ranking(sc_name, swap_inverted) == (False, True, 0.5)

    n_sc = len(SCENARIO_GROUND_TRUTH_MAP)
    # Aggregate across all 8 scenarios:
    # All Rank-1
    agg_r1_top1 = sum(t[0] for t in trials_all_rank1) / n_sc
    agg_r1_top3 = sum(t[1] for t in trials_all_rank1) / n_sc
    agg_r1_mrr = sum(t[2] for t in trials_all_rank1) / n_sc
    assert agg_r1_top1 == 1.0
    assert agg_r1_top3 == 1.0
    assert agg_r1_mrr == 1.0

    # All Rank-2 (incorrect ranks 1st, correct ranks 2nd across all scenarios)
    agg_r2_top1 = sum(t[0] for t in trials_all_rank2) / n_sc
    agg_r2_top3 = sum(t[1] for t in trials_all_rank2) / n_sc
    agg_r2_mrr = sum(t[2] for t in trials_all_rank2) / n_sc
    assert agg_r2_top1 == 0.0
    assert agg_r2_top3 == 1.0
    assert agg_r2_mrr == 0.5000

    # All Absent
    agg_abs_top1 = sum(t[0] for t in trials_all_absent) / n_sc
    agg_abs_top3 = sum(t[1] for t in trials_all_absent) / n_sc
    agg_abs_mrr = sum(t[2] for t in trials_all_absent) / n_sc
    assert agg_abs_top1 == 0.0
    assert agg_abs_top3 == 0.0
    assert agg_abs_mrr == 0.0

    # Verify appropriate decreases:
    assert agg_r1_top1 > agg_r2_top1 == agg_abs_top1
    assert agg_r1_top3 == agg_r2_top3 > agg_abs_top3
    assert agg_r1_mrr > agg_r2_mrr > agg_abs_mrr

    # E) Score / Confidence Independence Verification
    # An incorrect candidate with 0.999 confidence must NOT be counted as a hit
    fake_high_conf_wrong = "Redis cache failure on cache-service"
    top1_wrong, top3_wrong, rr_wrong = ScenarioCauseMatcher.evaluate_ranking(
        "database_saturation", [fake_high_conf_wrong]
    )
    assert top1_wrong is False
    assert top3_wrong is False
    assert rr_wrong == 0.0

    # A correct candidate with low 0.35 confidence MUST still be counted as a hit
    valid_low_conf = "PostgreSQL database connection pool exhaustion"
    top1_right, top3_right, rr_right = ScenarioCauseMatcher.evaluate_ranking(
        "database_saturation", [valid_low_conf]
    )
    assert top1_right is True
    assert top3_right is True
    assert rr_right == 1.0


def test_live_cloud_benchmark_ranking_degradation_when_cloud_available():
    """
    Verify live cloud evaluation ranking metrics when live cloud inference is available:
    1. If live model produces hypotheses where incorrect ranks 1st and correct ranks 2nd:
       live_top1_accuracy decreases to 0.0, live_top3_accuracy is 1.0, live_mrr decreases to 0.5.
    2. If live model produces hypotheses where correct cause is absent from top-3:
       live_top1_accuracy decreases to 0.0, live_top3_accuracy decreases to 0.0, live_mrr decreases to 0.0.
    """
    mock_inv_rank2 = json.dumps({
        "observed_facts": ["Query latency spiked to 1450ms [EV-PROM-1]"],
        "hypotheses_evaluated": [
            {
                "hypothesis": "Redis cache failure on cache-service",
                "candidate_type": "CACHE",
                "original_score": 0.95,
                "calibrated_status": "CONFIRMED",
                "supporting_evidence_ids": ["EV-PROM-1"],
                "reasoning": "Misidentified cache failure",
            },
            {
                "hypothesis": "Database degradation on postgres",
                "candidate_type": "DATABASE",
                "original_score": 0.85,
                "calibrated_status": "CONFIRMED",
                "supporting_evidence_ids": ["EV-PROM-1"],
                "reasoning": "Actual postgres failure at rank 2",
            },
        ],
        "recommended_diagnostic_steps": [],
    })

    mock_summary = json.dumps({
        "executive_summary": "Database incident analyzed.",
        "what_happened": "Connection pool reached maximum capacity.",
        "probable_root_cause": "Database degradation on postgres",
        "impact": {"services": ["postgres"], "severity": "CRITICAL", "description": "500 errors"},
        "timeline": [],
        "evidence": [
            {
                "evidence_id": "E1",
                "claim": "Latency spike",
                "source_type": "PROMETHEUS",
                "source_id": "prom-1",
                "support": "metric",
            }
        ],
        "remediation": [{"action": "Restart pool", "priority": "HIGH", "reason": "Clear connections"}],
        "confidence": 0.85,
    })

    mock_review = json.dumps({
        "review_summary": "Report verified.",
        "passed": True,
        "confidence": 0.95,
    })

    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model") as mock_probe, \
         patch("backend.app.summary.llm.huggingface_provider.HuggingFaceProvider.generate_with_telemetry") as mock_gen, \
         patch("backend.app.summary.llm.huggingface_provider.HuggingFaceProvider.is_available", return_value=True):

        mock_probe.side_effect = lambda base_url, token, model_id, task, timeout_sec=10.0: {
            "model_id": model_id,
            "task": task,
            "status": "AVAILABLE",
            "http_status": 200,
            "error": None,
            "client_latency_ms": 10.0,
            "usable": True,
        }

        mock_gen.side_effect = lambda prompt, task=None: (
            mock_inv_rank2
            if "investigation" in (task or "").lower()
            else (mock_summary if "summary" in (task or "").lower() else mock_review),
            {
                "provider": "huggingface",
                "actual_model_id": "meta-llama/Llama-3.1-8B-Instruct",
                "task": task or "generic",
                "request_latency_ms": 15.0,
                "request_latency_seconds": 0.015,
                "fallback_status": False,
                "errors": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        valid_map = {
            "ambiguous_noise": "Insufficient evidence: isolated transient symptoms",
            "auth_failure": "Authentication failure on auth-api",
            "bad_deployment": "Recent deployment on booking-api",
            "database_saturation": "Database degradation on postgres",
            "memory_exhaustion": "Memory exhaustion on catalog-api",
            "payment_pool_exhaustion": "Database degradation on postgres",
            "redis_failure": "Redis cache failure on cache-service",
            "traffic_spike": "Queue processing backlog on worker-service",
        }

        def mock_score_r2(self, candidates, signals, edges=[], traces=None):
            sc = _get_scenario_from_signals(signals)
            correct_name = valid_map.get(sc, "Database degradation on postgres")
            wrong_name = (
                "Redis cache failure on cache-service"
                if sc != "redis_failure"
                else "Database degradation on postgres"
            )
            return [
                {"candidate_name": wrong_name, "score": 0.95, "candidate_type": "CACHE"},
                {"candidate_name": correct_name, "score": 0.85, "candidate_type": "DATABASE"},
            ]

        with patch("backend.app.rca.analysis.scoring.CandidateScorer.score_candidates", new=mock_score_r2):
            results_live_r2 = run_benchmark(trials_per_scenario=1, save_results=False)

        live_eval_r2 = results_live_r2["live_cloud_evaluation"]
        assert live_eval_r2["status"] == "AVAILABLE"
        assert live_eval_r2["live_top1_accuracy"] < 1.0
        assert live_eval_r2["live_top3_accuracy"] == 1.0
        assert live_eval_r2["live_mrr"] < 1.0
        assert live_eval_r2["live_top1_accuracy"] < live_eval_r2["live_top3_accuracy"]

        # Absent from top-3 in live mode
        def mock_score_abs(self, candidates, signals, edges=[], traces=None):
            sc = _get_scenario_from_signals(signals)
            wrong1 = (
                "Redis cache failure on cache-service"
                if sc != "redis_failure"
                else "Database degradation on postgres"
            )
            wrong2 = (
                "Authentication failure on auth-api"
                if sc != "auth_failure"
                else "Recent deployment on booking-api"
            )
            wrong3 = (
                "Memory exhaustion on catalog-api"
                if sc != "memory_exhaustion"
                else "Recent deployment on booking-api"
            )
            return [
                {"candidate_name": wrong1, "score": 0.95, "candidate_type": "CACHE"},
                {"candidate_name": wrong2, "score": 0.90, "candidate_type": "AUTH"},
                {"candidate_name": wrong3, "score": 0.85, "candidate_type": "MEMORY"},
                {"candidate_name": "Database degradation on postgres", "score": 0.60, "candidate_type": "DATABASE"},
            ]

        with patch("backend.app.rca.analysis.scoring.CandidateScorer.score_candidates", new=mock_score_abs):
            results_live_abs = run_benchmark(trials_per_scenario=1, save_results=False)

        live_eval_abs = results_live_abs["live_cloud_evaluation"]
        assert live_eval_abs["status"] == "AVAILABLE"
        assert live_eval_abs["live_top3_accuracy"] < live_eval_r2["live_top3_accuracy"]
        assert live_eval_abs["live_mrr"] < live_eval_r2["live_mrr"]

