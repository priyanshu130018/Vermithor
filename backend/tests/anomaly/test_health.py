from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Verify that GET /health returns 200 and healthy payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] in ["vermithor", "vermithor-backend", "anomaly-service", "correlation-service", "incident-service", "ingestion-service", "log-intelligence-service", "rca-service", "retrieval-service", "summary-service"]
    assert data["status"] in ["healthy", "ready", "degraded"]
