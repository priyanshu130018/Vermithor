import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.database import Base


class Event(Base):
    """Canonical Event model for observability signals with async processing lifecycle."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
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
    event_type: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
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
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Asynchronous processing lifecycle fields
    processing_status: Mapped[str] = mapped_column(
        String(32),
        index=True,
        default="PENDING",
        server_default="PENDING",
        nullable=False,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processing_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, event_id='{self.event_id}', service='{self.service}', type='{self.event_type}', status='{self.processing_status}')>"
