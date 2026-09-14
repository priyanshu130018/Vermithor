from backend.app.anomaly.detectors.isolation_forest import IsolationForestDetector


def test_isolation_forest_normal_pattern():
    """Test that a metric within the learned historical cluster is classified as normal."""
    detector = IsolationForestDetector(contamination="auto", min_samples=10, random_state=42)
    history = [50.0, 52.0, 49.0, 51.0, 50.0, 48.0, 53.0, 51.0, 49.0, 52.0, 50.0, 51.0, 49.5, 50.5]
    current = 50.2

    result = detector.detect(current_val=current, history_vals=history, metric_name="request_latency")
    assert result.is_anomaly is False
    assert result.severity in ["NONE", "LOW"]
    assert result.anomaly_score < 0.60
    assert "normal partition" in result.reason.lower()


def test_isolation_forest_outlier_detection():
    """Test that an obvious multidimensional outlier is isolated and marked as an anomaly."""
    detector = IsolationForestDetector(contamination="auto", min_samples=10, random_state=42)
    history = [10.0, 11.0, 10.5, 9.8, 10.2, 10.1, 9.9, 10.4, 10.0, 10.3, 10.2, 9.7]
    current = 150.0  # Massive outlier

    result = detector.detect(current_val=current, history_vals=history, metric_name="error_rate")
    assert result.is_anomaly is True
    assert result.severity in ["MEDIUM", "HIGH", "CRITICAL"]
    assert result.anomaly_score >= 0.60
    assert "isolated as an anomalous outlier" in result.reason.lower()


def test_isolation_forest_insufficient_samples():
    """Test that Isolation Forest gracefully falls back when historical points < min_samples."""
    detector = IsolationForestDetector(contamination="auto", min_samples=10, random_state=42)
    history = [10.0, 12.0, 11.0, 10.5]  # Only 4 samples < 10

    result = detector.detect(current_val=150.0, history_vals=history, metric_name="cpu_usage")
    assert result.is_anomaly is False
    assert result.severity == "NONE"
    assert result.anomaly_score == 0.0
    assert "Insufficient historical samples" in result.reason
