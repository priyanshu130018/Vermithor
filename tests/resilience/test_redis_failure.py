import pytest
from unittest.mock import patch
from backend.app.ingestion.services.task_publisher import TaskPublisher


def test_task_publisher_redis_failure_handled_gracefully():
    """Verify that Ingestion Service TaskPublisher handles broker disconnections safely without crashing."""
    with patch("backend.app.ingestion.workers.tasks.process_event.delay", side_effect=ConnectionError("Redis connection refused")):
        success = TaskPublisher.publish_event_processing("evt-resilience-fail-001")
        assert success is False, "TaskPublisher should return False on broker failure rather than raising uncaught exception"
