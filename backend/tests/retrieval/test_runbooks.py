from fastapi.testclient import TestClient


def test_runbook_crud_and_search(client: TestClient):
    """Test full CRUD lifecycle and search for operational runbooks."""
    # 1. Create Runbook
    payload = {
        "runbook_key": "RB-DB-001",
        "title": "Database Connection Pool Troubleshooting",
        "description": "Steps to diagnose and recover from DB connection exhaustion",
        "content": "Check database connection pool utilization. Check active connections. Restart service if saturated.",
        "service": "booking-api",
        "environment": "production",
        "category": "DATABASE",
        "tags": ["postgres", "connections", "db"],
    }
    create_res = client.post("/api/v1/runbooks", json=payload)
    assert create_res.status_code == 201
    rb_data = create_res.json()
    assert rb_data["runbook_key"] == "RB-DB-001"
    assert rb_data["title"] == "Database Connection Pool Troubleshooting"

    # 2. Get Runbook by Key
    get_res = client.get("/api/v1/runbooks/RB-DB-001")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Database Connection Pool Troubleshooting"

    # 3. List Runbooks
    list_res = client.get("/api/v1/runbooks?service=booking-api")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1

    # 4. Search Runbooks
    search_res = client.post(
        "/api/v1/runbooks/search",
        json={"query": "database connection pool", "top_k": 3},
    )
    assert search_res.status_code == 200
    search_items = search_res.json()
    assert len(search_items) >= 1
    assert search_items[0]["source_id"] == "RB-DB-001"

    # 5. Delete Runbook
    del_res = client.delete("/api/v1/runbooks/RB-DB-001")
    assert del_res.status_code == 204

    # 6. Verify 404 after deletion
    get_404 = client.get("/api/v1/runbooks/RB-DB-001")
    assert get_404.status_code == 404
