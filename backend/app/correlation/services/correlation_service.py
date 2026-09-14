from collections import Counter
from datetime import datetime
import logging
from typing import List, Optional, Tuple
from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session, selectinload

from backend.app.common.config import Settings, get_settings
from backend.app.correlation.db.models import CorrelationGroup, CorrelationSignal
from backend.app.correlation.schemas.correlation import CorrelationGroupCreateRequest, SignalInput
from backend.app.correlation.scoring.scorer import CorrelationScorer
from backend.app.correlation.services.incident_client import IncidentServiceClient

logger = logging.getLogger(__name__)


class CorrelationService:
    """Service layer for evaluating signals, forming correlation groups, and integrating with incidents."""

    def __init__(
        self,
        scorer: Optional[CorrelationScorer] = None,
        incident_client: Optional[IncidentServiceClient] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.scorer = scorer or CorrelationScorer(self.settings)
        self.incident_client = incident_client or IncidentServiceClient(self.settings.INCIDENT_SERVICE_URL)

    @staticmethod
    def generate_group_key(db: Session) -> str:
        """
        Generate a database-backed unique group key (e.g. GRP-000001).
        Uses PostgreSQL sequence 'correlation_group_key_seq' when available,
        falling back to table-count increment for test SQLite databases.
        """
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            seq_val = db.execute(text("SELECT nextval('correlation_group_key_seq')")).scalar()
            return f"GRP-{int(seq_val):06d}"
        else:
            count = db.execute(select(func.count(CorrelationGroup.id))).scalar() or 0
            return f"GRP-{count + 1:06d}"

    def evaluate_signals(
        self,
        signals: List[SignalInput],
    ) -> Tuple[float, bool, List[str]]:
        """Dry-run correlation evaluation on candidate signals."""
        score, is_correlated, reasons, _ = self.scorer.score_group(signals)
        return score, is_correlated, reasons

    def create_group(
        self,
        db: Session,
        req: CorrelationGroupCreateRequest,
    ) -> CorrelationGroup:
        """
        Evaluate candidate signals, form a persisted CorrelationGroup with associated signals,
        and optionally trigger incident creation if auto-incident threshold is met.
        """
        signals = req.signals
        group_score, is_correlated, group_reasons, signal_breakdowns = self.scorer.score_group(signals)

        # Infer primary metadata
        services = [s.service for s in signals]
        primary_service = Counter(services).most_common(1)[0][0] if services else "unknown"
        environment = signals[0].environment if signals else "unknown"
        started_at = min(s.timestamp for s in signals)
        ended_at = max(s.timestamp for s in signals)

        # Generate group key
        group_key = self.generate_group_key(db)

        # Highest severity present
        severities = [s.severity.upper() for s in signals]
        highest_sev = "CRITICAL" if "CRITICAL" in severities or "SEV1" in severities else (
            "HIGH" if "HIGH" in severities or "ERROR" in severities or "SEV2" in severities else "MEDIUM"
        )

        db_group = CorrelationGroup(
            group_key=group_key,
            environment=environment,
            primary_service=primary_service,
            started_at=started_at,
            ended_at=ended_at,
            correlation_score=group_score,
            status=req.status.value if req.status else "CANDIDATE",
            reasons=group_reasons,
        )
        db.add(db_group)
        db.flush()  # assign db_group.id

        # Add associated signals
        for s in signals:
            s_score, s_reasons = signal_breakdowns.get(s.signal_id, (group_score, []))
            db_signal = CorrelationSignal(
                group_id=db_group.id,
                signal_id=s.signal_id,
                signal_type=s.signal_type.value,
                service=s.service,
                environment=s.environment,
                timestamp=s.timestamp,
                severity=s.severity,
                source_reference=s.source_reference,
                metadata_json=s.metadata,
                relationship_score=s_score,
                relationship_reasons=s_reasons,
            )
            db.add(db_signal)

        # Check for incident creation threshold
        if group_score >= self.settings.AUTO_INCIDENT_THRESHOLD:
            title = f"Correlated Incident on {primary_service} ({highest_sev})"
            description = (
                f"Automated correlation group {group_key} (Score: {group_score:.2f}). "
                f"Reasons: {'; '.join(group_reasons[:3])}."
            )
            incident_key = self.incident_client.create_incident(
                title=title,
                description=description,
                severity=highest_sev,
                environment=environment,
                started_at=started_at,
                confidence=group_score,
            )

            if incident_key:
                db_group.incident_key = incident_key
                db_group.status = "CONFIRMED"

                # Attach external event signals to the newly created incident
                for s in signals:
                    ref_id = s.source_reference or s.signal_id
                    if s.signal_type.value in ["EVENT", "ALERT", "DEPLOYMENT", "TRACE"]:
                        self.incident_client.attach_event_evidence(
                            incident_key=incident_key,
                            event_id=ref_id,
                            relation_type="PRIMARY_SIGNAL" if s.service == primary_service else "RELATED_ERROR",
                            score=signal_breakdowns.get(s.signal_id, (group_score, []))[0],
                        )

        db.commit()
        db.refresh(db_group)

        # Eagerly load signals
        return db.execute(
            select(CorrelationGroup)
            .options(selectinload(CorrelationGroup.signals))
            .where(CorrelationGroup.id == db_group.id)
        ).scalar_one()

    @staticmethod
    def get_group(
        db: Session,
        group_key: str,
    ) -> Optional[CorrelationGroup]:
        """Retrieve a correlation group by its group_key with associated signals."""
        return db.execute(
            select(CorrelationGroup)
            .options(selectinload(CorrelationGroup.signals))
            .where(CorrelationGroup.group_key == group_key)
        ).scalar_one_or_none()

    @staticmethod
    def list_groups(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        environment: Optional[str] = None,
        service: Optional[str] = None,
        min_score: Optional[float] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[CorrelationGroup], int]:
        """Retrieve paginated correlation groups with multi-attribute filtering."""
        query: Select = select(CorrelationGroup).options(selectinload(CorrelationGroup.signals))
        count_query: Select = select(func.count(CorrelationGroup.id))

        filters = []
        if status:
            filters.append(CorrelationGroup.status == status)
        if environment:
            filters.append(CorrelationGroup.environment == environment)
        if service:
            filters.append(CorrelationGroup.primary_service == service)
        if min_score is not None:
            filters.append(CorrelationGroup.correlation_score >= min_score)
        if start_time:
            filters.append(CorrelationGroup.started_at >= start_time)
        if end_time:
            filters.append(CorrelationGroup.ended_at <= end_time)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0
        offset = (page - 1) * page_size

        items = list(
            db.execute(
                query.order_by(CorrelationGroup.created_at.desc())
                .offset(offset)
                .limit(page_size)
            ).scalars().all()
        )

        return items, total
