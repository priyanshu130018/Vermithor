import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.anomaly.db.models import AnomalyResult, MetricObservation


def test_create_observation_and_detect_anomaly(client: TestClient):
    """Test full observation ingestion and anomaly detection pipeline."""
    # 1. Seed 10 normal historical observations
    for i in range(10):
        client.post(
            "/api/v1/observations",
            json={
                "observation_id": f"obs-hist-{i}",
                "timestamp": f"2026-08-29T12:{i:02d}:00Z",
                "service": "booking-api",
                "environment": "production",
                "metric_name": "request_latency",
                "metric_value": 100.0 + (i % 3),
                "unit": "ms",
                "labels": {"endpoint": "/api/book"},
            },
        )

    # 2. Ingest an extreme latency spike observation
    spike_payload = {
        "observation_id": "obs-spike-001",
        "timestamp": "2026-08-29T12:30:00Z",
        "service": "booking-api",
        "environment": "production",
        "metric_name": "request_latency",
        "metric_value": 950.0,
        "unit": "ms",
        "labels": {"endpoint": "/api/book", "region": "ap-south-1"},
    }
    response = client.post("/api/v1/observations", json=spike_payload)
    assert response.status_code == 201
    data = response.json()

    # Verify observation
    obs = data["observation"]
    assert obs["observation_id"] == "obs-spike-001"
    assert obs["metric_value"] == 950.0
    assert obs["service"] == "booking-api"

    # Verify anomalies evaluated by both detectors
    anomalies = data["anomalies"]
    assert len(anomalies) == 2
    detectors = {a["detector"] for a in anomalies}
    assert "STATISTICAL" in detectors
    assert "ISOLATION_FOREST" in detectors

    # Both detectors should flag this 9.5x spike as anomalous
    for a in anomalies:
        assert a["is_anomaly"] is True
        assert a["anomaly_score"] >= 0.60
        assert a["severity"] in ["MEDIUM", "HIGH", "CRITICAL"]
        assert a["reason"] is not None
        assert a["detector_version"] == "1.0"


def test_duplicate_observation_handling(client: TestClient, db_session: Session):
    """Test that duplicate observation_id is idempotent and creates only 1 DB record."""
    payload = {
        "observation_id": "obs-dup-001",
        "timestamp": "2026-08-29T12:00:00Z",
        "service": "payment-service",
        "environment": "production",
        "metric_name": "cpu_usage",
        "metric_value": 45.0,
        "unit": "percent",
    }

    # First POST -> 201 Created
    res1 = client.post("/api/v1/observations", json=payload)
    assert res1.status_code == 201

    # Second POST with same observation_id -> 200 OK
    res2 = client.post("/api/v1/observations", json=payload)
    assert res2.status_code == 200

    # Verify only 1 record exists in metric_observations table
    count = db_session.execute(
        select(func.count(MetricObservation.id)).where(
            MetricObservation.observation_id == "obs-dup-001"
        )
    ).scalar()
    assert count == 1


@pytest.mark.parametrize(
    "invalid_payload,expected_field",
    [
        (
            {
                # missing observation_id
                "timestamp": "2026-08-29T12:00:00Z",
                "service": "booking-api",
                "environment": "production",
                "metric_name": "request_latency",
                "metric_value": 100.0,
            },
            "observation_id",
        ),
        (
            {
                "observation_id": "obs-inv-1",
                "timestamp": "2026-08-29T12:00:00Z",
                # missing service
                "environment": "production",
                "metric_name": "request_latency",
                "metric_value": 100.0,
            },
            "service",
        ),
        (
            {
                "observation_id": "obs-inv-2",
                "timestamp": "2026-08-29 12:00:00",  # naive timestamp
                "service": "booking-api",
                "environment": "production",
                "metric_name": "request_latency",
                "metric_value": 100.0,
            },
            "timestamp",
        ),
    ],
)
def test_create_observation_validation_errors(
    client: TestClient,
    invalid_payload: dict,
    expected_field: str,
):
    """Test validation errors for schema violations return HTTP 422."""
    response = client.post("/api/v1/observations", json=invalid_payload)
    assert response.status_code == 422


def test_get_observation_by_id(client: TestClient):
    """Test retrieving an observation by observation_id."""
    # Non-existent
    res_404 = client.get("/api/v1/observations/non-existent-obs-999")
    assert res_404.status_code == 404

    # Create observation
    payload = {
        "observation_id": "obs-fetch-001",
        "timestamp": "2026-08-29T12:00:00Z",
        "service": "inventory-api",
        "environment": "staging",
        "metric_name": "memory_usage",
        "metric_value": 78.5,
        "unit": "percent",
    }
    client.post("/api/v1/observations", json=payload)

    # Fetch
    res_200 = client.get("/api/v1/observations/obs-fetch-001")
    assert res_200.status_code == 200
    fetched = res_200.json()
    assert fetched["observation_id"] == "obs-fetch-001"
    assert fetched["metric_value"] == 78.5
    assert fetched["service"] == "inventory-api"


def test_list_observations_and_anomalies(client: TestClient):
    """Test listing and filtering observations and anomalies."""
    for i in range(6):
        client.post(
            "/api/v1/observations",
            json={
                "observation_id": f"obs-list-{i}",
                "timestamp": f"2026-08-29T12:{i:02d}:00Z",
                "service": "orders-service" if i % 2 == 0 else "users-service",
                "environment": "production" if i < 3 else "staging",
                "metric_name": "request_rate",
                "metric_value": 500.0 if i == 5 else 50.0,
            },
        )

    # 1. List observations pagination
    res_obs = client.get("/api/v1/observations?page=1&page_size=2")
    assert res_obs.status_code == 200
    obs_data = res_obs.json()
    assert obs_data["total"] == 6
    assert obs_data["page"] == 1
    assert len(obs_data["items"]) == 2

    # 2. Filter observations by service
    res_srv = client.get("/api/v1/observations?service=orders-service")
    assert res_srv.status_code == 200
    assert res_srv.json()["total"] == 3

    # 3. Get anomalies for observation
    res_anom = client.get("/api/v1/anomalies/obs-list-5")
    assert res_anom.status_code == 200
    anom_list = res_anom.json()
    assert len(anom_list) == 2

    # 4. List anomalies filter by detector
    res_det = client.get("/api/v1/anomalies?detector=STATISTICAL")
    assert res_det.status_code == 200
    assert res_det.json()["total"] == 6
