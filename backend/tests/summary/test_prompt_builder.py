from backend.app.summary.prompts.incident_summary import IncidentSummaryPromptBuilder


def test_prompt_builder_structure():
    """Verify prompt builder contains all required grounding, security, and contextual sections."""
    incident = {
        "incident_key": "INC-000001",
        "service": "booking-api",
        "environment": "production",
        "severity": "CRITICAL",
        "title": "Booking API Outage",
        "description": "HTTP 500 errors on checkout",
        "started_at": "2026-08-29T12:00:00Z",
    }
    rca = {
        "analysis_key": "RCA-000001",
        "status": "COMPLETED",
        "primary_root_cause": "PostgreSQL Connection Pool Exhaustion",
        "primary_confidence": 0.94,
        "candidates": [{"candidate_name": "PostgreSQL Connection Pool Exhaustion", "score": 0.94}],
    }
    rag_context = {
        "context_text": "### [LOG:evt-101] Connection refused to PostgreSQL\n### [RUNBOOK:RB-001] DB Recovery SOP",
    }

    prompt = IncidentSummaryPromptBuilder.build_prompt(
        incident=incident,
        rca=rca,
        rag_context=rag_context,
    )

    # Grounding & security assertions
    assert "PROMPT INJECTION DEFENSE" in prompt
    assert "UNTRUSTED DATA" in prompt
    assert "Insufficient evidence" in prompt
    assert "INC-000001" in prompt
    assert "booking-api" in prompt
    assert "RCA-000001" in prompt
    assert "PostgreSQL Connection Pool Exhaustion" in prompt
    assert "[LOG:evt-101]" in prompt
    assert "[RUNBOOK:RB-001]" in prompt
    assert "OUTPUT FORMAT" in prompt
