from backend.app.summary.schemas.summaries import EvidenceItemSchema
from backend.app.summary.services.evidence_validator import EvidenceValidator


def test_evidence_validator_valid_and_unsupported_sources():
    """Verify supported citations are kept while hallucinated source IDs are stripped."""
    rag_context = {
        "context": [
            {"source_id": "evt-001"},
            {"source_id": "RB-DB-001"},
        ]
    }
    rca = {
        "analysis_key": "RCA-000001",
    }

    valid_ids = EvidenceValidator.extract_valid_source_ids(rag_context, rca)
    assert "evt-001" in valid_ids
    assert "rb-db-001" in valid_ids
    assert "rca-000001" in valid_ids

    evidence_items = [
        EvidenceItemSchema(claim="Database timed out", source_type="LOG", source_id="evt-001", support="Log excerpt"),
        EvidenceItemSchema(claim="Runbook applied", source_type="RUNBOOK", source_id="RB-DB-001", support="SOP excerpt"),
        EvidenceItemSchema(claim="Hallucinated claim", source_type="LOG", source_id="fake-source-999", support="Fake"),
    ]

    filtered, warnings = EvidenceValidator.validate_and_filter_evidence(evidence_items, valid_ids)

    assert len(filtered) == 2
    assert len(warnings) == 1
    assert "fake-source-999" in warnings[0]
    assert all(item.source_id != "fake-source-999" for item in filtered)
