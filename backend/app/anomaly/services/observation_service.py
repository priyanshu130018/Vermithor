from datetime import datetime
import logging
from typing import List, Optional, Tuple
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.anomaly.db.models import MetricObservation
from backend.app.anomaly.schemas.observation import MetricObservationCreate

logger = logging.getLogger(__name__)


class ObservationService:
    """Service layer managing metric observations and historical baseline retrieval."""

    @staticmethod
    def create_observation(
        db: Session,
        obs_in: MetricObservationCreate,
    ) -> Tuple[MetricObservation, bool]:
        """
        Persist a metric observation with idempotent duplicate protection.

        Returns:
            Tuple[MetricObservation, bool]: The stored record and a boolean indicating
            whether it was newly created (True) or a duplicate (False).
        """
        existing = db.execute(
            select(MetricObservation).where(
                MetricObservation.observation_id == obs_in.observation_id
            )
        ).scalar_one_or_none()

        if existing:
            logger.info(
                "Duplicate observation received for observation_id='%s'. Returning existing record.",
                obs_in.observation_id,
            )
            return existing, False

        db_obs = MetricObservation(
            observation_id=obs_in.observation_id,
            timestamp=obs_in.timestamp,
            service=obs_in.service,
            environment=obs_in.environment,
            metric_name=obs_in.metric_name,
            metric_value=obs_in.metric_value,
            unit=obs_in.unit,
            labels=obs_in.labels,
        )

        try:
            db.add(db_obs)
            db.commit()
            db.refresh(db_obs)
            logger.info(
                "Stored metric observation id='%s', obs_id='%s', service='%s', metric='%s', value=%f",
                db_obs.id,
                db_obs.observation_id,
                db_obs.service,
                db_obs.metric_name,
                db_obs.metric_value,
            )
            return db_obs, True
        except IntegrityError:
            db.rollback()
            existing = db.execute(
                select(MetricObservation).where(
                    MetricObservation.observation_id == obs_in.observation_id
                )
            ).scalar_one_or_none()
            if existing:
                return existing, False
            raise

    @staticmethod
    def get_observation(
        db: Session,
        observation_id: str,
    ) -> Optional[MetricObservation]:
        """Retrieve a single observation by observation_id."""
        return db.execute(
            select(MetricObservation).where(
                MetricObservation.observation_id == observation_id
            )
        ).scalar_one_or_none()

    @staticmethod
    def list_observations(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        service: Optional[str] = None,
        environment: Optional[str] = None,
        metric_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[MetricObservation], int]:
        """Retrieve paginated metric observations with optional multi-attribute filters."""
        query: Select = select(MetricObservation)
        count_query: Select = select(func.count(MetricObservation.id))

        filters = []
        if service:
            filters.append(MetricObservation.service == service)
        if environment:
            filters.append(MetricObservation.environment == environment)
        if metric_name:
            filters.append(MetricObservation.metric_name == metric_name)
        if start_time:
            filters.append(MetricObservation.timestamp >= start_time)
        if end_time:
            filters.append(MetricObservation.timestamp <= end_time)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0
        offset = (page - 1) * page_size

        items = list(
            db.execute(
                query.order_by(MetricObservation.timestamp.desc())
                .offset(offset)
                .limit(page_size)
            ).scalars().all()
        )

        return items, total

    @staticmethod
    def get_historical_values(
        db: Session,
        service: str,
        environment: str,
        metric_name: str,
        before_timestamp: datetime,
        limit: int = 100,
    ) -> List[float]:
        """
        Fetch historical metric values prior to a given timestamp for baseline modeling.
        Returns values in chronological order.
        """
        query = (
            select(MetricObservation.metric_value)
            .where(
                MetricObservation.service == service,
                MetricObservation.environment == environment,
                MetricObservation.metric_name == metric_name,
                MetricObservation.timestamp < before_timestamp,
            )
            .order_by(MetricObservation.timestamp.desc())
            .limit(limit)
        )
        values = list(db.execute(query).scalars().all())
        # Reverse to chronological order for time-series modeling
        values.reverse()
        return [float(v) for v in values]
