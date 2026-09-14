import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.incidents.db.models import Incident, IncidentEvent


def test_create_incident_success(client: TestClient):
    """Test successful incident creation via POST /api/v1/incidents."""
    payload = {
        "title": "Database Connection Saturation",
        "description": "Connection pool reached critical capacity under load.",
        "severity": "SEV1",
        "environment": "production",
        "started_at": "2026-08-29T12:00:00Z",
        "confidence": 0.89,
    }
    response = client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["incident_key"].startswith("INC-")
    assert data["title"] == "Database Connection Saturation"
    assert data["description"] == "Connection pool reached critical capacity under load."
    assert data["severity"] == "SEV1"
    assert data["status"] == "DETECTED"
    assert data["environment"] == "production"
    assert data["confidence"] == 0.89
    assert data["ended_at"] is None
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.parametrize(
    "invalid_payload,expected_field",
    [
        (
            {
                # missing title
                "severity": "SEV1",
                "environment": "production",
                "started_at": "2026-08-29T12:00:00Z",
            },
            "title",
        ),
        (
            {
                "title": "Test Incident",
                "severity": "INVALID_SEV",  # invalid severity
                "environment": "production",
                "started_at": "2026-08-29T12:00:00Z",
            },
            "severity",
        ),
        (
            {
                "title": "Test Incident",
                "severity": "SEV2",
                "environment": "production",
                "started_at": "2026-08-29T12:00:00Z",
                "confidence": 1.5,  # confidence > 1.0
            },
            "confidence",
        ),
        (
            {
                "title": "Test Incident",
                "severity": "SEV2",
                "environment": "production",
                "started_at": "2026-08-29T12:00:00Z",
                "confidence": -0.1,  # confidence < 0.0
            },
            "confidence",
        ),
        (
            {
                "title": "Test Incident",
                "severity": "SEV2",
                "environment": "production",
                "started_at": "2026-08-29 12:00:00",  # naive timestamp
            },
            "started_at",
        ),
    ],
)
def test_create_incident_validation_errors(
    client: TestClient,
    invalid_payload: dict,
    expected_field: str,
):
    """Test that schema violations return HTTP 422 with validation errors."""
    response = client.post("/api/v1/incidents", json=invalid_payload)
    assert response.status_code == 422
    errors = response.json().get("detail", [])
    assert any(expected_field in str(err.get("loc", [])) for err in errors)


def test_get_incident_by_key(client: TestClient):
    """Test retrieving an incident by its incident_key."""
    # 1. Non-existent key returns 404
    res_404 = client.get("/api/v1/incidents/INC-999999")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"].lower()

    # 2. Create an incident
    create_res = client.post(
        "/api/v1/incidents",
        json={
            "title": "API Gateway 502 Spikes",
            "severity": "SEV2",
            "environment": "production",
            "started_at": "2026-08-29T13:00:00Z",
        },
    )
    assert create_res.status_code == 201
    incident_key = create_res.json()["incident_key"]

    # 3. Retrieve incident
    res_200 = client.get(f"/api/v1/incidents/{incident_key}")
    assert res_200.status_code == 200
    fetched = res_200.json()
    assert fetched["incident_key"] == incident_key
    assert fetched["title"] == "API Gateway 502 Spikes"
    assert fetched["severity"] == "SEV2"
    assert fetched["status"] == "DETECTED"


