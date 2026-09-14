import logging
from typing import List, Optional, Tuple
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.ingestion.db.models import Event
from backend.app.ingestion.schemas.event import EventCreate
from backend.app.ingestion.services.task_publisher import TaskPublisher

logger = logging.getLogger(__name__)


class EventService:
    """Service layer handling business logic for event ingestion, retrieval, and async task dispatch."""

    @staticmethod
    def create_event(
        db: Session,
        event_in: EventCreate,
        publish_task: bool = True,
    ) -> Tuple[Event, bool]:
        """
        Ingest and persist an observability event, then dispatch an async processing task.

        Returns:
            Tuple[Event, bool]: The persisted Event and a boolean indicating whether
            it was newly created (True) or was a duplicate (False).
        """
        # Check if event already exists (idempotency check)
        existing = db.execute(
            select(Event).where(Event.event_id == event_in.event_id)
        ).scalar_one_or_none()

        if existing:
            logger.info(
                "Duplicate event received with event_id='%s' (service='%s'). Returning existing record.",
                event_in.event_id,
                event_in.service,
            )
            return existing, False

        db_event = Event(
            event_id=event_in.event_id,
            timestamp=event_in.timestamp,
            service=event_in.service,
            environment=event_in.environment,
            event_type=event_in.event_type.value,
            severity=event_in.severity.value,
            message=event_in.message,
            trace_id=event_in.trace_id,
            metadata_json=event_in.metadata,
            processing_status="PENDING",
        )

        try:
            db.add(db_event)
            db.commit()
            db.refresh(db_event)
            logger.info(
                "Successfully stored event id='%s', event_id='%s', service='%s', type='%s', severity='%s'",
                db_event.id,
                db_event.event_id,
                db_event.service,
                db_event.event_type,
                db_event.severity,
            )

            # Publish async processing job
            if publish_task:
                TaskPublisher.publish_event_processing(db_event.event_id)

            return db_event, True
        except IntegrityError:
            # Handle race conditions for concurrent duplicate submissions
            db.rollback()
            logger.warning(
                "Integrity conflict for event_id='%s'. Resolving to existing record.",
                event_in.event_id,
            )
            existing = db.execute(
                select(Event).where(Event.event_id == event_in.event_id)
            ).scalar_one_or_none()
            if existing:
                return existing, False
            raise

    @staticmethod
    def get_event_by_event_id(db: Session, event_id: str) -> Optional[Event]:
        """Retrieve an event by its unique event_id."""
        return db.execute(
            select(Event).where(Event.event_id == event_id)
        ).scalar_one_or_none()

    @staticmethod
    def list_events(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        service: Optional[str] = None,
        environment: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> Tuple[List[Event], int]:
        """
        Retrieve paginated events with optional filters.

        Returns:
            Tuple[List[Event], int]: List of events and total record count.
        """
        query: Select = select(Event)
        count_query: Select = select(func.count(Event.id))

        filters = []
        if service:
            filters.append(Event.service == service)
        if environment:
            filters.append(Event.environment == environment)
        if event_type:
            filters.append(Event.event_type == event_type)
        if severity:
            filters.append(Event.severity == severity)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0

        offset = (page - 1) * page_size
        items = list(
            db.execute(
                query.order_by(Event.timestamp.desc()).offset(offset).limit(page_size)
            ).scalars().all()
        )

        return items, total
