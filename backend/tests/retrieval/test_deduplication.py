from backend.app.retrieval.retrieval.deduplication import ResultDeduplicator
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType


def test_deduplicate_identical_sources():
    """Verify duplicate source items are deduplicated and keep the higher score."""
    item1 = RetrievalResultItem(
        source_type=SourceType.RCA,
        source_id="RCA-001",
        title="RCA report v1",
        content="First version",
        final_score=0.75,
        citation="[RCA:RCA-001]",
    )
    item2 = RetrievalResultItem(
        source_type=SourceType.RCA,
        source_id="RCA-001",
        title="RCA report v2",
        content="Updated version",
        final_score=0.92,
        citation="[RCA:RCA-001]",
    )
    item3 = RetrievalResultItem(
        source_type=SourceType.RUNBOOK,
        source_id="RB-001",
        title="Runbook DB",
        content="DB steps",
        final_score=0.80,
        citation="[RUNBOOK:RB-001]",
    )

    deduped = ResultDeduplicator.deduplicate([item1, item2, item3])
    assert len(deduped) == 2
    rca_item = next(i for i in deduped if i.source_type == SourceType.RCA)
    assert rca_item.final_score == 0.92