def test_list_incidents_pagination_and_filtering(client: TestClient):
    """Test listing incidents with pagination and multi-field filters."""
    # Seed incidents
    for i in range(5):
        client.post(
            "/api/v1/incidents",
            json={
                "title": f"Incident {i}",
                "severity": "SEV1" if i % 2 == 0 else "SEV3",
                "environment": "production" if i < 3 else "staging",
                "started_at": f"2026-08-29T12:{i:02d}:00Z",
            },
        )

    # 1. Pagination
    res_p1 = client.get("/api/v1/incidents?page=1&page_size=2")
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert p1_data["total"] == 5
    assert p1_data["page"] == 1
    assert p1_data["page_size"] == 2
    assert p1_data["total_pages"] == 3
    assert len(p1_data["items"]) == 2

    res_p2 = client.get("/api/v1/incidents?page=2&page_size=2")
    assert res_p2.status_code == 200
    p2_data = res_p2.json()
    assert len(p2_data["items"]) == 2

    # 2. Filter by severity
    res_sev = client.get("/api/v1/incidents?severity=SEV1")
    assert res_sev.status_code == 200
    sev_data = res_sev.json()
    assert sev_data["total"] == 3
    assert all(item["severity"] == "SEV1" for item in sev_data["items"])

    # 3. Filter by environment
    res_env = client.get("/api/v1/incidents?environment=staging")
    assert res_env.status_code == 200
    env_data = res_env.json()
    assert env_data["total"] == 2
    assert all(item["environment"] == "staging" for item in env_data["items"])


def test_lifecycle_transitions_happy_path(client: TestClient):
    """Test valid sequential state transitions: DETECTED -> INVESTIGATING -> ACKNOWLEDGED -> RESOLVED -> CLOSED."""
    create_res = client.post(
        "/api/v1/incidents",
        json={
            "title": "Payment Checkout Failures",
            "severity": "SEV1",
            "environment": "production",
            "started_at": "2026-08-29T10:00:00Z",
        },
    )
    incident_key = create_res.json()["incident_key"]

    # 1. DETECTED -> INVESTIGATING
    res_inv = client.post(f"/api/v1/incidents/{incident_key}/investigate")
    assert res_inv.status_code == 200
    assert res_inv.json()["status"] == "INVESTIGATING"

    # 2. INVESTIGATING -> ACKNOWLEDGED
    res_ack = client.post(f"/api/v1/incidents/{incident_key}/acknowledge")
    assert res_ack.status_code == 200
    assert res_ack.json()["status"] == "ACKNOWLEDGED"

    # 3. ACKNOWLEDGED -> RESOLVED (sets ended_at)
    res_res = client.post(f"/api/v1/incidents/{incident_key}/resolve")
    assert res_res.status_code == 200
    res_data = res_res.json()
    assert res_data["status"] == "RESOLVED"
    assert res_data["ended_at"] is not None
    resolved_ended_at = res_data["ended_at"]

    # 4. RESOLVED -> CLOSED (preserves ended_at)
    res_close = client.post(f"/api/v1/incidents/{incident_key}/close")
    assert res_close.status_code == 200
    close_data = res_close.json()
    assert close_data["status"] == "CLOSED"
    assert close_data["ended_at"] == resolved_ended_at


def test_lifecycle_alternate_transitions(client: TestClient):
    """Test alternate valid paths (e.g. DETECTED -> FALSE_POSITIVE, INVESTIGATING -> RESOLVED)."""
    # 1. False Positive from DETECTED
    create_res1 = client.post(
        "/api/v1/incidents",
        json={
            "title": "Spurious Alert",
            "severity": "SEV4",
            "environment": "staging",
            "started_at": "2026-08-29T10:00:00Z",
        },
    )
    key1 = create_res1.json()["incident_key"]
    res_fp = client.post(f"/api/v1/incidents/{key1}/false-positive")
    assert res_fp.status_code == 200
    assert res_fp.json()["status"] == "FALSE_POSITIVE"

    # 2. Direct RESOLVED from INVESTIGATING
    create_res2 = client.post(
        "/api/v1/incidents",
        json={
            "title": "Quick Fix Incident",
            "severity": "SEV3",
            "environment": "production",
            "started_at": "2026-08-29T10:00:00Z",
        },
    )
    key2 = create_res2.json()["incident_key"]
    client.post(f"/api/v1/incidents/{key2}/investigate")
    res_res2 = client.post(f"/api/v1/incidents/{key2}/resolve")
    assert res_res2.status_code == 200
    assert res_res2.json()["status"] == "RESOLVED"


