import math
from typing import List, Optional, Tuple
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from backend.app.retrieval.db.models import Runbook
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType
from backend.app.retrieval.schemas.runbooks import RunbookCreateRequest, RunbookUpdateRequest


class RunbookRepository:
    """Data access and search operations for the Runbook knowledge base."""

    @staticmethod
    def generate_runbook_key(db: Session) -> str:
        """Generate sequence-backed runbook key (e.g. RB-000001)."""
        count = db.execute(select(func.count(Runbook.id))).scalar() or 0
        return f"RB-{count + 1:06d}"

    @classmethod
    def create(cls, db: Session, req: RunbookCreateRequest) -> Runbook:
        """Create a new runbook in the knowledge base."""
        key = req.runbook_key or cls.generate_runbook_key(db)
        rb = Runbook(
            runbook_key=key,
            title=req.title,
            description=req.description,
            content=req.content,
            service=req.service,
            environment=req.environment,
            category=req.category,
            tags=req.tags or [],
        )
        db.add(rb)
        db.commit()
        db.refresh(rb)
        return rb

    @staticmethod
    def get_by_key(db: Session, runbook_key: str) -> Optional[Runbook]:
        """Fetch a runbook by its key."""
        return db.execute(
            select(Runbook).where(Runbook.runbook_key == runbook_key)
        ).scalar_one_or_none()

    @staticmethod
    def list_runbooks(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        service: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Tuple[List[Runbook], int]:
        """List runbooks with pagination and filters."""
        query: Select = select(Runbook)
        count_query: Select = select(func.count(Runbook.id))

        filters = []
        if service:
            filters.append(Runbook.service == service)
        if category:
            filters.append(Runbook.category == category)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = db.execute(count_query).scalar() or 0
        offset = (page - 1) * page_size
        items = list(
            db.execute(
                query.order_by(Runbook.created_at.desc())
                .offset(offset)
                .limit(page_size)
            ).scalars().all()
        )
        return items, total

    @staticmethod
    def update(db: Session, runbook_key: str, req: RunbookUpdateRequest) -> Optional[Runbook]:
        """Update an existing runbook."""
        rb = RunbookRepository.get_by_key(db, runbook_key)
        if not rb:
            return None

        if req.title is not None:
            rb.title = req.title
        if req.description is not None:
            rb.description = req.description
        if req.content is not None:
            rb.content = req.content
        if req.service is not None:
            rb.service = req.service
        if req.environment is not None:
            rb.environment = req.environment
        if req.category is not None:
            rb.category = req.category
        if req.tags is not None:
            rb.tags = req.tags

        db.commit()
        db.refresh(rb)
        return rb

    @staticmethod
    def delete(db: Session, runbook_key: str) -> bool:
        """Delete a runbook by key."""
        rb = RunbookRepository.get_by_key(db, runbook_key)
        if not rb:
            return False
        db.delete(rb)
        db.commit()
        return True

    CANONICAL_RUNBOOKS = [
        {
            "runbook_key": "RB-000001",
            "title": "Database Connection Pool Exhaustion & Query Timeout",
            "description": "Remediation procedures for PostgreSQL pool exhaustion, transaction lock contention, and connection timeout anomalies.",
            "service": "postgres",
            "category": "DATABASE",
            "tags": ["postgres", "database", "pool", "timeout", "connection", "saturation", "lock"],
            "content": (
                "## Diagnosis:\n"
                "1. Check pg_stat_activity for long-running idle in transaction queries.\n"
                "2. Inspect active vs maximum pool size metrics (db_active_connections).\n"
                "## Immediate Remediation Actions:\n"
                "1. Terminate blocked client queries: SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction';\n"
                "2. Scale connection pool limit in application configuration by 25% if database instance capacity permits.\n"
                "3. Restart misbehaving connection pool holders.\n"
                "## Permanent Fix:\n"
                "Implement strict client timeout thresholds (statement_timeout=30s) and optimize slow queries."
            ),
        },
        {
            "runbook_key": "RB-000002",
            "title": "Redis Cache Failure & Cluster Degradation",
            "description": "Recovery steps for Redis cache outages, network partition, and fallback degradation.",
            "service": "cache-service",
            "category": "CACHE",
            "tags": ["redis", "cache", "cache-service", "connection_refused", "timeout", "cluster"],
            "content": (
                "## Diagnosis:\n"
                "1. Verify Redis cluster node health via redis-cli ping.\n"
                "2. Check cache eviction and memory saturation rates.\n"
                "## Immediate Remediation Actions:\n"
                "1. Enable circuit breakers on downstream clients to prevent database overwhelm.\n"
                "2. Restart failed Redis sentinel / replica nodes.\n"
                "3. Flush transient corrupted keys if memory threshold exceeded: redis-cli FLUSHDB ASYNC.\n"
                "## Permanent Fix:\n"
                "Provision dedicated read-replicas and increase maxmemory policy to allkeys-lru."
            ),
        },
        {
            "runbook_key": "RB-000003",
            "title": "High Memory Usage & JVM/Container OOM Mitigation",
            "description": "Steps to resolve memory exhaustion, aggressive garbage collection pauses, and kernel OOM termination.",
            "service": "catalog-api",
            "category": "RESOURCE",
            "tags": ["memory", "oom", "heap", "garbage", "gc", "resource", "jvm", "leak"],
            "content": (
                "## Diagnosis:\n"
                "1. Inspect JVM heap / container memory consumption graphs.\n"
                "2. Analyze GC pause duration and thread allocation bottlenecks.\n"
                "## Immediate Remediation Actions:\n"
                "1. Temporarily restart leaking service pods to release uncollected heap memory.\n"
                "2. Increase container memory limits (spec.resources.limits.memory) by 50% in deployment manifests.\n"
                "## Permanent Fix:\n"
                "Capture heap dump (jmap) to identify object allocation leaks and tune GC collector."
            ),
        },
        {
            "runbook_key": "RB-000004",
            "title": "Faulty Deployment Rollback & Feature Flag Disablement",
            "description": "Procedures for rolling back breaking releases and isolating regressions.",
            "service": "booking-api",
            "category": "DEPLOYMENT",
            "tags": ["deployment", "release", "5xx", "rollback", "version", "exception", "regression"],
            "content": (
                "## Diagnosis:\n"
                "1. Compare error rates and latency before and after deployment timestamp.\n"
                "2. Inspect stack traces for newly introduced exceptions in recently deployed commit.\n"
                "## Immediate Remediation Actions:\n"
                "1. Execute zero-downtime rollback: kubectl rollout undo deployment/<service-name>.\n"
                "2. Disable active feature flags introduced in the release via config management.\n"
                "## Permanent Fix:\n"
                "Patch regression in staging, add integration tests covering failure path, and re-deploy."
            ),
        },
        {
            "runbook_key": "RB-000005",
            "title": "High CPU Utilization & Thread Starvation",
            "description": "Mitigating thread pool exhaustion and CPU spikes.",
            "service": "worker-service",
            "category": "INFRASTRUCTURE",
            "tags": ["cpu", "load", "thread", "starvation", "worker", "saturation"],
            "content": (
                "## Diagnosis:\n"
                "1. Check CPU load average and top worker thread utilization.\n"
                "## Immediate Remediation Actions:\n"
                "1. Scale replica count: kubectl scale deployment/<service-name> --replicas=+3.\n"
                "2. Throttle background batch processing worker ingestion rate.\n"
                "## Permanent Fix:\n"
                "Profile hot execution paths and introduce asynchronous task offloading."
            ),
        },
    ]

    @classmethod
    def seed_canonical_runbooks(cls, db: Session) -> None:
        """Ensure canonical operational runbooks are populated in database if empty."""
        count = db.execute(select(func.count(Runbook.id))).scalar() or 0
        if count == 0:
            for rb_data in cls.CANONICAL_RUNBOOKS:
                rb = Runbook(
                    runbook_key=rb_data["runbook_key"],
                    title=rb_data["title"],
                    description=rb_data["description"],
                    content=rb_data["content"],
                    service=rb_data["service"],
                    environment="production",
                    category=rb_data["category"],
                    tags=rb_data["tags"],
                )
                db.add(rb)
            try:
                db.commit()
            except Exception:
                db.rollback()

    @classmethod
    def search_runbooks(
        cls,
        db: Session,
        query: str,
        top_k: int = 5,
        service: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[RetrievalResultItem]:
        """Search runbooks using keyword and metadata matching."""
        terms = [t.strip().lower() for t in query.split() if len(t.strip()) > 1]
        all_rbs = db.execute(select(Runbook)).scalars().all()

        if not all_rbs:
            cls.seed_canonical_runbooks(db)
            all_rbs = db.execute(select(Runbook)).scalars().all()

        scored_rbs: List[Tuple[Runbook, float]] = []

        for rb in all_rbs:
            # Metadata filter checks
            if service and rb.service and rb.service.lower() != service.lower():
                continue
            if category and rb.category and rb.category.lower() != category.lower():
                continue

            text_blob = f"{rb.title} {rb.description or ''} {rb.content} {' '.join(rb.tags or [])}".lower()
            term_matches = sum(1 for t in terms if t in text_blob)
            score = 0.50 + (0.50 * (term_matches / max(1, len(terms)))) if term_matches > 0 else 0.30

            scored_rbs.append((rb, score))

        scored_rbs.sort(key=lambda x: x[1], reverse=True)

        results: List[RetrievalResultItem] = []
        for rb, score in scored_rbs[:top_k]:
            results.append(
                RetrievalResultItem(
                    source_type=SourceType.RUNBOOK,
                    source_id=rb.runbook_key,
                    title=rb.title,
                    content=rb.content,
                    service=rb.service,
                    environment=rb.environment,
                    timestamp=rb.updated_at,
                    similarity_score=round(score, 4),
                    citation=f"[RUNBOOK:{rb.runbook_key}]",
                    metadata={"category": rb.category, "tags": rb.tags},
                )
            )
        return results
