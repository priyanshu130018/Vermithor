from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from backend.app.agent.db.models import Investigation, investigation_key_seq
from backend.app.agent.graph.state import InvestigationState
from backend.app.agent.graph.workflow import create_investigation_graph
from backend.app.agent.schemas.investigation import (
    InvestigationReport,
    InvestigationRequest,
    InvestigationResponse,
    InvestigationStatus,
)
from backend.app.anomaly.services.anomaly_service import AnomalyService
from backend.app.common.config import Settings, get_settings
from backend.app.correlation.services.correlation_service import CorrelationService
from backend.app.incidents.services.incident_service import IncidentService
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService
from backend.app.rca.analysis.analyzer import RCAAnalyzer
from backend.app.retrieval.retrieval.engine import RetrievalEngine
from backend.app.summary.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class InvestigationService:
    """Service layer managing LangGraph AI incident investigations, persistence, and caching."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    @staticmethod
    def generate_investigation_key(db: Session) -> str:
        """Generate sequence key (e.g. INV-000001)."""
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            try:
                next_val = db.execute(investigation_key_seq).scalar()
                return f"INV-{int(next_val):06d}"
            except Exception:
                db.rollback()
                count = db.execute(select(func.count(Investigation.id))).scalar() or 0
                return f"INV-{count + 1:06d}"
        else:
            count = db.execute(select(func.count(Investigation.id))).scalar() or 0
            return f"INV-{count + 1:06d}"

    def run_investigation(
        self,
        db: Session,
        req: InvestigationRequest,
        telemetry_service: Optional[TelemetryEvidenceService] = None,
        anomaly_service: Optional[AnomalyService] = None,
        correlation_service: Optional[CorrelationService] = None,
        rca_analyzer: Optional[RCAAnalyzer] = None,
        retrieval_engine: Optional[RetrievalEngine] = None,
        llm_provider: Optional[LLMProvider] = None,
    ) -> InvestigationResponse:
        """
        Execute full LangGraph incident investigation workflow.
        Includes idempotency caching, graph execution, persistence, and schema validation.
        """
        incident_key = req.incident_key.strip()

        # 1. Idempotency Check: Return existing completed investigation if not forced refresh
        if not req.force_refresh:
            existing = db.execute(
                select(Investigation)
                .where(
                    Investigation.incident_key == incident_key,
                    Investigation.status.in_(["COMPLETED", "INSUFFICIENT_EVIDENCE"]),
                )
                .order_by(Investigation.created_at.desc())
            ).scalars().first()

            if existing and existing.report_json:
                logger.info("Returning cached investigation '%s' for incident '%s'", existing.investigation_key, incident_key)
                return self._to_response(existing)

        # 2. Validate incident existence
        incident = IncidentService.get_incident_by_key(db, incident_key)
        if not incident:
            logger.warning("Incident with key '%s' not found in database", incident_key)

        # 3. Create initial Investigation record in database
        inv_key = self.generate_investigation_key(db)
        now = datetime.now(timezone.utc)

        db_inv = Investigation(
            investigation_key=inv_key,
            incident_key=incident_key,
            status=InvestigationStatus.INVESTIGATING.value,
            target_service="unknown",
            environment=incident.environment if incident else "production",
            started_at=now,
        )
        db.add(db_inv)
        db.commit()
        db.refresh(db_inv)

        # 4. Construct LangGraph Workflow with dependency injection
        graph = create_investigation_graph(
            db=db,
            telemetry_service=telemetry_service,
            anomaly_service=anomaly_service,
            correlation_service=correlation_service,
            rca_analyzer=rca_analyzer,
            retrieval_engine=retrieval_engine,
            llm_provider=llm_provider,
            settings=self.settings,
        )

        initial_state: InvestigationState = {
            "investigation_id": inv_key,
            "incident_key": incident_key,
            "lookback_minutes": req.lookback_minutes,
            "query_iteration": 0,
            "max_query_iterations": req.max_additional_queries if req.allow_additional_queries else 0,
            "needs_additional_query": False,
            "additional_query_targets": [],
            "errors": [],
            "collected_evidence": [],
        }

        # 5. Execute Graph
        try:
            final_state = graph.invoke(initial_state)
            completed_at = datetime.now(timezone.utc)

            rep_data = final_state.get("final_report")
            db_inv.status = final_state.get("status", InvestigationStatus.COMPLETED.value)
            db_inv.target_service = final_state.get("target_service", "unknown")
            db_inv.leading_hypothesis = (
                final_state.get("leading_hypothesis")
                or final_state.get("primary_root_cause")
                or (rep_data.get("leading_hypothesis") if isinstance(rep_data, dict) else None)
            )
            db_inv.confidence = float(final_state.get("primary_confidence", 0.0))
            db_inv.is_fallback = bool(final_state.get("is_fallback", False))
            db_inv.model_provider = final_state.get("llm_provider", "unknown")
            db_inv.model_name = final_state.get("llm_model")
            db_inv.report_json = rep_data
            db_inv.evidence_json = final_state.get("collected_evidence", [])
            db_inv.completed_at = completed_at

            db.commit()
            db.refresh(db_inv)

            logger.info("Investigation '%s' completed successfully with status: %s", inv_key, db_inv.status)
            return self._to_response(db_inv)

        except Exception as exc:
            db.rollback()
            logger.error("Investigation '%s' execution failed: %s", inv_key, exc)
            db_inv.status = InvestigationStatus.FAILED.value
            db_inv.completed_at = datetime.now(timezone.utc)
            db.commit()
            raise

    def get_investigation(self, db: Session, key_or_id: str) -> Optional[InvestigationResponse]:
        """Retrieve an investigation by key (INV-...) or UUID."""
        query = select(Investigation)
        try:
            val_uuid = uuid.UUID(key_or_id)
            query = query.where(Investigation.id == val_uuid)
        except ValueError:
            query = query.where(Investigation.investigation_key == key_or_id)

        inv = db.execute(query).scalar_one_or_none()
        if not inv:
            return None
        return self._to_response(inv)

    def get_latest_for_incident(self, db: Session, incident_key: str) -> Optional[InvestigationResponse]:
        """Retrieve the most recent investigation report for an incident."""
        inv = db.execute(
            select(Investigation)
            .where(Investigation.incident_key == incident_key)
            .order_by(Investigation.created_at.desc())
        ).scalars().first()

        if not inv:
            return None
        return self._to_response(inv)

    def list_investigations(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        incident_key: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[InvestigationResponse], int]:
        """Retrieve paginated investigations."""
        query: Select = select(Investigation)
        count_query: Select = select(func.count(Investigation.id))

        filters = []
        if incident_key:
            filters.append(Investigation.incident_key == incident_key)
        if status:
            filters.append(Investigation.status == status)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0
        offset = (page - 1) * page_size
        items = list(
            db.execute(
                query.order_by(Investigation.created_at.desc())
                .offset(offset)
                .limit(page_size)
            ).scalars().all()
        )

        return [self._to_response(i) for i in items], total

    @staticmethod
    def _to_response(inv: Investigation) -> InvestigationResponse:
        """Convert SQLAlchemy Investigation model into Pydantic InvestigationResponse."""
        report = None
        if inv.report_json:
            try:
                report = InvestigationReport.model_validate(inv.report_json)
            except Exception as exc:
                logger.warning("Could not validate report_json: %s", exc)

        return InvestigationResponse(
            id=inv.id,
            investigation_key=inv.investigation_key,
            incident_key=inv.incident_key,
            status=InvestigationStatus(inv.status),
            target_service=inv.target_service,
            environment=inv.environment,
            leading_hypothesis=inv.leading_hypothesis,
            confidence=inv.confidence,
            is_fallback=inv.is_fallback,
            model_provider=inv.model_provider,
            model_name=inv.model_name,
            report=report,
            created_at=inv.created_at,
            completed_at=inv.completed_at,
        )
