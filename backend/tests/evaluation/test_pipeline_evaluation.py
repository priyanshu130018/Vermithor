import json
import os
import pytest
from evaluation.evaluator import IncidentEvaluator


@pytest.fixture(scope="module")
def evaluator_instance():
    return IncidentEvaluator()


def test_evaluation_benchmark_runs_all_scenarios(evaluator_instance):
    """Verifies that the evaluator executes all 7 scenarios and produces >85% Top-1 accuracy and 100% Top-3 accuracy."""
    summary = evaluator_instance.run_benchmark()

    assert summary["total_scenarios_evaluated"] == 7
    metrics = summary["overall_metrics"]
    assert metrics["rca_top_1_accuracy"] >= 0.85
    assert metrics["rca_top_3_accuracy"] == 1.0
    assert metrics["rca_mean_reciprocal_rank"] >= 0.90
    assert metrics["anomaly_detection_f1"] == 1.0
    assert metrics["llm_json_validity_rate"] == 1.0
    assert metrics["unknown_scenario_handling_pass"] is True


def test_evaluation_unknown_ambiguity_preservation(evaluator_instance):
    """Verifies that the ambiguous scenario strictly preserves UNKNOWN and avoids confident hallucinations."""
    scenarios = evaluator_instance.load_all_scenarios()
    ambiguous = next((s for s in scenarios if s.get("name") == "ambiguous_noise"), None)
    assert ambiguous is not None

    res = evaluator_instance.evaluate_scenario(ambiguous)
    rca = res["rca_evaluation"]
    llm = res["llm_evaluation"]

    assert rca["predicted_root_cause"] == "UNKNOWN"
    assert rca["confidence"] <= 0.40
    assert rca["top_1_correct"] is True
    assert llm["unknown_preserved"] is True
    assert "Insufficient evidence" in llm["aligned_root_cause"]


def test_evaluation_artifacts_generated():
    """Verifies latest.json and report.md exist, are non-empty, and conform to schema."""
    latest_path = os.path.join("evaluation", "results", "latest.json")
    report_path = os.path.join("evaluation", "report.md")

    assert os.path.exists(latest_path), "evaluation/results/latest.json was not created"
    assert os.path.exists(report_path), "evaluation/report.md was not created"

    with open(latest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "run_timestamp" in data
        assert "overall_metrics" in data
        assert "scenarios" in data
        assert len(data["scenarios"]) == 7

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "# Vermithor — Intelligence Pipeline Benchmark & Evaluation Report" in content
        assert "Executive Metric Summary" in content
        assert "Scenario-by-Scenario Evaluation Results" in content