def test_lifecycle_invalid_transitions_rejected(client: TestClient):
    """Test that illegal status transitions are rejected with HTTP 409 Conflict."""
    create_res = client.post(
        "/api/v1/incidents",
        json={
            "title": "Lifecycle Test Incident",
            "severity": "SEV2",
            "environment": "production",
            "started_at": "2026-08-29T10:00:00Z",
        },
    )
    key = create_res.json()["incident_key"]

    # 1. DETECTED -> CLOSED (Illegal)
    res_bad1 = client.post(f"/api/v1/incidents/{key}/close")
    assert res_bad1.status_code == 409
    assert "invalid incident status transition" in res_bad1.json()["detail"].lower()

    # Move to RESOLVED then CLOSED
    client.post(f"/api/v1/incidents/{key}/investigate")
    client.post(f"/api/v1/incidents/{key}/resolve")
    client.post(f"/api/v1/incidents/{key}/close")

    # 2. CLOSED -> INVESTIGATING (Illegal)
    res_bad2 = client.post(f"/api/v1/incidents/{key}/investigate")
    assert res_bad2.status_code == 409
    assert "CLOSED -> INVESTIGATING" in res_bad2.json()["detail"]

    # 3. CLOSED -> RESOLVED (Illegal)
    res_bad3 = client.post(f"/api/v1/incidents/{key}/resolve")
    assert res_bad3.status_code == 409


def test_event_association_and_duplicate_handling(
    client: TestClient, db_session: Session
):
    """Test associating external event IDs with an incident and verifying duplicate prevention."""
    # 1. Create Incident
    create_res = client.post(
        "/api/v1/incidents",
        json={
            "title": "Memory Leak Incident",
            "severity": "SEV2",
            "environment": "production",
            "started_at": "2026-08-29T11:00:00Z",
        },
    )
    key = create_res.json()["incident_key"]

    # 2. Associate event
    event_payload = {
        "event_id": "evt-mem-001",
        "relation_type": "METRIC_ANOMALY",
        "score": 0.95,
    }
    assoc_res1 = client.post(f"/api/v1/incidents/{key}/events", json=event_payload)
    assert assoc_res1.status_code == 201
    assoc_data = assoc_res1.json()
    assert assoc_data["event_id"] == "evt-mem-001"
    assert assoc_data["relation_type"] == "METRIC_ANOMALY"
    assert assoc_data["score"] == 0.95

    # 3. Duplicate event association (idempotent, returns 200 OK)
    assoc_res2 = client.post(f"/api/v1/incidents/{key}/events", json=event_payload)
    assert assoc_res2.status_code == 200
    assert assoc_res2.json()["event_id"] == "evt-mem-001"

    # Verify only 1 association record exists in DB
    count = db_session.execute(
        select(func.count(IncidentEvent.id)).where(IncidentEvent.event_id == "evt-mem-001")
    ).scalar()
    assert count == 1

    # 4. Attach a second event
    client.post(
        f"/api/v1/incidents/{key}/events",
        json={
            "event_id": "evt-log-002",
            "relation_type": "PRIMARY_SIGNAL",
            "score": 0.88,
        },
    )

    # 5. List events for incident
    list_res = client.get(f"/api/v1/incidents/{key}/events")
    assert list_res.status_code == 200
    events = list_res.json()
    assert len(events) == 2
    event_ids = [ev["event_id"] for ev in events]
    assert "evt-mem-001" in event_ids
    assert "evt-log-002" in event_ids


def test_event_association_nonexistent_incident(client: TestClient):
    """Test associating events to non-existent incidents returns 404."""
    res_post = client.post(
        "/api/v1/incidents/INC-NONEXISTENT/events",
        json={
            "event_id": "evt-001",
            "relation_type": "PRIMARY_SIGNAL",
        },
    )
    assert res_post.status_code == 404

    res_get = client.get("/api/v1/incidents/INC-NONEXISTENT/events")
    assert res_get.status_code == 404
