from datetime import datetime, timedelta, timezone
from backend.app.retrieval.retrieval.ranking import HybridRanker
from backend.app.retrieval.schemas.retrieval import RetrievalQuery, RetrievalResultItem, SourceType


def test_source_weight_preference():
    """Verify RCA source ranks higher than LOG source when semantic scores are equal."""
    ranker = HybridRanker()
    query = RetrievalQuery(query="database error")

    item_rca = RetrievalResultItem(
        source_type=SourceType.RCA,
        source_id="RCA-001",
        title="Database pool exhaustion",
        content="...",
        similarity_score=0.85,
        citation="[RCA:RCA-001]",
    )
    item_log = RetrievalResultItem(
        source_type=SourceType.LOG,
        source_id="log-001",
        title="Database timeout",
        content="...",
        similarity_score=0.85,
        citation="[LOG:log-001]",
    )

    scored_rca = ranker.score_item(item_rca, query)
    scored_log = ranker.score_item(item_log, query)

    assert scored_rca.final_score > scored_log.final_score


def test_metadata_boost_ranking():
    """Verify matching service and environment boost metadata score and final score."""
    ranker = HybridRanker()
    query = RetrievalQuery(
        query="database timeout",
        service="booking-api",
        environment="production",
    )

    item_matching = RetrievalResultItem(
        source_type=SourceType.LOG,
        source_id="log-match",
        title="Timeout log",
        content="...",
        service="booking-api",
        environment="production",
        similarity_score=0.80,
        citation="[LOG:log-match]",
    )
    item_mismatch = RetrievalResultItem(
        source_type=SourceType.LOG,
        source_id="log-mismatch",
        title="Timeout log",
        content="...",
        service="payment-api",
        environment="staging",
        similarity_score=0.80,
        citation="[LOG:log-mismatch]",
    )

    scored_match = ranker.score_item(item_matching, query)
    scored_mismatch = ranker.score_item(item_mismatch, query)

    assert scored_match.metadata_score > scored_mismatch.metadata_score
    assert scored_match.final_score > scored_mismatch.final_score


def test_recency_score_decay():
    """Verify recent incident ranks higher than a 60-day-old incident with identical parameters."""
    ranker = HybridRanker()
    query = RetrievalQuery(query="incident")

    now = datetime.now(timezone.utc)
    item_recent = RetrievalResultItem(
        source_type=SourceType.INCIDENT,
        source_id="INC-RECENT",
        title="Recent failure",
        content="...",
        timestamp=now - timedelta(hours=2),
        similarity_score=0.80,
        citation="[INCIDENT:INC-RECENT]",
    )
    item_old = RetrievalResultItem(
        source_type=SourceType.INCIDENT,
        source_id="INC-OLD",
        title="Old failure",
        content="...",
        timestamp=now - timedelta(days=60),
        similarity_score=0.80,
        citation="[INCIDENT:INC-OLD]",
    )

    scored_recent = ranker.score_item(item_recent, query)
    scored_old = ranker.score_item(item_old, query)

    assert scored_recent.recency_score > scored_old.recency_score
    assert scored_recent.final_score > scored_old.final_score
