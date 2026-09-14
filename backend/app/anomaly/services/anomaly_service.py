from datetime import datetime
import logging
from typing import List, Optional, Tuple
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.common.config import get_settings
from backend.app.anomaly.db.models import AnomalyResult, MetricObservation
from backend.app.anomaly.detectors.base import AnomalyDetector
from backend.app.anomaly.detectors.isolation_forest import IsolationForestDetector
from backend.app.anomaly.detectors.statistical import StatisticalDetector
from backend.app.anomaly.services.observation_service import ObservationService

logger = logging.getLogger(__name__)


class AnomalyService:
    """Service layer managing the anomaly detection pipeline, persistence, and queries."""

    def __init__(self, detectors: Optional[List[AnomalyDetector]] = None):
        settings = get_settings()
        self.detectors = detectors or [
            StatisticalDetector(
                warning_z=settings.STATISTICAL_WARNING_Z,
                critical_z=settings.STATISTICAL_CRITICAL_Z,
                min_samples=settings.STATISTICAL_MIN_SAMPLES,
            ),
            IsolationForestDetector(
                contamination=settings.ISOLATION_FOREST_CONTAMINATION,
                min_samples=settings.ISOLATION_FOREST_MIN_SAMPLES,
                random_state=settings.ISOLATION_FOREST_RANDOM_STATE,
            ),
        ]

    def analyze_observation(
        self,
        db: Session,
        observation: MetricObservation,
    ) -> List[AnomalyResult]:
        """
        Execute configured anomaly detector algorithms on a metric observation
        and persist the resulting AnomalyResult records.
        """
        # Fetch historical series for this metric
        history = ObservationService.get_historical_values(
            db=db,
            service=observation.service,
            environment=observation.environment,
            metric_name=observation.metric_name,
            before_timestamp=observation.timestamp,
            limit=100,
        )

        results: List[AnomalyResult] = []

        for detector in self.detectors:
            eval_output = detector.detect(
                current_val=observation.metric_value,
                history_vals=history,
                metric_name=observation.metric_name,
            )

            # Check if anomaly result for this (observation_id, detector) already exists
            existing = db.execute(
                select(AnomalyResult).where(
                    AnomalyResult.observation_id == observation.observation_id,
                    AnomalyResult.detector == eval_output.detector,
                )
            ).scalar_one_or_none()

            if existing:
                results.append(existing)
                continue

            db_result = AnomalyResult(
                observation_id=observation.observation_id,
                detector=eval_output.detector,
                detector_version=eval_output.detector_version,
                anomaly_score=eval_output.anomaly_score,
                is_anomaly=eval_output.is_anomaly,
                severity=eval_output.severity,
                expected_value=eval_output.expected_value,
                deviation=eval_output.deviation,
                reason=eval_output.reason,
            )

            try:
                db.add(db_result)
                db.commit()
                db.refresh(db_result)
                logger.info(
                    "Anomaly evaluated: obs_id='%s', detector='%s', is_anomaly=%s, score=%.2f, sev='%s'",
                    db_result.observation_id,
                    db_result.detector,
                    db_result.is_anomaly,
                    db_result.anomaly_score,
                    db_result.severity,
                )
                results.append(db_result)
            except IntegrityError:
                db.rollback()
                existing = db.execute(
                    select(AnomalyResult).where(
                        AnomalyResult.observation_id == observation.observation_id,
                        AnomalyResult.detector == eval_output.detector,
                    )
                ).scalar_one_or_none()
                if existing:
                    results.append(existing)

        return results

    @staticmethod
    def get_anomalies_for_observation(
        db: Session,
        observation_id: str,
    ) -> List[AnomalyResult]:
        """Retrieve all detector anomaly results for a given observation ID."""
        return list(
            db.execute(
                select(AnomalyResult)
                .where(AnomalyResult.observation_id == observation_id)
                .order_by(AnomalyResult.created_at.asc())
            ).scalars().all()
        )

    @staticmethod
    def list_anomalies(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        severity: Optional[str] = None,
        detector: Optional[str] = None,
        is_anomaly: Optional[bool] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[AnomalyResult], int]:
        """Retrieve paginated anomaly results with multi-attribute filtering."""
        query: Select = select(AnomalyResult)
        count_query: Select = select(func.count(AnomalyResult.id))

        filters = []
        if severity:
            filters.append(AnomalyResult.severity == severity)
        if detector:
            filters.append(AnomalyResult.detector == detector)
        if is_anomaly is not None:
            filters.append(AnomalyResult.is_anomaly == is_anomaly)
        if start_time:
            filters.append(AnomalyResult.created_at >= start_time)
        if end_time:
            filters.append(AnomalyResult.created_at <= end_time)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0
        offset = (page - 1) * page_size

        items = list(
            db.execute(
                query.order_by(AnomalyResult.created_at.desc())
                .offset(offset)
                .limit(page_size)
            ).scalars().all()
        )

        return items, total
