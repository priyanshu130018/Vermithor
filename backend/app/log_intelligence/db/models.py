import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from backend.app.common.database import Base


class ProcessedLog(Base):
    """Structured and normalized representation of an observability log event."""

    __tablename__ = "processed_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_event_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    service: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    raw_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    normalized_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    template: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        index=True,
        nullable=True,
    )
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        server_default="{}",
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    embedding: Mapped[Optional["LogEmbedding"]] = relationship(
        "LogEmbedding",
        uselist=False,
        back_populates="log",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ProcessedLog(source_event_id='{self.source_event_id}', service='{self.service}', category='{self.category}')>"


class LogEmbedding(Base):
    """Dense vector embedding for a processed log."""

    __tablename__ = "log_embeddings"
    __table_args__ = (
        UniqueConstraint("log_id", "model_name", "model_version", name="uq_log_embeddings_log_model_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    log_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        ForeignKey("processed_logs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    model_version: Mapped[Optional[str]] = mapped_column(
        String(64),
        default="1.0",
        nullable=True,
    )
    dimension: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    embedding: Mapped[List[float]] = mapped_column(
        Vector(384).with_variant(JSON, "sqlite"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    log: Mapped["ProcessedLog"] = relationship("ProcessedLog", back_populates="embedding")

    def __repr__(self) -> str:
        return f"<LogEmbedding(log_id='{self.log_id}', model='{self.model_name}', dim={self.dimension})>"
