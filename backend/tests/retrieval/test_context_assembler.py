from backend.app.retrieval.retrieval.context_assembler import ContextAssembler
from backend.app.retrieval.schemas.retrieval import RetrievalResultItem, SourceType


def test_context_assembler_budget_and_citation():
    """Verify context assembler respects limits and attaches citations."""
    assembler = ContextAssembler()

    items = [
        RetrievalResultItem(
            source_type=SourceType.RCA,
            source_id="RCA-001",
            title="Database pool saturation",
            content="Detailed RCA content with steps and logs.",
            final_score=0.95,
            citation="[RCA:RCA-001]",
        ),
        RetrievalResultItem(
            source_type=SourceType.RUNBOOK,
            source_id="RB-001",
            title="DB Recovery",
            content="Restart connection pool.",
            final_score=0.85,
            citation="[RUNBOOK:RB-001]",
        ),
        RetrievalResultItem(
            source_type=SourceType.LOG,
            source_id="log-001",
            title="Error log",
            content="Connection refused.",
            final_score=0.75,
            citation="[LOG:log-001]",
        ),
    ]

    included, text, truncated = assembler.assemble(items, max_results=2, max_chars=10000)

    assert len(included) == 2
    assert truncated is True
    assert "[RCA:RCA-001]" in text
    assert "[RUNBOOK:RB-001]" in text
    assert "[LOG:log-001]" not in text


def test_context_assembler_char_limit_truncation():
    """Verify context assembler truncates safely when characters exceed budget."""
    assembler = ContextAssembler()
    huge_content = "A" * 5000

    items = [
        RetrievalResultItem(
            source_type=SourceType.RUNBOOK,
            source_id="RB-HUGE",
            title="Massive Runbook",
            content=huge_content,
            final_score=0.90,
            citation="[RUNBOOK:RB-HUGE]",
        ),
    ]

    included, text, truncated = assembler.assemble(items, max_results=5, max_chars=500)
    assert truncated is True
    assert len(text) < 700
