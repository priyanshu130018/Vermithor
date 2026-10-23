"""
Unit tests for Vermithor Cloud Multi-Model Benchmark.
Validates:
- Explicit scenario-to-cause mappings & strict ground-truth matching
- Negative controls across cross-domain failures
- Ambiguous noise controls & rejection of concrete attributions
- Ranking evaluation (Top-1, Top-3, MRR)
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
        results = run_benchmark(trials_per_scenario=1)

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
