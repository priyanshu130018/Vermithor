import logging
from backend.app.ingestion.workers.tasks import process_event

logger = logging.getLogger(__name__)


class TaskPublisher:
    """
    Publisher abstraction responsible for dispatching asynchronous processing jobs.

    This abstraction decouples domain and event services from the underlying broker,
    providing a seamless future migration path to Kafka or other message streams.
    """

    @staticmethod
    def publish_event_processing(event_id: str) -> bool:
        """
        Publish an event processing task to the Celery broker.

        Returns:
            bool: True if the task was successfully queued, False if broker is unreachable.
        """
        try:
            logger.info("Dispatching async processing task for event_id='%s'", event_id)
            process_event.delay(event_id=event_id)
            return True
        except Exception as exc:
            # Fault-tolerant: log warning without failing the ingestion persistence
            logger.warning(
                "Failed to queue Celery processing task for event_id='%s' (Broker may be unavailable): %s",
                event_id,
                str(exc),
            )
            return False
