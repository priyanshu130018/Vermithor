import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Float, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.common.database import Base


class MetricObservation(Base):
    """Metric observation recording raw numeric system telemetry."""

    __tablename__ = "metric_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    observation_id: Mapped[str] = mapped_column(
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
    metric_name: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )
    metric_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    unit: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    labels: Mapped[Dict[str, Any]] = mapped_column(
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

    def __repr__(self) -> str:
        return f"<MetricObservation(id={self.id}, obs_id='{self.observation_id}', service='{self.service}', metric='{self.metric_name}', val={self.metric_value})>"


class AnomalyResult(Base):
    """Evaluation output from an anomaly detector on a metric observation."""

    __tablename__ = "anomaly_results"
    __table_args__ = (
        UniqueConstraint("observation_id", "detector", name="uq_anomaly_results_obs_detector"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql"),
        primary_key=True,
        default=uuid.uuid4,
    )
    observation_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    detector: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    detector_version: Mapped[str] = mapped_column(
        String(32),
        default="1.0",
        nullable=False,
    )
    anomaly_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    is_anomaly: Mapped[bool] = mapped_column(
        Boolean,
        index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    expected_value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    deviation: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AnomalyResult(obs_id='{self.observation_id}', detector='{self.detector}', is_anomaly={self.is_anomaly}, score={self.anomaly_score:.2f}, sev='{self.severity}')>"
