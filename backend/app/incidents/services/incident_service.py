import logging
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple
from sqlalchemy import Select, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.incidents.db.models import Incident, IncidentEvent
from backend.app.incidents.schemas.incident import (
    IncidentCreate,
    IncidentEventCreate,
    IncidentSeverity,
    IncidentStatus,
)

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    """Raised when an invalid lifecycle state transition is requested."""
    def __init__(self, current_status: str, target_status: str):
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Invalid incident status transition: {current_status} -> {target_status}"
        )


class IncidentService:
    """Service layer managing Incident domain models, lifecycle state transitions, and event associations."""

    ALLOWED_TRANSITIONS: dict[IncidentStatus, Set[IncidentStatus]] = {
        IncidentStatus.DETECTED: {
            IncidentStatus.INVESTIGATING,
            IncidentStatus.ACKNOWLEDGED,
            IncidentStatus.FALSE_POSITIVE,
        },
        IncidentStatus.INVESTIGATING: {
            IncidentStatus.ACKNOWLEDGED,
            IncidentStatus.RESOLVED,
            IncidentStatus.FALSE_POSITIVE,
        },
        IncidentStatus.ACKNOWLEDGED: {
            IncidentStatus.INVESTIGATING,
            IncidentStatus.RESOLVED,
        },
        IncidentStatus.RESOLVED: {
            IncidentStatus.CLOSED,
        },
        IncidentStatus.CLOSED: set(),
        IncidentStatus.FALSE_POSITIVE: set(),
    }

    @staticmethod
    def generate_incident_key(db: Session) -> str:
        """
        Generate a unique, human-readable incident key using a PostgreSQL sequence.
        Falls back to atomic max increment if sequence does not exist or for SQLite test environments.
        """
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            try:
                val = db.execute(text("SELECT nextval('incident_key_seq')")).scalar()
                return f"INC-{val:06d}"
            except Exception:
                db.rollback()

        # Fallback for SQLite testing environments or when sequence is not yet created
        max_key = db.execute(select(func.max(Incident.incident_key))).scalar()
        if max_key and max_key.startswith("INC-"):
            try:
                num = int(max_key.split("-")[1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        return f"INC-{num:06d}"

    @classmethod
    def create_incident(cls, db: Session, incident_in: IncidentCreate) -> Incident:
        """Create and persist a new operational incident in DETECTED state.

        If an incident with the specified incident_key already exists, returns
        the existing record idempotently instead of raising IntegrityError.
        """
        if incident_in.incident_key:
            existing = cls.get_incident_by_key(db, incident_in.incident_key)
            if existing:
                logger.info(
                    "Incident with key '%s' already exists; returning existing instance.",
                    incident_in.incident_key,
                )
                return existing

        key = incident_in.incident_key or cls.generate_incident_key(db)

        incident = Incident(
            incident_key=key,
            title=incident_in.title,
            description=incident_in.description,
            severity=incident_in.severity.value,
            status=IncidentStatus.DETECTED.value,
            environment=incident_in.environment,
            started_at=incident_in.started_at,
            confidence=incident_in.confidence,
        )

        try:
            db.add(incident)
            db.commit()
            db.refresh(incident)
        except IntegrityError:
            db.rollback()
            existing = cls.get_incident_by_key(db, key)
            if existing:
                logger.info(
                    "Incident key '%s' committed concurrently; returning existing instance.",
                    key,
                )
                return existing
            raise

        logger.info(
            "Created incident key='%s', id='%s', severity='%s', status='%s', environment='%s'",
            incident.incident_key,
            incident.id,
            incident.severity,
            incident.status,
            incident.environment,
        )
        return incident

    @staticmethod
    def get_incident_by_key(db: Session, incident_key: str) -> Optional[Incident]:
        """Retrieve an incident by its human-facing incident_key."""
        return db.execute(
            select(Incident).where(Incident.incident_key == incident_key)
        ).scalar_one_or_none()

    @staticmethod
    def list_incidents(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> Tuple[List[Incident], int]:
        """Retrieve a paginated list of incidents with optional filters."""
        query: Select = select(Incident)
        count_query: Select = select(func.count(Incident.id))

        filters = []
        if status:
            filters.append(Incident.status == status)
        if severity:
            filters.append(Incident.severity == severity)
        if environment:
            filters.append(Incident.environment == environment)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0

        offset = (page - 1) * page_size
        items = list(
            db.execute(
                query.order_by(Incident.created_at.desc()).offset(offset).limit(page_size)
            ).scalars().all()
        )

        return items, total

    @classmethod
    def transition_status(
        cls,
        db: Session,
        incident_key: str,
        target_status: IncidentStatus,
    ) -> Incident:
        """
        Transition an incident's lifecycle status according to defined state machine rules.

        Raises:
            KeyError if incident not found.
            InvalidTransitionError if the transition is disallowed.
        """
        incident = cls.get_incident_by_key(db, incident_key)
        if not incident:
            raise KeyError(f"Incident with key '{incident_key}' not found")

        current_status = IncidentStatus(incident.status)
        allowed_targets = cls.ALLOWED_TRANSITIONS.get(current_status, set())

        if target_status not in allowed_targets:
            logger.warning(
                "Rejected invalid status transition for incident '%s': %s -> %s",
                incident_key,
                current_status.value,
                target_status.value,
            )
            raise InvalidTransitionError(current_status.value, target_status.value)

        # Apply state transition
        incident.status = target_status.value
        incident.updated_at = datetime.now(timezone.utc)

        # If resolving, record ended_at timestamp
        if target_status == IncidentStatus.RESOLVED and incident.ended_at is None:
            incident.ended_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(incident)

        logger.info(
            "Status transitioned for incident '%s': %s -> %s",
            incident_key,
            current_status.value,
            target_status.value,
        )
        return incident

    @classmethod
    def add_event_to_incident(
        cls,
        db: Session,
        incident_key: str,
        event_in: IncidentEventCreate,
    ) -> Tuple[Optional[IncidentEvent], bool]:
        """
        Associate an external canonical observability event with an incident.

        Returns:
            Tuple[Optional[IncidentEvent], bool]: Association and boolean indicating
            whether it was newly created (True) or was a duplicate (False).
        """
        incident = cls.get_incident_by_key(db, incident_key)
        if not incident:
            return None, False

        # Check existing association (idempotency check)
        existing = db.execute(
            select(IncidentEvent).where(
                IncidentEvent.incident_id == incident.id,
                IncidentEvent.event_id == event_in.event_id,
            )
        ).scalar_one_or_none()

        if existing:
            logger.info(
                "Event '%s' is already associated with incident '%s'. Returning existing link.",
                event_in.event_id,
                incident_key,
            )
            return existing, False

        assoc = IncidentEvent(
            incident_id=incident.id,
            event_id=event_in.event_id,
            relation_type=event_in.relation_type.value,
            score=event_in.score,
        )

        try:
            db.add(assoc)
            db.commit()
            db.refresh(assoc)
            logger.info(
                "Associated event '%s' with incident '%s' (relation='%s', score=%s)",
                event_in.event_id,
                incident_key,
                event_in.relation_type.value,
                event_in.score,
            )
            return assoc, True
        except IntegrityError:
            db.rollback()
            existing = db.execute(
                select(IncidentEvent).where(
                    IncidentEvent.incident_id == incident.id,
                    IncidentEvent.event_id == event_in.event_id,
                )
            ).scalar_one_or_none()
            if existing:
                return existing, False
            raise

    @classmethod
    def get_incident_events(
        cls,
        db: Session,
        incident_key: str,
    ) -> Optional[List[IncidentEvent]]:
        """Retrieve all event associations for an incident."""
        incident = cls.get_incident_by_key(db, incident_key)
        if not incident:
            return None

        return list(
            db.execute(
                select(IncidentEvent)
                .where(IncidentEvent.incident_id == incident.id)
                .order_by(IncidentEvent.created_at.asc())
            ).scalars().all()
        )
