import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from backend.app.common.database import Base


class CorrelationGroup(Base):
    """Represents an aggregate group of related observability signals."""

    __tablename__ = "correlation_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    group_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    primary_service: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    correlation_score: Mapped[float] = mapped_column(
        Float,
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        index=True,
        default="CANDIDATE",
        nullable=False,
    )
    reasons: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    incident_key: Mapped[Optional[str]] = mapped_column(
        String(32),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    signals: Mapped[List["CorrelationSignal"]] = relationship(
        "CorrelationSignal",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="CorrelationSignal.timestamp.asc()",
    )

    def __repr__(self) -> str:
        return f"<CorrelationGroup(key='{self.group_key}', service='{self.primary_service}', env='{self.environment}', score={self.correlation_score:.2f}, status='{self.status}')>"


class CorrelationSignal(Base):
    """An individual signal associated with a correlation group with calculated relationship scores."""

    __tablename__ = "correlation_signals"
    __table_args__ = (
        UniqueConstraint("group_id", "signal_id", name="uq_correlation_signals_group_signal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        ForeignKey("correlation_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    signal_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    signal_type: Mapped[str] = mapped_column(
        String(64),
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
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    source_reference: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    relationship_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    relationship_reasons: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    group: Mapped["CorrelationGroup"] = relationship("CorrelationGroup", back_populates="signals")

    def __repr__(self) -> str:
        return f"<CorrelationSignal(id={self.id}, signal_id='{self.signal_id}', type='{self.signal_type}', score={self.relationship_score:.2f})>"
