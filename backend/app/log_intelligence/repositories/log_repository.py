import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sqlalchemy import Select, and_, desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.log_intelligence.db.models import LogEmbedding, ProcessedLog


class LogRepository:
    """Data access and vector query operations for logs and embeddings."""

    @staticmethod
    def get_by_id(db: Session, log_id: uuid.UUID) -> Optional[ProcessedLog]:
        """Fetch a processed log by UUID with its embedding metadata."""
        return db.execute(
            select(ProcessedLog)
            .options(selectinload(ProcessedLog.embedding))
            .where(ProcessedLog.id == log_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_by_source_event_id(db: Session, source_event_id: str) -> Optional[ProcessedLog]:
        """Fetch a processed log by its source event ID."""
        return db.execute(
            select(ProcessedLog)
            .options(selectinload(ProcessedLog.embedding))
            .where(ProcessedLog.source_event_id == source_event_id)
        ).scalar_one_or_none()

    @staticmethod
    def save_processed_log(
        db: Session,
        log_data: Dict[str, Any],
    ) -> ProcessedLog:
        """Persist or retrieve existing processed log."""
        source_event_id = log_data["source_event_id"]
        existing = LogRepository.get_by_source_event_id(db, source_event_id)
        if existing:
            return existing

        log = ProcessedLog(
            source_event_id=source_event_id,
            timestamp=log_data["timestamp"],
            service=log_data["service"],
            environment=log_data["environment"],
            severity=log_data["severity"],
            category=log_data["category"],
            raw_message=log_data["raw_message"],
            normalized_message=log_data["normalized_message"],
            template=log_data["template"],
            trace_id=log_data.get("trace_id"),
            metadata_json=log_data.get("metadata", {}),
        )
        db.add(log)
        db.flush()
        return log

    @staticmethod
    def save_log_embedding(
        db: Session,
        log_id: uuid.UUID,
        model_name: str,
        model_version: str,
        dimension: int,
        embedding: List[float],
    ) -> LogEmbedding:
        """Persist or update a log vector embedding."""
        existing = db.execute(
            select(LogEmbedding).where(
                LogEmbedding.log_id == log_id,
                LogEmbedding.model_name == model_name,
                LogEmbedding.model_version == model_version,
            )
        ).scalar_one_or_none()

        if existing:
            existing.embedding = embedding
            db.flush()
            return existing

        emb_record = LogEmbedding(
            log_id=log_id,
            model_name=model_name,
            model_version=model_version,
            dimension=dimension,
            embedding=embedding,
        )
        db.add(emb_record)
        db.flush()
        return emb_record

    @classmethod
    def search_vector_similarity(
        cls,
        db: Session,
        query_vector: List[float],
        top_k: int = 5,
        service: Optional[str] = None,
        environment: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        min_similarity: Optional[float] = None,
        exclude_log_id: Optional[uuid.UUID] = None,
    ) -> List[Tuple[ProcessedLog, float]]:
        """
        Execute filtered semantic similarity search against log embeddings.

        Returns:
            List[Tuple[ProcessedLog, float]]: List of (ProcessedLog, similarity_score)
        """
        dialect = db.get_bind().dialect.name

        # PostgreSQL pgvector native query
        if dialect == "postgresql":
            # pgvector distance operator: <=> is cosine distance
            cosine_dist = LogEmbedding.embedding.cosine_distance(query_vector)
            similarity_expr = (1.0 - cosine_dist).label("similarity")

            query = (
                select(ProcessedLog, similarity_expr)
                .join(LogEmbedding, ProcessedLog.id == LogEmbedding.log_id)
            )

            filters = []
            if service:
                filters.append(ProcessedLog.service == service)
            if environment:
                filters.append(ProcessedLog.environment == environment)
            if severity:
                filters.append(ProcessedLog.severity == severity)
            if category:
                filters.append(ProcessedLog.category == category)
            if start_time:
                filters.append(ProcessedLog.timestamp >= start_time)
            if end_time:
                filters.append(ProcessedLog.timestamp <= end_time)
            if exclude_log_id:
                filters.append(ProcessedLog.id != exclude_log_id)
            if min_similarity is not None:
                filters.append(similarity_expr >= min_similarity)

            if filters:
                query = query.where(and_(*filters))

            query = query.order_by(desc("similarity")).limit(top_k)
            rows = db.execute(query).all()
            return [(r[0], float(r[1])) for r in rows]

        # SQLite fallback for test environment
        else:
            query = (
                select(ProcessedLog, LogEmbedding)
                .join(LogEmbedding, ProcessedLog.id == LogEmbedding.log_id)
            )
            filters = []
            if service:
                filters.append(ProcessedLog.service == service)
            if environment:
                filters.append(ProcessedLog.environment == environment)
            if severity:
                filters.append(ProcessedLog.severity == severity)
            if category:
                filters.append(ProcessedLog.category == category)
            if start_time:
                filters.append(ProcessedLog.timestamp >= start_time)
            if end_time:
                filters.append(ProcessedLog.timestamp <= end_time)
            if exclude_log_id:
                filters.append(ProcessedLog.id != exclude_log_id)

            if filters:
                query = query.where(and_(*filters))

            rows = db.execute(query).all()
            if not rows:
                return []

            q_vec = np.array(query_vector, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            if q_norm == 0:
                q_norm = 1.0

            results: List[Tuple[ProcessedLog, float]] = []
            for log_item, emb_item in rows:
                v = emb_item.embedding
                if isinstance(v, list):
                    db_vec = np.array(v, dtype=np.float32)
                else:
                    db_vec = np.array(list(v), dtype=np.float32)

                v_norm = np.linalg.norm(db_vec)
                if v_norm == 0:
                    v_norm = 1.0

                sim = float(np.dot(q_vec, db_vec) / (q_norm * v_norm))
                if min_similarity is not None and sim < min_similarity:
                    continue
                results.append((log_item, sim))

            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

    @classmethod
    def get_logs_for_clustering(
        cls,
        db: Session,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        service: Optional[str] = None,
        environment: Optional[str] = None,
        limit: int = 2000,
    ) -> List[Tuple[ProcessedLog, List[float]]]:
        """
        Fetch processed logs with their corresponding vector embeddings for clustering analysis.
        """
        query = (
            select(ProcessedLog, LogEmbedding)
            .join(LogEmbedding, ProcessedLog.id == LogEmbedding.log_id)
        )
        filters = []
        if start_time:
            filters.append(ProcessedLog.timestamp >= start_time)
        if end_time:
            filters.append(ProcessedLog.timestamp <= end_time)
        if service:
            filters.append(ProcessedLog.service == service)
        if environment:
            filters.append(ProcessedLog.environment == environment)

        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(desc(ProcessedLog.timestamp)).limit(limit)
        rows = db.execute(query).all()

        results: List[Tuple[ProcessedLog, List[float]]] = []
        for log_item, emb_item in rows:
            v = emb_item.embedding
            if isinstance(v, list):
                vec = [float(x) for x in v]
            else:
                vec = [float(x) for x in list(v)]
            results.append((log_item, vec))
        return results
