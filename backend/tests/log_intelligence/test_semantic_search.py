from fastapi.testclient import TestClient


def test_semantic_vector_search_and_ranking(client: TestClient):
    """Test semantic similarity search returns top semantically related logs."""
    # 1. Ingest 4 distinct logs
    logs = [
        {
            "source_event_id": "search-evt-1",
            "timestamp": "2026-08-29T12:00:00Z",
            "service": "booking-api",
            "environment": "production",
            "severity": "ERROR",
            "message": "Connection refused to PostgreSQL database server",
        },
        {
            "source_event_id": "search-evt-2",
            "timestamp": "2026-08-29T12:01:00Z",
            "service": "booking-api",
            "environment": "production",
            "severity": "ERROR",
            "message": "Unable to establish database connection to replica",
        },
        {
            "source_event_id": "search-evt-3",
            "timestamp": "2026-08-29T12:02:00Z",
            "service": "auth-api",
            "environment": "production",
            "severity": "WARNING",
            "message": "User authentication failed due to invalid JWT token",
        },
        {
            "source_event_id": "search-evt-4",
            "timestamp": "2026-08-29T12:03:00Z",
            "service": "worker-service",
            "environment": "production",
            "severity": "HIGH",
            "message": "CPU utilization exceeded threshold reaching 98 percent",
        },
    ]
    batch_res = client.post("/api/v1/logs/batch", json={"logs": logs})
    assert batch_res.status_code == 201

    # 2. Semantic search query: "database connection timeout"
    search_payload = {
        "query": "database connection timeout",
        "top_k": 4,
    }
    search_res = client.post("/api/v1/logs/search", json=search_payload)
    assert search_res.status_code == 200
    search_data = search_res.json()

    assert search_data["total_results"] == 4
    top_matches = search_data["results"]

    # The top 2 results must be the database-related logs (evt-1 and evt-2)
    top_source_ids = [r["source_event_id"] for r in top_matches[:2]]
    assert "search-evt-1" in top_source_ids
    assert "search-evt-2" in top_source_ids

    # 3. Filtered search: service="auth-api"
    filtered_res = client.post(
        "/api/v1/logs/search",
        json={"query": "database error", "service": "auth-api"},
    )
    assert filtered_res.status_code == 200
    filtered_data = filtered_res.json()
    assert filtered_data["total_results"] == 1
    assert filtered_data["results"][0]["service"] == "auth-api"


def test_similar_logs_endpoint(client: TestClient):
    """Test GET /api/v1/logs/{log_id}/similar finds related logs excluding the target log."""
    res_a = client.post(
        "/api/v1/logs",
        json={
            "source_event_id": "sim-evt-a",
            "timestamp": "2026-08-29T12:00:00Z",
            "service": "booking-api",
            "environment": "production",
            "severity": "ERROR",
            "message": "PostgreSQL connection pool exhausted",
        },
    )
    res_b = client.post(
        "/api/v1/logs",
        json={
            "source_event_id": "sim-evt-b",
            "timestamp": "2026-08-29T12:01:00Z",
            "service": "booking-api",
            "environment": "production",
            "severity": "ERROR",
            "message": "Failed to acquire database connection from pool",
        },
    )
    log_a_id = res_a.json()["id"]

    sim_res = client.get(f"/api/v1/logs/{log_a_id}/similar?top_k=2")
    assert sim_res.status_code == 200
    sim_data = sim_res.json()

    assert len(sim_data) >= 1
    # Ensure source log A is excluded from results
    returned_ids = [item["log_id"] for item in sim_data]
    assert log_a_id not in returned_ids
    assert res_b.json()["id"] in returned_ids
