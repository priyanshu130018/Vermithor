import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from backend.app.ingestion.db.models import Event


def test_create_event_success(client: TestClient):
    """Test successful event ingestion via POST /api/v1/events."""
    payload = {
        "event_id": "evt-test-001",
        "timestamp": "2026-08-27T15:00:00Z",
        "service": "booking-api",
        "environment": "production",
        "event_type": "LOG",
        "severity": "ERROR",
        "message": "database connection timeout",
        "trace_id": "trace-001",
        "metadata": {
            "host": "booking-api-01",
            "region": "ap-south-1"
        }
    }
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["event_id"] == "evt-test-001"
    assert data["service"] == "booking-api"
    assert data["environment"] == "production"
    assert data["event_type"] == "LOG"
    assert data["severity"] == "ERROR"
    assert data["message"] == "database connection timeout"
    assert data["trace_id"] == "trace-001"
    assert data["metadata"]["host"] == "booking-api-01"
    assert data["metadata"]["region"] == "ap-south-1"
    assert "created_at" in data
    # In eager test mode, Celery task executes immediately to PROCESSED
    assert data["processing_status"] in ["PENDING", "PROCESSED"]


def test_duplicate_event_handling(client: TestClient, db_session: Session):
    """Test that submitting duplicate event_id is idempotent and creates only one DB record."""
    payload = {
        "event_id": "evt-dup-001",
        "timestamp": "2026-08-27T15:00:00Z",
        "service": "payment-service",
        "environment": "staging",
        "event_type": "ALERT",
        "severity": "CRITICAL",
        "message": "High latency detected on checkout endpoint",
        "trace_id": "trace-dup-01",
        "metadata": {"threshold_ms": 5000}
    }

    # First POST -> 201 Created
    response1 = client.post("/api/v1/events", json=payload)
    assert response1.status_code == 201
    data1 = response1.json()

    # Second POST with identical event_id -> 200 OK (idempotent)
    response2 = client.post("/api/v1/events", json=payload)
    assert response2.status_code == 200
    data2 = response2.json()

    # The returned IDs must be identical
    assert data1["id"] == data2["id"]
    assert data1["event_id"] == data2["event_id"]

    # Verify directly in the DB that only 1 record exists
    count = db_session.execute(
        select(func.count(Event.id)).where(Event.event_id == "evt-dup-001")
    ).scalar()
    assert count == 1


@pytest.mark.parametrize(
    "invalid_payload,expected_error_field",
    [
        (
            {
                "event_id": "evt-inv-1",
                "timestamp": "2026-08-27T15:00:00Z",
                "service": "auth-service",
                "environment": "production",
                "event_type": "INVALID_TYPE",  # Invalid event type
                "severity": "ERROR",
                "message": "Invalid type test",
            },
            "event_type",
        ),
        (
            {
                "event_id": "evt-inv-2",
                "timestamp": "2026-08-27T15:00:00Z",
                "service": "auth-service",
                "environment": "production",
                "event_type": "LOG",
                "severity": "UNKNOWN_SEV",  # Invalid severity
                "message": "Invalid severity test",
            },
            "severity",
        ),
        (
            {
                "event_id": "evt-inv-3",
                "timestamp": "2026-08-27T15:00:00Z",
                # missing service
                "environment": "production",
                "event_type": "LOG",
                "severity": "INFO",
                "message": "Missing service test",
            },
            "service",
        ),
        (
            {
                "event_id": "evt-inv-4",
                "timestamp": "2026-08-27T15:00:00Z",
                "service": "auth-service",
                "environment": "production",
                "event_type": "LOG",
                "severity": "INFO",
                # missing message
            },
            "message",
        ),
        (
            {
                "event_id": "evt-inv-5",
                "timestamp": "invalid-timestamp",  # Invalid timestamp format
                "service": "auth-service",
                "environment": "production",
                "event_type": "LOG",
                "severity": "INFO",
                "message": "Invalid timestamp test",
            },
            "timestamp",
        ),
        (
            {
                "event_id": "evt-inv-6",
                "timestamp": "2026-08-27T15:00:00",  # Naive timestamp (no tz)
                "service": "auth-service",
                "environment": "production",
                "event_type": "LOG",
                "severity": "INFO",
                "message": "Naive timestamp test",
            },
            "timestamp",
        ),
    ],
)
def test_create_event_validation_errors(
    client: TestClient,
    invalid_payload: dict,
    expected_error_field: str,
):
    """Test validation errors for schema violations return HTTP 422."""
    response = client.post("/api/v1/events", json=invalid_payload)
    assert response.status_code == 422
    errors = response.json().get("detail", [])
    assert any(expected_error_field in str(err.get("loc", [])) for err in errors)


