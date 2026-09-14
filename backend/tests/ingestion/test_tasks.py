from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from unittest.mock import patch

from backend.app.ingestion.db.models import Event
from backend.app.ingestion.services.task_publisher import TaskPublisher
from backend.app.ingestion.workers.tasks import process_event


def test_process_event_task_lifecycle(db_session: Session):
    """Test Celery task execution transitions event state from PENDING to PROCESSED."""
    # Seed an event with PENDING status
    event = Event(
        event_id="evt-task-001",
        timestamp=datetime.now(timezone.utc),
        service="payment-service",
        environment="production",
        event_type="LOG",
        severity="ERROR",
        message="Payment gateway timed out",
        trace_id="trace-task-01",
        metadata_json={"gateway": "stripe"},
        processing_status="PENDING",
    )
    db_session.add(event)
    db_session.commit()

    # Execute task
    result = process_event("evt-task-001")
    assert result["status"] == "processed"
    assert result["event_id"] == "evt-task-001"

    # Verify event state in database
    db_session.expire_all()
    updated_event = db_session.execute(
        select(Event).where(Event.event_id == "evt-task-001")
    ).scalar_one()

    assert updated_event.processing_status == "PROCESSED"
    assert updated_event.processed_at is not None
    assert updated_event.processing_error is None


def test_process_event_task_idempotency(db_session: Session):
    """Test that running process_event on an already PROCESSED event is idempotent."""
    processed_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
    event = Event(
        event_id="evt-task-idempotent",
        timestamp=datetime.now(timezone.utc),
        service="checkout-service",
        environment="production",
        event_type="ALERT",
        severity="CRITICAL",
        message="Checkout failure spike",
        metadata_json={},
        processing_status="PROCESSED",
        processed_at=processed_time,
    )
    db_session.add(event)
    db_session.commit()

    # Run task second time
    result = process_event("evt-task-idempotent")
    assert result["status"] == "already_processed"

    # Verify state remains untouched
    db_session.expire_all()
    queried = db_session.execute(
        select(Event).where(Event.event_id == "evt-task-idempotent")
    ).scalar_one()
    assert queried.processing_status == "PROCESSED"
    assert queried.processed_at is not None
    # Compare date components ignoring SQLite timezone stripping
    assert queried.processed_at.year == processed_time.year
    assert queried.processed_at.month == processed_time.month
    assert queried.processed_at.day == processed_time.day


def test_process_event_task_not_found():
    """Test that processing a non-existent event ID returns not_found without failing."""
    result = process_event("non-existent-event-id-999")
    assert result["status"] == "not_found"


def test_process_event_task_failure(db_session: Session):
    """Test that unexpected errors during processing set the status to FAILED and record the error."""
    event = Event(
        event_id="evt-task-fail-001",
        timestamp=datetime.now(timezone.utc),
        service="orders-service",
        environment="production",
        event_type="METRIC",
        severity="WARNING",
        message="High memory usage",
        metadata_json={},
        processing_status="PENDING",
    )
    db_session.add(event)
    db_session.commit()

    # Simulate an unhandled exception inside the processing block by failing datetime.now
    with patch("backend.app.ingestion.workers.tasks.datetime") as mock_dt:
        mock_dt.now.side_effect = RuntimeError("Simulated worker processing failure")
        try:
            process_event("evt-task-fail-001")
        except Exception:
            pass

    # Verify failure record in database
    db_session.expire_all()
    failed_event = db_session.execute(
        select(Event).where(Event.event_id == "evt-task-fail-001")
    ).scalar_one()

    assert failed_event.processing_status == "FAILED"
    assert failed_event.processing_error is not None
    assert "RuntimeError" in failed_event.processing_error


def test_task_publisher_dispatch():
    """Test TaskPublisher publishes task successfully."""
    success = TaskPublisher.publish_event_processing("evt-pub-001")
    assert success is True


def test_task_publisher_redis_down_resilience():
    """Test that TaskPublisher gracefully handles broker disconnections."""
    with patch("backend.app.ingestion.workers.tasks.process_event.delay", side_effect=ConnectionError("Redis connection refused")):
        success = TaskPublisher.publish_event_processing("evt-pub-fail-001")
        assert success is False
