"""
End-to-End Tests for Vermithor Cloud Benchmark Ranking Metrics.

Validates:
1. Scenario candidate rankings where incorrect root cause ranks first,
   correct cause ranks second, and correct cause is absent from top three.
2. Top-1 accuracy, Top-3 accuracy, and Mean Reciprocal Rank (MRR) decrease appropriately.
3. Verification that ranking metrics are computed directly from actual candidate predictions
   and ground-truth labels rather than manually supplied or hardcoded expected scores.
"""

from typing import Any, Dict, List
from unittest.mock import patch
import pytest

from evaluation.ground_truth_matcher import ScenarioCauseMatcher, SCENARIO_GROUND_TRUTH_MAP
from evaluation.run_cloud_benchmark import run_benchmark


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


def test_e2e_cloud_benchmark_ranking_metrics_degradation():
    """
    End-to-end verification across baseline, rank-2, and absent runs:
    - Baseline: 100% Top-1, 100% Top-3, 1.0000 MRR
    - Rank 2 (incorrect #1, correct #2): Top-1 drops, Top-3 preserved, MRR drops
    - Absent from Top 3: Top-1, Top-3, and MRR all decrease strictly
    """
    # 1. Baseline Perfect Run
    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model", side_effect=_mock_blocked_probe):
        baseline_res = run_benchmark(trials_per_scenario=1, save_results=False)

    base_m = baseline_res["deterministic_baseline_metrics"]
    assert base_m["rca_top1_accuracy"] == 1.0
    assert base_m["rca_top3_accuracy"] == 1.0
    assert base_m["mrr"] == 1.0000

    # 2. Incorrect ranks #1, correct ranks #2
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

        wrong = (
            "Redis cache failure on cache-service"
            if sc != "redis_failure"
            else "Database degradation on postgres"
        )
        third = (
            "Authentication failure on auth-api"
            if sc != "auth_failure"
            else "Recent deployment on booking-api"
        )

        return [
            {"candidate_name": wrong, "score": 0.95, "candidate_type": "CACHE"},
            {"candidate_name": correct_name, "score": 0.85, "candidate_type": "DATABASE"},
            {"candidate_name": third, "score": 0.70, "candidate_type": "AUTH"},
        ]

    with patch("evaluation.run_cloud_benchmark.probe_live_cloud_model", side_effect=_mock_blocked_probe):
        with patch("backend.app.rca.analysis.scoring.CandidateScorer.score_candidates", new=score_rank2):
            rank2_res = run_benchmark(trials_per_scenario=1, save_results=False)

    rank2_m = rank2_res["deterministic_baseline_metrics"]

    # Verify per-trial behavior for non-ambiguous scenarios
    for trial in rank2_res["per_trial_results"]:
        if not trial["is_ambiguous_control"]:
            assert trial["is_top1_hit"] is False
            assert trial["is_top3_hit"] is True
            assert trial["reciprocal_rank"] == 0.5

    # Top-1 decreased, MRR decreased, Top-3 preserved
    assert rank2_m["rca_top1_accuracy"] < base_m["rca_top1_accuracy"]
    assert rank2_m["mrr"] < base_m["mrr"]
    assert rank2_m["rca_top3_accuracy"] == base_m["rca_top3_accuracy"]
    assert rank2_m["rca_top1_accuracy"] < rank2_m["rca_top3_accuracy"]

    # 3. Correct cause absent from top 3
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
            absent_res = run_benchmark(trials_per_scenario=1, save_results=False)

    absent_m = absent_res["deterministic_baseline_metrics"]

    # Verify per-trial behavior for non-ambiguous scenarios
    for trial in absent_res["per_trial_results"]:
        if not trial["is_ambiguous_control"]:
            assert trial["is_top1_hit"] is False
            assert trial["is_top3_hit"] is False
            assert trial["reciprocal_rank"] == 0.0

    # Top-1, Top-3, and MRR all decrease strictly
    assert absent_m["rca_top1_accuracy"] < base_m["rca_top1_accuracy"]
    assert absent_m["rca_top3_accuracy"] < rank2_m["rca_top3_accuracy"]
    assert absent_m["mrr"] < rank2_m["mrr"]

    # Stepwise hierarchy verification
    assert base_m["rca_top1_accuracy"] > rank2_m["rca_top1_accuracy"] == absent_m["rca_top1_accuracy"]
    assert base_m["rca_top3_accuracy"] == rank2_m["rca_top3_accuracy"] > absent_m["rca_top3_accuracy"]
    assert base_m["mrr"] > rank2_m["mrr"] > absent_m["mrr"]


def test_e2e_ranking_metrics_derived_from_actual_candidates_and_ground_truth():
    """
    Validates Requirement 3: metrics are computed from actual ranked candidates
    and ground-truth labels from SCENARIO_GROUND_TRUTH_MAP, not manually supplied expected scores.
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

    negative_control_map = {
        "ambiguous_noise": "Database degradation on postgres",
        "auth_failure": "Database degradation on postgres",
        "bad_deployment": "Redis cache failure on cache-service",
        "database_saturation": "Redis cache failure on cache-service",
        "memory_exhaustion": "Database degradation on postgres",
        "payment_pool_exhaustion": "Redis cache failure on cache-service",
        "redis_failure": "Database degradation on postgres",
        "traffic_spike": "Database degradation on postgres",
    }

    for sc_name in SCENARIO_GROUND_TRUTH_MAP:
        gt = ScenarioCauseMatcher.get_ground_truth(sc_name)
        assert gt is not None

        valid = valid_candidates_map[sc_name]
        wrong = negative_control_map[sc_name]

        # 1. Correct candidate ranks first -> Top-1: True, Top-3: True, RR: 1.0
        top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking(sc_name, [valid, wrong])
        assert top1 is True
        assert top3 is True
        assert rr == 1.0

        # 2. Swapping positions: Incorrect candidate ranks first, correct ranks second
        # Dynamically alters Top-1 and RR
        top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking(sc_name, [wrong, valid])
        assert top1 is False
        assert top3 is True
        assert rr == 0.5

        # 3. Correct candidate absent from top three
        top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking(sc_name, [wrong, "Other wrong", "Third wrong", valid])
        assert top1 is False
        assert top3 is False
        assert rr == 0.0

        # 4. Correct candidate not present at all
        top1, top3, rr = ScenarioCauseMatcher.evaluate_ranking(sc_name, [wrong, "Other wrong"])
        assert top1 is False
        assert top3 is False
        assert rr == 0.0
