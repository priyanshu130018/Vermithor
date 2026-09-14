import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.app.retrieval.clients.incident_client import IncidentServiceClient
from backend.app.retrieval.clients.log_intelligence_client import LogIntelligenceClient
from backend.app.retrieval.clients.rca_client import RCAServiceClient
from backend.app.common.config import get_settings
from backend.app.retrieval.repositories.runbook_repository import RunbookRepository
from backend.app.retrieval.retrieval.context_assembler import ContextAssembler
from backend.app.retrieval.retrieval.deduplication import ResultDeduplicator
from backend.app.retrieval.retrieval.ranking import HybridRanker
from backend.app.retrieval.schemas.retrieval import (
    RAGContextRequest,
    RAGContextResponse,
    RetrievalQuery,
    RetrievalResponse,
    RetrievalResultItem,
    SourceType,
)

logger = logging.getLogger(__name__)


class RetrievalEngine:
    """Coordinates multi-source evidence collection, hybrid ranking, deduplication, and context assembly."""

    def __init__(
        self,
        log_client: Optional[LogIntelligenceClient] = None,
        incident_client: Optional[IncidentServiceClient] = None,
        rca_client: Optional[RCAServiceClient] = None,
        ranker: Optional[HybridRanker] = None,
        assembler: Optional[ContextAssembler] = None,
    ):
        self.log_client = log_client or LogIntelligenceClient()
        self.incident_client = incident_client or IncidentServiceClient()
        self.rca_client = rca_client or RCAServiceClient()
        self.ranker = ranker or HybridRanker()
        self.assembler = assembler or ContextAssembler()
        self.settings = get_settings()

    def execute_query(
        self,
        db: Session,
        req: RetrievalQuery,
    ) -> RetrievalResponse:
        """Execute multi-source hybrid search across logs, incidents, RCA reports, and runbooks."""
        target_sources = req.source_types or [
            SourceType.LOG,
            SourceType.INCIDENT,
            SourceType.RCA,
            SourceType.RUNBOOK,
        ]

        query_str = req.query or ""
        collected_items: List[RetrievalResultItem] = []
        warnings: List[str] = []
        sources_attempted = len(target_sources)
        sources_available = 0

        # 1. Retrieve Logs
        if SourceType.LOG in target_sources:
            log_items, warn = self.log_client.search_logs(
                query=query_str,
                top_k=req.top_k,
                service=req.service,
                environment=req.environment,
                severity=req.severity,
                start_time=req.start_time,
                end_time=req.end_time,
            )
            if warn:
                warnings.append(warn)
            else:
                sources_available += 1
            collected_items.extend(log_items)

        # 2. Retrieve Historical Incidents
        if SourceType.INCIDENT in target_sources:
            inc_items, warn = self.incident_client.search_incidents(
                query=query_str,
                service=req.service,
                environment=req.environment,
                severity=req.severity,
                top_k=req.top_k,
            )
            if warn:
                warnings.append(warn)
            else:
                sources_available += 1
            collected_items.extend(inc_items)

        # 3. Retrieve Historical RCA Analyses
        if SourceType.RCA in target_sources:
            rca_items, warn = self.rca_client.search_rca_reports(
                group_key=req.group_key,
                top_k=req.top_k,
            )
            if warn:
                warnings.append(warn)
            else:
                sources_available += 1
            collected_items.extend(rca_items)

        # 4. Retrieve Runbooks
        if SourceType.RUNBOOK in target_sources:
            try:
                rb_items = RunbookRepository.search_runbooks(
                    db=db,
                    query=query_str,
                    top_k=req.top_k,
                    service=req.service,
                )
                collected_items.extend(rb_items)
                sources_available += 1
            except Exception as exc:
                warnings.append(f"Runbook database error: {exc}")

        # 5. Hybrid Scoring
        scored_items = [self.ranker.score_item(item, req) for item in collected_items]

        # 6. Deduplication
        deduped = ResultDeduplicator.deduplicate(scored_items)

        # 7. Sort by final score descending
        deduped.sort(key=lambda x: x.final_score, reverse=True)

        # 8. Minimum score filter if requested
        if req.min_score is not None:
            deduped = [item for item in deduped if item.final_score >= req.min_score]

        top_results = deduped[: req.top_k]

        return RetrievalResponse(
            query=query_str,
            incident_key=req.incident_key,
            total_results=len(top_results),
            sources_attempted=sources_attempted,
            sources_available=sources_available,
            warnings=warnings,
            results=top_results,
        )

    def execute_incident_retrieval(
        self,
        db: Session,
        incident_key: str,
        top_k: int = 5,
    ) -> RetrievalResponse:
        """Collect and rank grounded operational context for a specific incident key."""
        incident = self.incident_client.get_incident(incident_key)
        if not incident:
            return RetrievalResponse(
                query=f"Incident {incident_key}",
                incident_key=incident_key,
                total_results=0,
                sources_attempted=4,
                sources_available=0,
                warnings=[f"Incident '{incident_key}' could not be fetched from Incident Service"],
                results=[],
            )

        # Extract incident context
        service = incident.get("service")
        env = incident.get("environment")
        severity = incident.get("severity")
        title = incident.get("title", "")
        desc = incident.get("description", "")
        query = f"{service or ''} {title} {desc}".strip()

        query_req = RetrievalQuery(
            query=query,
            incident_key=incident_key,
            service=service,
            environment=env,
            severity=severity,
            top_k=top_k,
        )
        return self.execute_query(db=db, req=query_req)

    def assemble_rag_context(
        self,
        db: Session,
        req: RAGContextRequest,
    ) -> RAGContextResponse:
        """Assemble structured RAG context for future LLM summarization."""
        if req.incident_key:
            retrieval_res = self.execute_incident_retrieval(
                db=db,
                incident_key=req.incident_key,
                top_k=req.top_k,
            )
        else:
            query_req = RetrievalQuery(
                query=req.query or "",
                top_k=req.top_k,
                source_types=req.source_types,
            )
            retrieval_res = self.execute_query(db=db, req=query_req)

        included, context_text, is_truncated = self.assembler.assemble(retrieval_res.results)

        return RAGContextResponse(
            query=retrieval_res.query,
            incident_key=req.incident_key,
            total_results=retrieval_res.total_results,
            included_results=len(included),
            truncated=is_truncated,
            warnings=retrieval_res.warnings,
            context=included,
            context_text=context_text,
        )
