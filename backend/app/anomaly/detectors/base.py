from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DetectionResult:
    """Standardized detection result dataclass returned by all detector algorithms."""
    detector: str
    detector_version: str
    anomaly_score: float
    is_anomaly: bool
    severity: str
    expected_value: Optional[float]
    deviation: Optional[float]
    reason: str


class AnomalyDetector(ABC):
    """Abstract base class defining the common interface for anomaly detectors."""

    @property
    @abstractmethod
    def detector_name(self) -> str:
        """Name of the detector algorithm."""
        pass

    @property
    @abstractmethod
    def detector_version(self) -> str:
        """Version of the detector algorithm."""
        pass

    @abstractmethod
    def detect(
        self,
        current_val: float,
        history_vals: List[float],
        metric_name: str = "metric",
    ) -> DetectionResult:
        """
        Evaluate current metric observation against historical baseline values.

        Args:
            current_val: The numeric value of the current observation.
            history_vals: List of historical numeric metric values.
            metric_name: Name of the metric for explainable reason generation.

        Returns:
            DetectionResult containing anomaly score, decision, severity, and reason.
        """
        pass
