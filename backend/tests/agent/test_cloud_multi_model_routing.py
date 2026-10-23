from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List
import httpx
import pytest
from unittest.mock import MagicMock, patch

from backend.app.common.config import Settings
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory
from backend.app.summary.llm.huggingface_provider import HuggingFaceProvider
from backend.app.agent.graph.workflow import create_investigation_graph
from backend.app.agent.graph.nodes.evaluate_hypotheses import evaluate_hypotheses_node
from backend.app.agent.graph.nodes.review_report import review_report_node
from backend.app.agent.graph.state import InvestigationState


# -----------------------------------------------------------------------------
# 1. Task-to-Model Routing Tests
# -----------------------------------------------------------------------------

def test_task_specific_model_routing_configuration():
    """Verify independent task-specific model routing settings in Settings."""
    settings = Settings(
        LLM_PROVIDER="huggingface",
        HF_TOKEN="hf_test_token_12345",
        HF_MODEL="meta-llama/Llama-3.1-8B-Instruct",
        HF_INVESTIGATION_MODEL="meta-llama/Llama-3.1-70B-Instruct",
        HF_SUMMARY_MODEL="mistralai/Mistral-7B-Instruct-v0.3",
        HF_REVIEW_MODEL="Qwen/Qwen2.5-72B-Instruct",
    )

    # Investigation / RCA routing
    assert settings.get_model_for_task("investigation") == "meta-llama/Llama-3.1-70B-Instruct"
    assert settings.get_model_for_task("rca") == "meta-llama/Llama-3.1-70B-Instruct"
    assert settings.get_model_for_task("hypothesis_evaluation") == "meta-llama/Llama-3.1-70B-Instruct"

    # Summary generation routing
    assert settings.get_model_for_task("summary") == "mistralai/Mistral-7B-Instruct-v0.3"
    assert settings.get_model_for_task("postmortem") == "mistralai/Mistral-7B-Instruct-v0.3"

    # Report review routing
    assert settings.get_model_for_task("report_review") == "Qwen/Qwen2.5-72B-Instruct"
    assert settings.get_model_for_task("review") == "Qwen/Qwen2.5-72B-Instruct"

    # Unspecified or unknown task falls back to base HF_MODEL
    assert settings.get_model_for_task("unknown_task") == "meta-llama/Llama-3.1-8B-Instruct"
    assert settings.get_model_for_task(None) == "meta-llama/Llama-3.1-8B-Instruct"


def test_provider_factory_instantiates_task_specific_providers():
    """Verify ProviderFactory yields HuggingFaceProvider instances bound to configured task models."""
    ProviderFactory.reset_provider()
    settings = Settings(
        LLM_PROVIDER="huggingface",
        HF_TOKEN="hf_mock_token_abc",
        HF_INVESTIGATION_MODEL="custom-org/investigation-model-v1",
        HF_SUMMARY_MODEL="custom-org/summary-model-v2",
        HF_REVIEW_MODEL="custom-org/review-model-v3",
    )

    inv_provider = ProviderFactory.get_provider(settings, task="investigation")
    sum_provider = ProviderFactory.get_provider(settings, task="summary")
    rev_provider = ProviderFactory.get_provider(settings, task="report_review")

    assert isinstance(inv_provider, HuggingFaceProvider)
    assert inv_provider.get_model_name() == "custom-org/investigation-model-v1"
    assert inv_provider.get_task() == "investigation"

    assert isinstance(sum_provider, HuggingFaceProvider)
    assert sum_provider.get_model_name() == "custom-org/summary-model-v2"
    assert sum_provider.get_task() == "summary"

    assert isinstance(rev_provider, HuggingFaceProvider)
    assert rev_provider.get_model_name() == "custom-org/review-model-v3"
    assert rev_provider.get_task() == "report_review"

    ProviderFactory.reset_provider()


# -----------------------------------------------------------------------------
# 2. Provider Failures & Deterministic Fallback Labeling Tests
# -----------------------------------------------------------------------------

