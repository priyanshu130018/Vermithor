import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import DateTime, Float, Sequence, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from backend.app.common.database import Base

summary_key_seq = Sequence("summary_key_seq", start=1)


class IncidentSummary(Base):
    """Structured and natural-language summary generated for an operational incident."""

    __tablename__ = "incident_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    summary_key: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    incident_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        default="PENDING",
    )
    summary_version: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        default="1.0",
    )
    model_provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    executive_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    what_happened: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    probable_root_cause: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    impact_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        server_default="{}",
        default=dict,
        nullable=False,
    )
    timeline_json: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        server_default="[]",
        default=list,
        nullable=False,
    )
    evidence_json: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        server_default="[]",
        default=list,
        nullable=False,
    )
    remediation_json: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        server_default="[]",
        default=list,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        index=True,
        default=0.0,
        nullable=False,
    )
    limitations_json: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        server_default="[]",
        default=list,
        nullable=False,
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

    def __repr__(self) -> str:
        return f"<IncidentSummary(summary_key='{self.summary_key}', incident_key='{self.incident_key}', status='{self.status}')>"
