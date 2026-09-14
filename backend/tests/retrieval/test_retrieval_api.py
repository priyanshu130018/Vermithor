from fastapi.testclient import TestClient
from backend.app.retrieval.clients.incident_client import IncidentServiceClient
from backend.app.retrieval.clients.log_intelligence_client import LogIntelligenceClient
from backend.app.retrieval.clients.rca_client import RCAServiceClient
from backend.app.retrieval.repositories.runbook_repository import RunbookRepository
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType
from backend.app.retrieval.schemas.runbooks import RunbookCreateRequest


def test_retrieval_search_multi_source(client: TestClient, monkeypatch, db_session):
    """Test POST /api/v1/retrieval/search collects evidence from runbooks, logs, incidents, and RCA."""
    # 1. Seed Runbook
    RunbookRepository.create(
        db_session,
        RunbookCreateRequest(
            runbook_key="RB-TEST-001",
            title="Postgres Connection Pool SOP",
            content="Restart connection pool service.",
            service="booking-api",
            environment="production",
            category="DATABASE",
        ),
    )

    # 2. Mock external service clients directly
    mock_log = RetrievalResultItem(
        source_type=SourceType.LOG,
        source_id="evt-mock-01",
        title="Log: DATABASE on booking-api",
        content="Connection refused to PostgreSQL server",
        service="booking-api",
        environment="production",
        similarity_score=0.88,
        citation="[LOG:evt-mock-01]",
    )
    mock_inc = RetrievalResultItem(
        source_type=SourceType.INCIDENT,
        source_id="INC-TEST-01",
        title="Incident: Database degradation",
        content="Database pool saturated",
        service="booking-api",
        environment="production",
        similarity_score=0.85,
        citation="[INCIDENT:INC-TEST-01]",
    )
    mock_rca = RetrievalResultItem(
        source_type=SourceType.RCA,
        source_id="RCA-TEST-01",
        title="RCA: PostgreSQL Connection Starvation",
        content="Primary Root Cause: PostgreSQL Connection Starvation",
        similarity_score=0.92,
        citation="[RCA:RCA-TEST-01]",
    )

    monkeypatch.setattr(
        LogIntelligenceClient,
        "search_logs",
        lambda *args, **kwargs: ([mock_log], None),
    )
    monkeypatch.setattr(
        IncidentServiceClient,
        "search_incidents",
        lambda *args, **kwargs: ([mock_inc], None),
    )
    monkeypatch.setattr(
        RCAServiceClient,
        "search_rca_reports",
        lambda *args, **kwargs: ([mock_rca], None),
    )

    res = client.post(
        "/api/v1/retrieval/search",
        json={
            "query": "postgres connection pool error",
            "service": "booking-api",
            "environment": "production",
            "top_k": 5,
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert data["total_results"] >= 4
    source_types = [item["source_type"] for item in data["results"]]
    assert "RUNBOOK" in source_types
    assert "LOG" in source_types
    assert "INCIDENT" in source_types
    assert "RCA" in source_types

    # Ensure every result has citation
    for r in data["results"]:
        assert r["citation"].startswith("[") and r["citation"].endswith("]")


def test_retrieval_search_partial_failure_resilience(client: TestClient, monkeypatch, db_session):
    """Test that when Log Intelligence is down, remaining sources succeed and warning is returned."""
    # Seed Runbook
    RunbookRepository.create(
        db_session,
        RunbookCreateRequest(
            runbook_key="RB-PARTIAL-01",
            title="Database SOP",
            content="Restart DB",
            service="booking-api",
        ),
    )

    monkeypatch.setattr(
        LogIntelligenceClient,
        "search_logs",
        lambda *args, **kwargs: ([], "Log Intelligence Service unavailable: Connection refused"),
    )
    monkeypatch.setattr(
        IncidentServiceClient,
        "search_incidents",
        lambda *args, **kwargs: ([], None),
    )
    monkeypatch.setattr(
        RCAServiceClient,
        "search_rca_reports",
        lambda *args, **kwargs: ([], None),
    )

    res = client.post(
        "/api/v1/retrieval/search",
        json={"query": "database error", "top_k": 5},
    )
    assert res.status_code == 200
    data = res.json()

    assert len(data["warnings"]) >= 1
    assert "unavailable" in data["warnings"][0].lower()
    # Still returns the runbook
    assert any(item["source_type"] == "RUNBOOK" for item in data["results"])


def test_retrieval_search_validation_empty_query_and_key(client: TestClient):
    """Test 422 when neither query nor incident_key is supplied."""
    res = client.post("/api/v1/retrieval/search", json={"top_k": 5})
    assert res.status_code == 422