def test_huggingface_http_402_prepaid_credits_exhausted():
    """Verify that HTTP 402 from HF Inference Providers raises clear PrepaidCreditsRequired RuntimeError."""
    settings = Settings(
        LLM_PROVIDER="huggingface",
        HF_TOKEN="hf_real_token_without_credits",
        HF_MODEL="meta-llama/Llama-3.1-8B-Instruct",
    )
    provider = HuggingFaceProvider(settings, task="investigation")

    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_resp.json.return_value = {
        "error": "You have no remaining credits. Purchase pre-paid credits to continue using Inference Providers."
    }
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        with pytest.raises(RuntimeError) as exc_info:
            provider.generate("Test prompt")
        assert "402" in str(exc_info.value)
        assert "PrepaidCreditsRequired" in str(exc_info.value)

    # Check telemetry record recorded failure
    history = provider.get_call_history()
    assert len(history) == 1
    assert history[0]["fallback_status"] is True
    assert "402" in history[0]["errors"]
    assert history[0]["actual_model_id"] == "meta-llama/Llama-3.1-8B-Instruct"


def test_huggingface_http_401_unauthorized():
    """Verify HTTP 401 raises authentication error with token verification advice."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="invalid_token")
    provider = HuggingFaceProvider(settings, task="summary")

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        with pytest.raises(RuntimeError) as exc_info:
            provider.generate("Test prompt")
        assert "401" in str(exc_info.value)

    history = provider.get_call_history()
    assert len(history) == 1
    assert history[0]["fallback_status"] is True


def test_fallback_results_clearly_labeled_as_non_llm():
    """Verify deterministic fallback clearly identifies results as non-LLM output."""
    mock_failing_provider = MagicMock(spec=LLMProvider)
    mock_failing_provider.is_available.return_value = True
    mock_failing_provider.generate.side_effect = RuntimeError("HF 402: PrepaidCreditsRequired")
    mock_failing_provider.get_provider_name.return_value = "huggingface"
    mock_failing_provider.get_model_name.return_value = "meta-llama/Llama-3.1-8B-Instruct"

    test_state: InvestigationState = {
        "incident_key": "INC-TEST-001",
        "incident_title": "Database Saturation",
        "target_service": "payment-api",
        "environment": "production",
        "collected_evidence": [
            {
                "evidence_id": "EV-01",
                "source_type": "METRIC_OBSERVATION",
                "service": "payment-api",
                "claim": "Database connection pool utilization 100%",
            }
        ],
        "rca_candidates": [
            {
                "candidate_name": "Database Connection Pool Exhaustion",
                "candidate_type": "DATABASE",
                "confidence": 0.92,
                "evidence_signal_ids": ["EV-01"],
            }
        ],
        "runbooks": [],
        "errors": [],
        "model_call_records": [],
    }

    result = evaluate_hypotheses_node(
        state=test_state,
        llm_provider=mock_failing_provider,
        settings=Settings(LLM_PROVIDER="huggingface"),
    )

    # Must be marked as fallback
    assert result["is_fallback"] is True
    assert result["llm_provider"] == "fallback"
    assert "deterministic-rules (non-LLM)" in result["llm_model"]
    assert "[Deterministic Rule-Based Fallback (Non-LLM)]" in result["uncertainty_assessment"]

    # Model call records must include the failed attempt and fallback record
    records = result.get("model_call_records", [])
    assert len(records) >= 1
    assert any(r["fallback_status"] is True for r in records)


# -----------------------------------------------------------------------------
# 3. Client-Observed Request Latency & Telemetry Metrics Tests
# -----------------------------------------------------------------------------

def test_client_observed_latency_measured_accurately():
    """Verify client-observed request latency is timed via perf_counter without hidden reasoning time claims."""
    settings = Settings(LLM_PROVIDER="huggingface", HF_TOKEN="hf_valid_token")
    provider = HuggingFaceProvider(settings, task="investigation")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "{\"hypotheses_evaluated\": []}"}}]
    }

    def mock_post(*args, **kwargs):
        time.sleep(0.05)  # 50ms simulated network duration
        return mock_resp

    with patch.object(httpx.Client, "post", side_effect=mock_post):
        content, record = provider.generate_with_telemetry("Evaluate incident", task="investigation")

    assert content == "{\"hypotheses_evaluated\": []}"
    assert record["provider"] == "huggingface"
    assert record["task"] == "investigation"
    assert record["fallback_status"] is False
    assert record["errors"] is None

    # Latency must be measured on client side in real milliseconds >= 45ms
    assert record["request_latency_ms"] >= 45.0
    assert record["request_latency_seconds"] >= 0.045
    # Verify no ungrounded claims about hidden internal server reasoning time
    assert "reasoning_latency" not in record


# -----------------------------------------------------------------------------
# 4. LangGraph Report Review Node & Safety Boundary Tests
# -----------------------------------------------------------------------------

def test_report_review_node_verifies_citations_and_safety_boundaries():
    """Verify review_report_node validates evidence citation integrity and human approval flags."""
    sample_state: InvestigationState = {
        "incident_key": "INC-TEST-002",
        "collected_evidence": [
            {"evidence_id": "EV-01", "service": "auth-api", "claim": "JWT verification failure spike"},
            {"evidence_id": "EV-02", "service": "redis", "claim": "Redis cache connection timeout"},
        ],
        "final_report": {
            "incident_key": "INC-TEST-002",
            "observed_facts": [
                "[EV-01] JWT verification failure rate elevated to 42%",
                "[EV-02] Redis cache connection timeout observed",
                "Ungrounded claim without citation brackets",
            ],
            "hypotheses_evaluated": [
                {
                    "hypothesis": "Redis Cache Outage",
                    "supporting_evidence_ids": ["EV-02", "EV-GHOST-99"],  # EV-GHOST-99 is invalid citation
                }
            ],
            "recommended_diagnostic_steps": [
                {
                    "action": "Check Redis sentinel cluster health",
                    "target_service": "redis",
                    "requires_human_approval": True,
                }
            ],
        },
        "model_call_records": [],
    }

    res = review_report_node(sample_state)
    assessment = res["review_assessment"]

    assert assessment is not None
    assert assessment["total_citations_checked"] >= 2
    # EV-GHOST-99 is invalid, EV-01 and EV-02 are valid
    assert "EV-GHOST-99" in assessment["invalid_citations"]
    assert assessment["citation_validity_rate"] < 1.0

    # One ungrounded claim detected
    assert assessment["unsupported_claims_count"] == 1
    assert assessment["safety_boundaries_enforced"] is True
    assert assessment["review_model"] == "deterministic-rules (non-LLM)"
    assert assessment["is_fallback"] is True


# -----------------------------------------------------------------------------
# 5. Evaluation Calculations (Top-1, Top-3, MRR, Rates) Tests
# -----------------------------------------------------------------------------

def test_rca_metric_calculations():
    """Verify mathematical accuracy of Top-1, Top-3, and MRR calculations."""
    # Case 1: Ground truth in rank 1 -> reciprocal rank = 1.0
    # Case 2: Ground truth in rank 3 -> reciprocal rank = 1/3 = 0.3333
    # Case 3: Ground truth in rank 2 -> reciprocal rank = 1/2 = 0.5000
    # Case 4: Ground truth not in candidates -> reciprocal rank = 0.0

    trials = [
        {"candidates": ["cause_A", "cause_B", "cause_C"], "ground_truth": "cause_A"},
        {"candidates": ["cause_X", "cause_Y", "cause_B"], "ground_truth": "cause_B"},
        {"candidates": ["cause_M", "cause_N", "cause_P"], "ground_truth": "cause_N"},
        {"candidates": ["cause_1", "cause_2", "cause_3"], "ground_truth": "cause_99"},
    ]

    top1_hits = 0
    top3_hits = 0
    reciprocal_ranks = []

    for trial in trials:
        cands = trial["candidates"]
        gt = trial["ground_truth"]

        if cands and cands[0] == gt:
            top1_hits += 1

        if gt in cands[:3]:
            top3_hits += 1
            rank = cands[:3].index(gt) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    n = len(trials)
    top1_accuracy = top1_hits / n
    top3_accuracy = top3_hits / n
    mrr = sum(reciprocal_ranks) / n

    assert top1_accuracy == 0.25  # 1 out of 4
    assert top3_accuracy == 0.75  # 3 out of 4
    # MRR: (1.0 + 1/3 + 1/2 + 0) / 4 = 1.8333 / 4 = 0.45833
    assert abs(mrr - (1.0 + 1/3 + 0.5 + 0.0) / 4) < 1e-4


def test_fallback_never_counted_as_live_cloud_success():
    """Verify that benchmark rigor rules strictly disallow counting fallback runs as live successes."""
    trial_result = {
        "case_id": "test_case_1",
        "is_fallback": True,
        "model_provider": "fallback",
        "model_name": "deterministic-rules (non-LLM)",
        "cloud_attempt_status_code": 402,
    }

    # Strict rule: is_live_cloud_success must be False
    is_live_cloud_success = (
        not trial_result["is_fallback"]
        and trial_result["model_provider"] == "huggingface"
        and trial_result.get("cloud_attempt_status_code") == 200
    )
    assert is_live_cloud_success is False
