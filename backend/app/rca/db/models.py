import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship
from sqlalchemy.types import JSON, Uuid

from backend.app.common.database import Base


class RCAAnalysis(Base):
    """Root Cause Analysis report for a specific Correlation Group."""

    __tablename__ = "rca_analyses"
    __table_args__ = (
        UniqueConstraint("group_key", "analysis_version", name="uq_rca_analyses_group_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    group_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    analysis_version: Mapped[str] = mapped_column(
        String(32),
        default="1.0",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        index=True,
        default="PENDING",
        nullable=False,
    )
    primary_root_cause: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    primary_confidence: Mapped[float] = mapped_column(
        Float,
        index=True,
        nullable=False,
    )
    causal_chain: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
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

    candidates: Mapped[List["RootCauseCandidate"]] = orm_relationship(
        "RootCauseCandidate",
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="RootCauseCandidate.rank.asc()",
    )
    edges: Mapped[List["CausalEdge"]] = orm_relationship(
        "CausalEdge",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<RCAAnalysis(key='{self.analysis_key}', group='{self.group_key}', root='{self.primary_root_cause}', conf={self.primary_confidence:.2f})>"


class RootCauseCandidate(Base):
    """Ranked root cause candidate with supporting structured evidence."""

    __tablename__ = "root_cause_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        ForeignKey("rca_analyses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    candidate_type: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    candidate_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(
        Float,
        index=True,
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    evidence: Mapped[List[Dict[str, Any]]] = mapped_column(
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

    analysis: Mapped["RCAAnalysis"] = orm_relationship("RCAAnalysis", back_populates="candidates")

    def __repr__(self) -> str:
        return f"<RootCauseCandidate(name='{self.candidate_name}', type='{self.candidate_type}', score={self.score:.2f}, rank={self.rank})>"


class CausalEdge(Base):
    """Directed edge representing causal propagation from source to target signal."""

    __tablename__ = "causal_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        ForeignKey("rca_analyses.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_signal_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    target_signal_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    relationship: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    evidence: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    analysis: Mapped["RCAAnalysis"] = orm_relationship("RCAAnalysis", back_populates="edges")

    def __repr__(self) -> str:
        return f"<CausalEdge({self.source_signal_id} -> {self.target_signal_id} [{self.relationship}])>"
