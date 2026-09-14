from fastapi.testclient import TestClient
from backend.app.retrieval.clients.incident_client import IncidentServiceClient
from backend.app.retrieval.clients.log_intelligence_client import LogIntelligenceClient
from backend.app.retrieval.clients.rca_client import RCAServiceClient
from backend.app.retrieval.repositories.runbook_repository import RunbookRepository
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType
from backend.app.retrieval.schemas.runbooks import RunbookCreateRequest


def test_rag_context_generation(client: TestClient, monkeypatch, db_session):
    """Test POST /api/v1/rag/context produces structured context and formatted context_text for LLM."""
    # Seed Runbook
    RunbookRepository.create(
        db_session,
        RunbookCreateRequest(
            runbook_key="RB-RAG-01",
            title="Database Connection Recovery",
            content="Execute pg_terminate_backend on idle connections.",
            service="booking-api",
        ),
    )

    mock_log = RetrievalResultItem(
        source_type=SourceType.LOG,
        source_id="evt-rag-01",
        title="Log: DATABASE on booking-api",
        content="Connection pool saturated at 100%",
        service="booking-api",
        similarity_score=0.90,
        citation="[LOG:evt-rag-01]",
    )

    monkeypatch.setattr(
        LogIntelligenceClient,
        "search_logs",
        lambda *args, **kwargs: ([mock_log], None),
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
        "/api/v1/rag/context",
        json={"query": "database connection pool saturated", "top_k": 5},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["included_results"] >= 2
    assert "context_text" in data
    assert "[RUNBOOK:RB-RAG-01]" in data["context_text"]
    assert "[LOG:evt-rag-01]" in data["context_text"]
    assert "Execute pg_terminate_backend" in data["context_text"]
