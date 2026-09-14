import logging
from typing import List, Union
import numpy as np
from sklearn.ensemble import IsolationForest

from backend.app.anomaly.detectors.base import AnomalyDetector, DetectionResult

logger = logging.getLogger(__name__)


class IsolationForestDetector(AnomalyDetector):
    """
    Non-parametric outlier detection using scikit-learn's Isolation Forest algorithm.
    Partitions metric observation space to isolate anomalies.
    """

    def __init__(
        self,
        contamination: Union[float, str] = "auto",
        min_samples: int = 10,
        random_state: int = 42,
        version: str = "1.0",
    ):
        self.contamination = contamination
        self.min_samples = min_samples
        self.random_state = random_state
        self._version = version

    @property
    def detector_name(self) -> str:
        return "ISOLATION_FOREST"

    @property
    def detector_version(self) -> str:
        return self._version

    def detect(
        self,
        current_val: float,
        history_vals: List[float],
        metric_name: str = "metric",
    ) -> DetectionResult:
        # Edge Case: Insufficient samples to train Isolation Forest
        if len(history_vals) < self.min_samples:
            median_val = float(np.median(history_vals)) if history_vals else None
            return DetectionResult(
                detector=self.detector_name,
                detector_version=self.detector_version,
                anomaly_score=0.0,
                is_anomaly=False,
                severity="NONE",
                expected_value=median_val,
                deviation=None,
                reason=f"Insufficient historical samples (N={len(history_vals)} < {self.min_samples}) for Isolation Forest training.",
            )

        # Prepare dataset: fit on historical baseline
        X_train = np.array(history_vals).reshape(-1, 1)
        model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
        )
        model.fit(X_train)

        # Predict on current observation
        X_test = np.array([[current_val]])
        prediction = model.predict(X_test)[0]  # -1 for anomaly, 1 for inlier
        decision_score = float(model.decision_function(X_test)[0])  # negative is anomaly

        median_expected = float(np.median(history_vals))
        deviation = current_val - median_expected

        if prediction == -1 or decision_score < 0:
            is_anomaly = True
            # Normalize anomaly score into [0.5, 1.0] for outliers
            norm_score = min(1.0, 0.5 + abs(decision_score) * 2.0)

            if norm_score >= 0.85:
                severity = "CRITICAL"
            elif norm_score >= 0.70:
                severity = "HIGH"
            else:
                severity = "MEDIUM"

            reason = (
                f"{metric_name} (observed {current_val:.2f}) was isolated as an anomalous outlier "
                f"by Isolation Forest (anomaly score: {norm_score:.2f}, median expected ~{median_expected:.2f})."
            )
        else:
            is_anomaly = False
            # Normalize normal score into [0.0, 0.5)
            norm_score = max(0.0, 0.5 - decision_score)
            severity = "LOW" if norm_score >= 0.40 else "NONE"
            reason = (
                f"{metric_name} (observed {current_val:.2f}) falls within the normal partition "
                f"boundary learned by Isolation Forest (score: {norm_score:.2f})."
            )

        return DetectionResult(
            detector=self.detector_name,
            detector_version=self.detector_version,
            anomaly_score=round(norm_score, 4),
            is_anomaly=is_anomaly,
            severity=severity,
            expected_value=round(median_expected, 4),
            deviation=round(deviation, 4),
            reason=reason,
        )
