from datetime import datetime, timezone
import json
import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from backend.app.common.config import Settings, get_settings
from backend.app.common.telemetry import (
    RAG_RETRIEVAL_DURATION_SECONDS,
    RAG_RETRIEVAL_TOTAL,
    SUMMARY_GENERATION_DURATION_SECONDS,
    SUMMARY_GENERATION_TOTAL,
)
from backend.app.summary.clients.incident_client import IncidentClient
from backend.app.summary.clients.rca_client import RCAClient
from backend.app.summary.clients.retrieval_client import RetrievalClient
from backend.app.summary.db.models import IncidentSummary, summary_key_seq
from backend.app.summary.llm.base import LLMProvider
from backend.app.summary.llm.factory import ProviderFactory
from backend.app.summary.prompts.incident_summary import IncidentSummaryPromptBuilder
from backend.app.summary.schemas.summaries import (
    EvidenceItemSchema,
    ImpactSchema,
    IncidentSummaryGeneratedSchema,
    IncidentSummaryResponse,
    RemediationItemSchema,
    SummaryStatus,
    TimelineItemSchema,
)
from backend.app.summary.services.evidence_validator import EvidenceValidator

logger = logging.getLogger(__name__)


def _to_response_model(s: IncidentSummary, debug_rag_info: Optional[Dict[str, Any]] = None, is_fallback: bool = False) -> IncidentSummaryResponse:
    impact_data = s.impact_json or {}
    return IncidentSummaryResponse(
        id=s.id,
        summary_key=s.summary_key,
        incident_key=s.incident_key,
        status=SummaryStatus(s.status),
        summary_version=s.summary_version,
        model_provider=s.model_provider,
        model_name=s.model_name,
        executive_summary=s.executive_summary,
        what_happened=s.what_happened,
        probable_root_cause=s.probable_root_cause,
        impact=ImpactSchema.model_validate(impact_data),
        timeline=[TimelineItemSchema.model_validate(t) for t in (s.timeline_json or [])],
        evidence=[EvidenceItemSchema.model_validate(e) for e in (s.evidence_json or [])],
        remediation=[RemediationItemSchema.model_validate(r) for r in (s.remediation_json or [])],
        confidence=s.confidence,
        limitations=s.limitations_json or [],
        similar_incidents=(s.evidence_json or []),  # or extracted similar incidents
        uncertainty="High uncertainty: isolated symptoms observed without identifiable root cause" if s.confidence < 0.40 else None,
        is_fallback=is_fallback or (s.model_provider == "fallback"),
        debug_rag_info=debug_rag_info,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


class IncidentSummaryService:
    """Coordinates multi-service context fetching, prompt construction, LLM generation, validation, and persistence."""

    def __init__(
        self,
        incident_client: Optional[IncidentClient] = None,
        rca_client: Optional[RCAClient] = None,
        retrieval_client: Optional[RetrievalClient] = None,
        llm_provider: Optional[LLMProvider] = None,
        settings: Optional[Settings] = None,
    ):
        self.incident_client = incident_client or IncidentClient()
        self.rca_client = rca_client or RCAClient()
        self.retrieval_client = retrieval_client or RetrievalClient()
        self.settings = settings or get_settings()
        self._llm_provider = llm_provider

    @property
    def llm_provider(self) -> LLMProvider:
        if self._llm_provider is not None:
            return self._llm_provider
        return ProviderFactory.get_provider(self.settings)

    def generate_summary_key(self, db: Session) -> str:
        """Generate sequence key (e.g. SUM-000001)."""
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            next_val = db.execute(summary_key_seq).scalar()
        else:
            count = db.execute(select(func.count(IncidentSummary.id))).scalar() or 0
            next_val = count + 1
        return f"SUM-{next_val:06d}"

    def generate_summary_for_incident(
        self,
        db: Session,
        incident_key: str,
        regenerate: bool = False,
        allow_fallback: Optional[bool] = None,
    ) -> IncidentSummaryResponse:
        """Generate or retrieve grounded natural-language incident summary."""
        start_time = time.perf_counter()
        use_fallback = self.settings.LLM_FALLBACK_ENABLED if allow_fallback is None else allow_fallback

        # 1. Check idempotency
        existing = db.execute(
            select(IncidentSummary).where(
                IncidentSummary.incident_key == incident_key,
                IncidentSummary.summary_version == self.settings.SUMMARY_VERSION,
                IncidentSummary.status == "COMPLETED",
            )
        ).scalar_one_or_none()

        if existing and not regenerate:
            logger.info("Returning existing completed summary '%s' for incident '%s'", existing.summary_key, incident_key)
            return _to_response_model(existing)

        # 2. Fetch Incident Context from Incident Service
        incident = self.incident_client.get_incident(incident_key)
        if not incident:
            raise ValueError(f"Incident with key '{incident_key}' not found in Incident Service")

        # 3. Fetch RCA Reports from RCA Service
        rca_reports = self.rca_client.get_rca_reports(top_k=1)
        rca = rca_reports[0] if rca_reports else None

        # 4. Fetch Grounded RAG Context from Retrieval Service
        rag_start = time.perf_counter()
        rag_context = self.retrieval_client.get_rag_context(incident_key=incident_key, top_k=10)
        rag_duration = time.perf_counter() - rag_start
        RAG_RETRIEVAL_DURATION_SECONDS.labels(status="success").observe(rag_duration)
        RAG_RETRIEVAL_TOTAL.labels(source_type="all", status="success").inc()

        # Extract debug RAG info
        debug_rag_info = {
            "retrieved_documents": [
                {
                    "source_id": item.get("source_id"),
                    "source_type": item.get("source_type"),
                    "title": item.get("title"),
                    "similarity_score": item.get("similarity_score"),
                    "final_score": item.get("final_score"),
                }
                for item in (rag_context.get("context", []) if rag_context else [])
            ],
            "total_retrieved": len(rag_context.get("context", [])) if rag_context else 0,
        }

        # 5. Build Grounded Prompt
        prompt = IncidentSummaryPromptBuilder.build_prompt(
            incident=incident,
            rca=rca,
            rag_context=rag_context,
        )

        # 6. Create or update summary record in GENERATING state
        summary_key = existing.summary_key if (existing and regenerate) else self.generate_summary_key(db)
        summary_record = existing if (existing and regenerate) else IncidentSummary(
            summary_key=summary_key,
            incident_key=incident_key,
            status="GENERATING",
            summary_version=self.settings.SUMMARY_VERSION,
            model_provider=self.llm_provider.get_provider_name(),
            model_name=self.llm_provider.get_model_name(),
        )

        if not (existing and regenerate):
            db.add(summary_record)
            db.commit()
            db.refresh(summary_record)

        # 7. Invoke LLM Provider with Safe Grounded Fallback
        try:
            raw_response = self.llm_provider.generate(prompt)
            parsed_json = self._parse_json(raw_response)
            validated_schema = IncidentSummaryGeneratedSchema.model_validate(parsed_json)

            # 8. Multi-Point Evidence Validation
            # Root Cause Alignment
            aligned_cause, cause_warn = EvidenceValidator.validate_root_cause(
                validated_schema.probable_root_cause,
                rca,
            )

            # Affected Services Validation
            impact_svcs = validated_schema.impact.services if validated_schema.impact else []
            valid_svcs, svc_warns = EvidenceValidator.validate_affected_services(
                impact_svcs,
                incident,
                rca,
            )
            validated_schema.impact.services = valid_svcs

            # Citation & Evidence ID Validation
            valid_source_ids = EvidenceValidator.extract_valid_source_ids(rag_context, rca)
            filtered_evidence, ev_warns = EvidenceValidator.validate_and_filter_evidence(
                validated_schema.evidence,
                valid_source_ids,
            )

            # Remediation Validation
            valid_remediation, rem_warns = EvidenceValidator.validate_remediations(
                validated_schema.remediation,
                rag_context,
            )

            # Combine warnings into limitations
            all_warnings = [w for w in [cause_warn] + svc_warns + ev_warns + rem_warns if w]
            limitations = validated_schema.limitations + all_warnings

            # RCA structured confidence takes strict precedence
            if rca:
                structured_conf = float(rca.get("primary_confidence", validated_schema.confidence))
            else:
                structured_conf = float(validated_schema.confidence)

            # 9. Update summary record as COMPLETED
            summary_record.status = "COMPLETED"
            summary_record.executive_summary = validated_schema.executive_summary
            summary_record.what_happened = validated_schema.what_happened
            summary_record.probable_root_cause = aligned_cause
            summary_record.impact_json = validated_schema.impact.model_dump()
            summary_record.timeline_json = [t.model_dump() for t in validated_schema.timeline]
            summary_record.evidence_json = [e.model_dump() for e in filtered_evidence]
            summary_record.remediation_json = [r.model_dump() for r in valid_remediation]
            summary_record.confidence = round(structured_conf, 4)
            summary_record.limitations_json = limitations

            duration = time.perf_counter() - start_time
            SUMMARY_GENERATION_DURATION_SECONDS.labels(
                provider=self.llm_provider.get_provider_name(),
                status="success",
            ).observe(duration)
            SUMMARY_GENERATION_TOTAL.labels(
                provider=self.llm_provider.get_provider_name(),
                status="success",
            ).inc()

            db.commit()
            db.refresh(summary_record)
            return _to_response_model(summary_record, debug_rag_info=debug_rag_info, is_fallback=False)

        except TimeoutError as exc:
            if not use_fallback:
                logger.error("Summary generation timed out for incident '%s': %s", incident_key, exc)
                summary_record.status = "FAILED"
                summary_record.executive_summary = f"Summary generation timed out: {exc}"
                db.commit()
                db.refresh(summary_record)
                raise exc

            logger.warning("LLM generation timed out (%s), activating deterministic grounded fallback", exc)
            return self._apply_fallback(db, summary_record, incident, rca, rag_context, debug_rag_info, start_time, exc)

        except Exception as exc:
            if not use_fallback:
                logger.error("Summary generation failed for incident '%s': %s", incident_key, exc)
                summary_record.status = "FAILED"
                summary_record.executive_summary = f"Summary generation failed: {exc}"
                db.commit()
                db.refresh(summary_record)
                raise RuntimeError(f"Incident summary generation failed: {exc}") from exc

            logger.warning("LLM generation failed (%s), activating deterministic grounded fallback", exc)
            return self._apply_fallback(db, summary_record, incident, rca, rag_context, debug_rag_info, start_time, exc)

    def _apply_fallback(
        self,
        db: Session,
        summary_record: IncidentSummary,
        incident: Dict[str, Any],
        rca: Optional[Dict[str, Any]],
        rag_context: Optional[Dict[str, Any]],
        debug_rag_info: Optional[Dict[str, Any]],
        start_time: float,
        exc: Exception,
    ) -> IncidentSummaryResponse:
        """Applies deterministic grounded fallback schema to summary record."""
        fallback_schema = self._build_deterministic_fallback(incident, rca, rag_context)
        summary_record.status = "COMPLETED"
        summary_record.model_provider = "fallback"
        summary_record.model_name = "deterministic_rules"
        summary_record.executive_summary = fallback_schema.executive_summary
        summary_record.what_happened = fallback_schema.what_happened
        summary_record.probable_root_cause = fallback_schema.probable_root_cause
        summary_record.impact_json = fallback_schema.impact.model_dump()
        summary_record.timeline_json = [t.model_dump() for t in fallback_schema.timeline]
        summary_record.evidence_json = [e.model_dump() for e in fallback_schema.evidence]
        summary_record.remediation_json = [r.model_dump() for r in fallback_schema.remediation]
        summary_record.confidence = round(fallback_schema.confidence, 4)
        summary_record.limitations_json = fallback_schema.limitations + [f"Synthesized via deterministic fallback: {str(exc)[:100]}"]

        duration = time.perf_counter() - start_time
        SUMMARY_GENERATION_DURATION_SECONDS.labels(provider="fallback", status="fallback").observe(duration)
        SUMMARY_GENERATION_TOTAL.labels(provider="fallback", status="fallback").inc()

        db.commit()
        db.refresh(summary_record)
        return _to_response_model(summary_record, debug_rag_info=debug_rag_info, is_fallback=True)

    def _build_deterministic_fallback(
        self,
        incident: Dict[str, Any],
        rca: Optional[Dict[str, Any]],
        rag_context: Optional[Dict[str, Any]],
    ) -> IncidentSummaryGeneratedSchema:
        """Builds structured, grounded fallback when LLM provider is unavailable."""
        inc_title = incident.get("title", "Operational Incident")
        service = incident.get("service", "platform")
        severity = incident.get("severity", "MEDIUM")

        if rca:
            root_cause = rca.get("primary_root_cause", "Insufficient evidence")
            conf = float(rca.get("primary_confidence", 0.50))
        else:
            root_cause = "Investigation in progress"
            conf = 0.30

        what_happened = f"Incident '{inc_title}' detected on service '{service}' with severity '{severity}'."

        evidence_list: List[EvidenceItemSchema] = []
        if rca:
            evidence_list.append(
                EvidenceItemSchema(
                    evidence_id="E1",
                    claim=f"Deterministic RCA identified '{root_cause}' with confidence {conf:.2f}.",
                    source_type="RCA",
                    source_id=rca.get("analysis_key", "RCA-UNKNOWN"),
                    support=f"Identified {len(rca.get('candidates', []))} causal candidates.",
                )
            )

        # Grounded remediation from canonical runbook or fallback
        remediation_list: List[RemediationItemSchema] = []
        if "database" in root_cause.lower() or "postgres" in root_cause.lower():
            remediation_list.append(
                RemediationItemSchema(
                    action="Inspect pg_stat_activity and scale connection pool limit in application configuration.",
                    priority="HIGH",
                    reason="Grounded in Database Connection Pool Exhaustion runbook (RB-000001).",
                )
            )
        elif "redis" in root_cause.lower() or "cache" in root_cause.lower():
            remediation_list.append(
                RemediationItemSchema(
                    action="Verify Redis sentinel health and flush corrupted keys if memory threshold exceeded.",
                    priority="HIGH",
                    reason="Grounded in Redis Cache Failure runbook (RB-000002).",
                )
            )
        elif "deployment" in root_cause.lower():
            remediation_list.append(
                RemediationItemSchema(
                    action="Execute rollback via kubectl rollout undo and disable active feature flags.",
                    priority="HIGH",
                    reason="Grounded in Faulty Deployment Rollback runbook (RB-000004).",
                )
            )
        else:
            remediation_list.append(
                RemediationItemSchema(
                    action="Review component error logs and metrics to stabilize service.",
                    priority="MEDIUM",
                    reason="Standard operational triage procedure.",
                )
            )

        return IncidentSummaryGeneratedSchema(
            executive_summary=f"{inc_title}: {root_cause} observed on {service}.",
            what_happened=what_happened,
            probable_root_cause=root_cause,
            impact=ImpactSchema(services=[service], severity=severity, description=f"Impacted {service}"),
            timeline=[
                TimelineItemSchema(
                    timestamp=incident.get("started_at"),
                    event=f"Incident opened: {inc_title}",
                    source=f"[INCIDENT:{incident.get('incident_key', 'UNKNOWN')}]",
                )
            ],
            evidence=evidence_list,
            remediation=remediation_list,
            confidence=conf,
            limitations=["Fallback mode active: generated via deterministic rules engine."],
        )

    def _parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from LLM response string."""
        raw_text = raw_text.strip()
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # Regex search for outermost JSON object
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"LLM did not return valid JSON structure: {raw_text[:200]}")

    def get_by_key(self, db: Session, summary_key: str) -> Optional[IncidentSummaryResponse]:
        """Fetch summary by unique key."""
        s = db.execute(
            select(IncidentSummary).where(IncidentSummary.summary_key == summary_key)
        ).scalar_one_or_none()
        return _to_response_model(s) if s else None

    def list_summaries(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        incident_key: Optional[str] = None,
        status: Optional[str] = None,
        min_confidence: Optional[float] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[IncidentSummaryResponse], int]:
        """List summaries with pagination and filtering."""
        query: Select = select(IncidentSummary)
        count_query: Select = select(func.count(IncidentSummary.id))

        filters = []
        if incident_key:
            filters.append(IncidentSummary.incident_key == incident_key)
        if status:
            filters.append(IncidentSummary.status == status)
        if min_confidence is not None:
            filters.append(IncidentSummary.confidence >= min_confidence)
        if start_time:
            filters.append(IncidentSummary.created_at >= start_time)
        if end_time:
            filters.append(IncidentSummary.created_at <= end_time)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0
        offset = (page - 1) * page_size
        items = list(
            db.execute(
                query.order_by(IncidentSummary.created_at.desc())
                .offset(offset)
                .limit(page_size)
            ).scalars().all()
        )
        return [_to_response_model(s) for s in items], total
