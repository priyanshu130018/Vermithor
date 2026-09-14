from fastapi.testclient import TestClient


def test_ingest_single_log_api(client: TestClient):
    """Test POST /api/v1/logs processes log, redacts secrets, extracts template, and generates embedding."""
    payload = {
        "source_event_id": "evt-test-001",
        "timestamp": "2026-08-29T12:00:00Z",
        "service": "booking-api",
        "environment": "production",
        "severity": "ERROR",
        "message": "Connection refused to postgres at 10.20.30.41:5432 with password=secret123",
        "trace_id": "tr-12345",
        "metadata": {"endpoint": "/api/v1/bookings"},
    }

    response = client.post("/api/v1/logs", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["source_event_id"] == "evt-test-001"
    assert data["service"] == "booking-api"
    assert data["category"] == "DATABASE"
    assert "secret123" not in data["normalized_message"]
    assert "password=<REDACTED>" in data["normalized_message"]
    assert "<IP>:<PORT>" in data["template"]
    assert data["embedding"] is not None
    assert data["embedding"]["dimension"] == 384

    # Fetch log by ID
    log_id = data["id"]
    get_res = client.get(f"/api/v1/logs/{log_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == log_id


def test_duplicate_source_event_id_idempotency(client: TestClient):
    """Test submitting same source_event_id returns existing record without duplication."""
    payload = {
        "source_event_id": "evt-dup-001",
        "timestamp": "2026-08-29T12:00:00Z",
        "service": "booking-api",
        "environment": "production",
        "severity": "ERROR",
        "message": "Connection refused to postgres",
    }

    res1 = client.post("/api/v1/logs", json=payload)
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    res2 = client.post("/api/v1/logs", json=payload)
    assert res2.status_code == 201
    assert res2.json()["id"] == id1


def test_get_nonexistent_log_404(client: TestClient):
    """Test retrieving non-existent log ID returns 404."""
    response = client.get("/api/v1/logs/123e4567-e89b-12d3-a456-426614174000")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
