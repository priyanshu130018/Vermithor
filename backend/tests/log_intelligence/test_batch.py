from fastapi.testclient import TestClient


def test_batch_log_ingestion_api(client: TestClient):
    """Test batch ingesting multiple logs in a single API call."""
    payload = {
        "logs": [
            {
                "source_event_id": f"batch-evt-{i}",
                "timestamp": f"2026-08-29T12:0{i}:00Z",
                "service": "orders-api" if i % 2 == 0 else "payment-api",
                "environment": "production",
                "severity": "ERROR" if i < 3 else "INFO",
                "message": f"Log message number {i} with IP 10.0.0.{i}:8080",
            }
            for i in range(5)
        ]
    }

    response = client.post("/api/v1/logs/batch", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["processed"] == 5
    assert len(data["items"]) == 5
    for item in data["items"]:
        assert item["embedding"] is not None
        assert item["embedding"]["dimension"] == 384
