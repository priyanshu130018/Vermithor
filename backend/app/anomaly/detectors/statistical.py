import logging
from typing import List
import numpy as np

from backend.app.anomaly.detectors.base import AnomalyDetector, DetectionResult

logger = logging.getLogger(__name__)


class StatisticalDetector(AnomalyDetector):
    """
    Statistical baseline anomaly detector using Gaussian mean, standard deviation, and Z-score.
    Handles zero-variance invariant metrics and insufficient history safely.
    """

    def __init__(
        self,
        warning_z: float = 3.0,
        critical_z: float = 4.0,
        min_samples: int = 5,
        version: str = "1.0",
    ):
        self.warning_z = warning_z
        self.critical_z = critical_z
        self.min_samples = min_samples
        self._version = version

    @property
    def detector_name(self) -> str:
        return "STATISTICAL"

    @property
    def detector_version(self) -> str:
        return self._version

    def detect(
        self,
        current_val: float,
        history_vals: List[float],
        metric_name: str = "metric",
    ) -> DetectionResult:
        # Edge Case 1: Insufficient history to establish reliable baseline
        if len(history_vals) < self.min_samples:
            mean_val = float(np.mean(history_vals)) if history_vals else None
            return DetectionResult(
                detector=self.detector_name,
                detector_version=self.detector_version,
                anomaly_score=0.0,
                is_anomaly=False,
                severity="NONE",
                expected_value=mean_val,
                deviation=None,
                reason=f"Insufficient historical observations (N={len(history_vals)} < {self.min_samples}) to establish a baseline.",
            )

        mean = float(np.mean(history_vals))
        std = float(np.std(history_vals))

        # Edge Case 2: Zero or near-zero variance in historical baseline
        if std < 1e-9:
            if abs(current_val - mean) < 1e-9:
                return DetectionResult(
                    detector=self.detector_name,
                    detector_version=self.detector_version,
                    anomaly_score=0.0,
                    is_anomaly=False,
                    severity="NONE",
                    expected_value=mean,
                    deviation=0.0,
                    reason=f"{metric_name} matches invariant historical baseline value of {mean:.2f}.",
                )
            else:
                deviation = current_val - mean
                return DetectionResult(
                    detector=self.detector_name,
                    detector_version=self.detector_version,
                    anomaly_score=1.0,
                    is_anomaly=True,
                    severity="CRITICAL",
                    expected_value=mean,
                    deviation=deviation,
                    reason=f"{metric_name} shifted by {abs(deviation):.2f} from a perfectly invariant historical baseline of {mean:.2f}.",
                )

        # Standard Gaussian Z-Score calculation
        z_score = (current_val - mean) / std
        abs_z = abs(z_score)
        deviation = current_val - mean

        # Normalize score into [0.0, 1.0]
        anomaly_score = min(1.0, max(0.0, abs_z / self.critical_z))

        # Classify severity and decision
        if abs_z >= self.critical_z:
            is_anomaly = True
            severity = "CRITICAL"
        elif abs_z >= self.warning_z:
            is_anomaly = True
            severity = "HIGH"
        elif abs_z >= 2.0:
            is_anomaly = False
            severity = "LOW"
        else:
            is_anomaly = False
            severity = "NONE"

        direction = "above" if z_score > 0 else "below"
        reason = (
            f"{metric_name} was {abs_z:.2f} standard deviations {direction} "
            f"the historical baseline (expected ~{mean:.2f}, observed {current_val:.2f}, std={std:.2f})."
        )

        return DetectionResult(
            detector=self.detector_name,
            detector_version=self.detector_version,
            anomaly_score=round(anomaly_score, 4),
            is_anomaly=is_anomaly,
            severity=severity,
            expected_value=round(mean, 4),
            deviation=round(deviation, 4),
            reason=reason,
        )
