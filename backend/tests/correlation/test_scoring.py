from datetime import datetime, timezone
from backend.app.correlation.schemas.correlation import SignalInput, SignalType
from backend.app.correlation.scoring.scorer import CorrelationScorer


def test_strongly_related_signals_scenario():
    """Test standard production failure cascade has strong correlation score and explainable reasons."""
    scorer = CorrelationScorer()

    s_dep = SignalInput(
        signal_id="dep-001",
        signal_type=SignalType.DEPLOYMENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        service="booking-api",
        environment="production",
        severity="INFO",
        metadata={"version": "v2.1.0"},
    )
    s_anom = SignalInput(
        signal_id="anom-001",
        signal_type=SignalType.ANOMALY,
        timestamp=datetime(2026, 8, 29, 12, 2, 0, tzinfo=timezone.utc),
        service="booking-api",
        environment="production",
        severity="HIGH",
        metadata={"metric_name": "request_latency"},
    )
    s_err1 = SignalInput(
        signal_id="err-001",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 2, 15, tzinfo=timezone.utc),
        service="booking-api",
        environment="production",
        severity="ERROR",
        metadata={"trace_id": "tr-xyz-999"},
    )
    s_err2 = SignalInput(
        signal_id="err-002",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 2, 20, tzinfo=timezone.utc),
        service="booking-api",
        environment="production",
        severity="ERROR",
        metadata={"trace_id": "tr-xyz-999"},
    )

    signals = [s_dep, s_anom, s_err1, s_err2]
    group_score, is_correlated, reasons, breakdowns = scorer.score_group(signals)

    assert group_score >= 0.60
    assert is_correlated is True
    assert any("same service: booking-api" in r for r in reasons)
    assert any("same environment: production" in r for r in reasons)
    assert any("deployment occurred" in r for r in reasons)
    assert any("shared trace_id: tr-xyz-999" in r for r in reasons)


def test_unrelated_signals_negative_scenario():
    """Test signals separated by hours and on different services receive low correlation."""
    scorer = CorrelationScorer()

    s1 = SignalInput(
        signal_id="sig-1",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        service="booking-api",
        environment="production",
        severity="INFO",
    )
    s2 = SignalInput(
        signal_id="sig-2",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 16, 0, 0, tzinfo=timezone.utc),  # 4 hours later
        service="payment-api",
        environment="production",
        severity="INFO",
    )

    score, is_correlated, reasons, _ = scorer.score_group([s1, s2])
    assert score < 0.30
    assert is_correlated is False
    assert any("exceeds" in r for r in reasons)


def test_trace_id_correlation_boost():
    """Test that sharing a distributed trace_id boosts correlation score."""
    scorer = CorrelationScorer()

    s1 = SignalInput(
        signal_id="s1",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        service="gateway-api",
        environment="production",
        severity="ERROR",
        metadata={"trace_id": "trace-shared-123"},
    )
    s2 = SignalInput(
        signal_id="s2",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 2, tzinfo=timezone.utc),
        service="auth-api",
        environment="production",
        severity="ERROR",
        metadata={"trace_id": "trace-shared-123"},
    )

    s2_no_trace = SignalInput(
        signal_id="s2_no_trace",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 2, tzinfo=timezone.utc),
        service="auth-api",
        environment="production",
        severity="ERROR",
        metadata={"trace_id": "trace-different-456"},
    )

    score_with_trace, reasons_with_trace = scorer.score_pair(s1, s2)
    score_without_trace, _ = scorer.score_pair(s1, s2_no_trace)

    assert score_with_trace > score_without_trace
    assert any("shared trace_id: trace-shared-123" in r for r in reasons_with_trace)


def test_different_environments_penalty():
    """Test that cross-environment signals (production vs development) are heavily penalized."""
    scorer = CorrelationScorer()

    s_prod = SignalInput(
        signal_id="sp",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        service="booking-api",
        environment="production",
        severity="ERROR",
    )
    s_dev = SignalInput(
        signal_id="sd",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),  # exact same timestamp
        service="booking-api",
        environment="development",
        severity="ERROR",
    )

    score, is_correlated, reasons, _ = scorer.score_group([s_prod, s_dev])
    assert score < 0.30
    assert is_correlated is False
    assert any("different environments" in r for r in reasons)


def test_same_service_scores_higher():
    """Test that same service scores higher than different services when other factors are equal."""
    scorer = CorrelationScorer()

    s1 = SignalInput(
        signal_id="s1",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        service="orders-api",
        environment="production",
        severity="WARNING",
    )
    s2_same = SignalInput(
        signal_id="s2_same",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 10, tzinfo=timezone.utc),
        service="orders-api",
        environment="production",
        severity="WARNING",
    )
    s2_diff = SignalInput(
        signal_id="s2_diff",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 10, tzinfo=timezone.utc),
        service="inventory-api",
        environment="production",
        severity="WARNING",
    )

    score_same, _ = scorer.score_pair(s1, s2_same)
    score_diff, _ = scorer.score_pair(s1, s2_diff)

    assert score_same > score_diff


def test_deployment_proximity_evidence():
    """Test deployment occurring before an error generates non-causal proximity evidence."""
    scorer = CorrelationScorer()

    dep = SignalInput(
        signal_id="dep-1",
        signal_type=SignalType.DEPLOYMENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        service="checkout-service",
        environment="production",
        severity="INFO",
    )
    err = SignalInput(
        signal_id="err-1",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 2, 0, tzinfo=timezone.utc),
        service="checkout-service",
        environment="production",
        severity="ERROR",
    )

    score, reasons = scorer.score_pair(dep, err)
    assert score >= 0.50
    assert any("deployment occurred 2 minutes before anomaly/error signal" in r for r in reasons)


def test_outside_correlation_window():
    """Test that signals separated by more than 15 minutes (900 seconds) do not correlate."""
    scorer = CorrelationScorer()

    s1 = SignalInput(
        signal_id="s1",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
        service="booking-api",
        environment="production",
        severity="ERROR",
    )
    s2 = SignalInput(
        signal_id="s2",
        signal_type=SignalType.EVENT,
        timestamp=datetime(2026, 8, 29, 12, 20, 0, tzinfo=timezone.utc),  # 20 mins apart
        service="booking-api",
        environment="production",
        severity="ERROR",
    )

    score, reasons = scorer.score_pair(s1, s2)
    assert score < 0.20
    assert any("exceeds 15m window" in r for r in reasons)