def test_get_event_by_id(client: TestClient):
    """Test retrieving an event by event_id with processing status."""
    # 1. Non-existent event returns 404
    res_404 = client.get("/api/v1/events/non-existent-event-999")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"].lower()

    # 2. Ingest an event
    payload = {
        "event_id": "evt-fetch-001",
        "timestamp": "2026-08-27T16:30:00Z",
        "service": "inventory-service",
        "environment": "production",
        "event_type": "METRIC",
        "severity": "WARNING",
        "message": "CPU utilization above 85%",
        "trace_id": "trace-fetch-001",
        "metadata": {"cpu_percent": 87.5}
    }
    create_res = client.post("/api/v1/events", json=payload)
    assert create_res.status_code == 201

    # 3. Retrieve event
    res_200 = client.get("/api/v1/events/evt-fetch-001")
    assert res_200.status_code == 200
    fetched = res_200.json()
    assert fetched["event_id"] == "evt-fetch-001"
    assert fetched["service"] == "inventory-service"
    assert fetched["event_type"] == "METRIC"
    assert fetched["severity"] == "WARNING"
    assert fetched["metadata"]["cpu_percent"] == 87.5
    assert "processing_status" in fetched
    assert "processed_at" in fetched


def test_list_events_and_filtering(client: TestClient):
    """Test listing events with filtering and pagination."""
    # Seed events
    events_data = [
        {
            "event_id": f"evt-list-{i}",
            "timestamp": f"2026-08-27T15:{i:02d}:00Z",
            "service": "orders-service" if i % 2 == 0 else "users-service",
            "environment": "production" if i < 3 else "staging",
            "event_type": "DEPLOYMENT" if i == 0 else "LOG",
            "severity": "ERROR" if i % 2 == 0 else "INFO",
            "message": f"Event message {i}",
            "trace_id": f"trace-{i}",
            "metadata": {"index": i}
        }
        for i in range(6)
    ]

    for ev in events_data:
        res = client.post("/api/v1/events", json=ev)
        assert res.status_code == 201

    # 1. Test pagination
    list_res = client.get("/api/v1/events?page=1&page_size=2")
    assert list_res.status_code == 200
    page1 = list_res.json()
    assert page1["total"] == 6
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert page1["total_pages"] == 3
    assert len(page1["items"]) == 2

    # Page 2
    page2_res = client.get("/api/v1/events?page=2&page_size=2")
    page2 = page2_res.json()
    assert len(page2["items"]) == 2
    # Ensure distinct items across pages
    page1_ids = {item["event_id"] for item in page1["items"]}
    page2_ids = {item["event_id"] for item in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)

    # 2. Filter by service
    service_res = client.get("/api/v1/events?service=orders-service")
    assert service_res.status_code == 200
    service_data = service_res.json()
    assert service_data["total"] == 3
    assert all(item["service"] == "orders-service" for item in service_data["items"])

    # 3. Filter by severity
    sev_res = client.get("/api/v1/events?severity=ERROR")
    assert sev_res.status_code == 200
    sev_data = sev_res.json()
    assert sev_data["total"] == 3
    assert all(item["severity"] == "ERROR" for item in sev_data["items"])

    # 4. Filter by event_type
    type_res = client.get("/api/v1/events?event_type=DEPLOYMENT")
    assert type_res.status_code == 200
    type_data = type_res.json()
    assert type_data["total"] == 1
    assert type_data["items"][0]["event_id"] == "evt-list-0"

    # 5. Filter by environment
    env_res = client.get("/api/v1/events?environment=staging")
    assert env_res.status_code == 200
    env_data = env_res.json()
    assert env_data["total"] == 3
    assert all(item["environment"] == "staging" for item in env_data["items"])
