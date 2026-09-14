from backend.app.anomaly.detectors.statistical import StatisticalDetector


def test_statistical_detector_normal_value():
    """Test that a value within normal Gaussian variance is marked normal."""
    detector = StatisticalDetector(warning_z=3.0, critical_z=4.0, min_samples=5)
    history = [98.0, 102.0, 100.0, 95.0, 105.0, 99.0, 101.0]
    current = 103.0

    result = detector.detect(current_val=current, history_vals=history, metric_name="request_latency")
    assert result.is_anomaly is False
    assert result.severity == "NONE"
    assert result.anomaly_score < 0.50
    assert result.expected_value is not None
    assert result.deviation is not None
    assert "within" in result.reason or "standard deviations" in result.reason


def test_statistical_detector_warning_outlier():
    """Test that a 3.5-sigma outlier is marked as HIGH severity anomaly."""
    detector = StatisticalDetector(warning_z=3.0, critical_z=4.0, min_samples=5)
    # Baseline mean ~100, std ~2
    history = [100.0, 101.0, 99.0, 100.0, 102.0, 98.0, 100.0]
    current = 107.5  # ~3.75 sigma above mean

    result = detector.detect(current_val=current, history_vals=history, metric_name="request_latency")
    assert result.is_anomaly is True
    assert result.severity in ["HIGH", "CRITICAL"]
    assert result.anomaly_score >= 0.70
    assert "above the historical baseline" in result.reason


def test_statistical_detector_critical_outlier():
    """Test that an extreme 10-sigma outlier is marked as CRITICAL severity with max score 1.0."""
    detector = StatisticalDetector(warning_z=3.0, critical_z=4.0, min_samples=5)
    history = [10.0, 12.0, 11.0, 9.0, 10.0, 11.0, 10.0]
    current = 500.0  # Massive spike

    result = detector.detect(current_val=current, history_vals=history, metric_name="cpu_usage")
    assert result.is_anomaly is True
    assert result.severity == "CRITICAL"
    assert result.anomaly_score == 1.0
    assert result.deviation > 400.0


def test_statistical_detector_zero_variance():
    """Test that zero standard deviation historical data is handled without division by zero."""
    detector = StatisticalDetector(warning_z=3.0, critical_z=4.0, min_samples=5)
    history = [50.0, 50.0, 50.0, 50.0, 50.0, 50.0]

    # Case A: Matches constant baseline
    res_normal = detector.detect(current_val=50.0, history_vals=history, metric_name="memory_usage")
    assert res_normal.is_anomaly is False
    assert res_normal.severity == "NONE"
    assert res_normal.anomaly_score == 0.0

    # Case B: Deviation from constant baseline
    res_anom = detector.detect(current_val=80.0, history_vals=history, metric_name="memory_usage")
    assert res_anom.is_anomaly is True
    assert res_anom.severity == "CRITICAL"
    assert res_anom.anomaly_score == 1.0
    assert res_anom.deviation == 30.0


def test_statistical_detector_insufficient_history():
    """Test that insufficient historical samples gracefully returns non-anomalous status."""
    detector = StatisticalDetector(warning_z=3.0, critical_z=4.0, min_samples=5)
    history = [10.0, 12.0, 11.0]  # Only 3 samples < 5

    result = detector.detect(current_val=999.0, history_vals=history, metric_name="request_rate")
    assert result.is_anomaly is False
    assert result.severity == "NONE"
    assert result.anomaly_score == 0.0
    assert "Insufficient historical observations" in result.reason
